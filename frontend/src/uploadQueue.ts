/**
 * The upload queue: one file at a time, each with one client key that is reused
 * on every retry, so the server never makes the same item twice.
 *
 * Pure apart from the injected dependencies, so it can be tested without a browser.
 */

export type UploadStatus = 'waiting' | 'resizing' | 'uploading' | 'done' | 'failed';

export interface QueueEntry {
  id: string;
  name: string;
  clientKey: string;
  status: UploadStatus;
  /** Upload attempts made so far for the current run (reset by a manual retry). */
  attempts: number;
  error: string | null;
  itemId: string | null;
}

export interface UploadErrorLike {
  status?: number;
  message?: string;
}

export interface QueueDeps<F> {
  /** Resize/re-encode; returns the blob to send and its file name. */
  prepare(file: F): Promise<{ blob: Blob; filename: string }>;
  upload(blob: Blob, filename: string, clientKey: string): Promise<{ id: string }>;
  newKey(): string;
  sleep(ms: number): Promise<void>;
  /** File name to show. */
  nameOf(file: F): string;
  /** How many times a network failure is retried automatically. Default 3. */
  autoRetries?: number;
  /** First backoff delay in ms; doubles each time. Default 1000. */
  backoffMs?: number;
}

/** Failures worth retrying without asking: the connection dropped or the server hiccupped. */
export function isTransient(err: UploadErrorLike): boolean {
  const s = err.status ?? 0;
  return s === 0 || s === 408 || s === 429 || s >= 500;
}

export function backoff(attempt: number, base = 1000): number {
  return base * 2 ** (attempt - 1);
}

type Listener = (entries: QueueEntry[]) => void;

export class UploadQueue<F> {
  private entries: QueueEntry[] = [];
  private files = new Map<string, F>();
  private prepared = new Map<string, { blob: Blob; filename: string }>();
  private listeners = new Set<Listener>();
  private running = false;
  private seq = 0;

  constructor(private deps: QueueDeps<F>) {}

  get snapshot(): QueueEntry[] {
    return this.entries;
  }

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  add(files: F[]): string[] {
    const ids = files.map((file) => {
      const id = `u${++this.seq}`;
      this.files.set(id, file);
      this.entries = [...this.entries, {
        id, name: this.deps.nameOf(file), clientKey: this.deps.newKey(), status: 'waiting', attempts: 0, error: null, itemId: null,
      }];
      return id;
    });
    this.emit();
    void this.run();
    return ids;
  }

  /** Try a failed upload again, with the same client key. */
  retry(id: string): void {
    const e = this.entries.find((x) => x.id === id);
    if (!e || e.status !== 'failed') return;
    this.update(id, { status: 'waiting', error: null, attempts: 0 });
    void this.run();
  }

  /** Forget finished and failed rows. */
  clearFinished(): void {
    const keep = this.entries.filter((e) => e.status !== 'done' && e.status !== 'failed');
    for (const e of this.entries) if (!keep.includes(e)) {
      this.files.delete(e.id);
      this.prepared.delete(e.id);
    }
    this.entries = keep;
    this.emit();
  }

  get busy(): boolean {
    return this.entries.some((e) => e.status === 'waiting' || e.status === 'resizing' || e.status === 'uploading');
  }

  /** Resolves when nothing is waiting or in progress. */
  async idle(): Promise<void> {
    while (this.running) await new Promise((r) => setTimeout(r, 1));
  }

  private update(id: string, patch: Partial<QueueEntry>) {
    this.entries = this.entries.map((e) => (e.id === id ? { ...e, ...patch } : e));
    this.emit();
  }

  private emit() {
    for (const l of this.listeners) l(this.entries);
  }

  private async run(): Promise<void> {
    if (this.running) return;
    this.running = true;
    try {
      for (;;) {
        const next = this.entries.find((e) => e.status === 'waiting');
        if (!next) break;
        await this.process(next.id);
      }
    } finally {
      this.running = false;
    }
  }

  private async process(id: string): Promise<void> {
    const file = this.files.get(id) as F;
    let ready = this.prepared.get(id);
    if (!ready) {
      this.update(id, { status: 'resizing' });
      try {
        ready = await this.deps.prepare(file);
      } catch {
        ready = { blob: file as unknown as Blob, filename: this.deps.nameOf(file) };
      }
      this.prepared.set(id, ready);
    }
    const limit = this.deps.autoRetries ?? 3;
    for (;;) {
      const entry = this.entries.find((e) => e.id === id)!;
      const attempt = entry.attempts + 1;
      this.update(id, { status: 'uploading', attempts: attempt });
      try {
        const item = await this.deps.upload(ready.blob, ready.filename, entry.clientKey);
        this.update(id, { status: 'done', itemId: item.id, error: null });
        return;
      } catch (err) {
        const e = err as UploadErrorLike;
        const message = e?.message || 'The upload did not work.';
        // attempt 1 is the first try; up to `limit` automatic retries follow it
        if (isTransient(e) && attempt <= limit) {
          this.update(id, { error: `${message} Trying again…` });
          await this.deps.sleep(backoff(attempt, this.deps.backoffMs));
          continue;
        }
        this.update(id, { status: 'failed', error: message });
        return;
      }
    }
  }
}
