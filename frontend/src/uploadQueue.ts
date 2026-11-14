/**
 * The upload queue: at most two files at a time, each with one client key that
 * is reused on every retry, so the server never makes the same item twice.
 *
 * The list (names, keys and what happened to each) can be saved, so an import
 * cut short by a closed tab or a restart can be carried on: the files have to be
 * chosen again; each keeps its first key, so the ones that already went in are
 * answered at once by the server and never added twice.
 *
 * Pure apart from the injected dependencies, so it can be tested without a browser.
 */

export type UploadStatus = 'waiting' | 'resizing' | 'uploading' | 'done' | 'duplicate' | 'failed' | 'missing';

export interface QueueEntry {
  id: string;
  name: string;
  /** Recognises the same file chosen again (name, size and date by default). */
  fileKey: string;
  clientKey: string;
  status: UploadStatus;
  /** Upload attempts made so far for the current run (reset by a manual retry). */
  attempts: number;
  error: string | null;
  itemId: string | null;
  /** The photo holds several pieces: it is kept once and each piece found in it becomes an item after a check. */
  several: boolean;
  /** For a photo of several pieces, the kept photo, whose boxes are checked before its items are added. */
  sourceId: string | null;
}

/** What is kept between visits (lists saved before photos of several pieces have neither of the last two). */
export type SavedEntry = Pick<QueueEntry, 'name' | 'fileKey' | 'clientKey' | 'status' | 'error' | 'itemId'>
  & Partial<Pick<QueueEntry, 'several' | 'sourceId'>>;

/** What the server answered for one upload: the item (or, for several pieces, the kept photo) it went into. */
export interface Uploaded {
  id: string | null;
  duplicate?: boolean;
  sourceId?: string | null;
}

export interface UploadErrorLike {
  status?: number;
  message?: string;
}

export interface QueueDeps<F> {
  /** Resize/re-encode; returns the blob to send and its file name. */
  prepare(file: F): Promise<{ blob: Blob; filename: string }>;
  /** `sha256` is the hash of the file as chosen (null if it could not be worked out); `several` sends it as a photo
   * of several pieces. */
  upload(blob: Blob, filename: string, clientKey: string, sha256: string | null, several: boolean): Promise<Uploaded>;
  newKey(): string;
  sleep(ms: number): Promise<void>;
  /** File name to show. */
  nameOf(file: F): string;
  /** Identity of a file, to recognise it when chosen again. Defaults to its name. */
  keyOf?(file: F): string;
  /** SHA-256 of the file as chosen, so the server can refuse a photo it already has. */
  hash?(file: F): Promise<string | null>;
  /** Where the list is kept between visits. */
  store?: { load(): SavedEntry[] | null; save(entries: SavedEntry[]): void };
  /** How many uploads run at once. Default 2. */
  concurrency?: number;
  /** How many times a network failure is retried automatically. Default 3. */
  autoRetries?: number;
  /** First backoff delay in ms; doubles each time. Default 1000. */
  backoffMs?: number;
}

export interface AddResult<F> {
  /** Rows that were queued (new, or an earlier row given its file again), in the order of `files`. */
  ids: string[];
  files: F[];
  /** Files left out because they are already waiting or uploading. */
  skipped: number;
}

export interface QueueCounts {
  waiting: number;
  uploading: number;
  done: number;
  duplicate: number;
  failed: number;
  missing: number;
}

/** Failures worth retrying without asking: the connection dropped or the server hiccupped. */
export function isTransient(err: UploadErrorLike): boolean {
  const s = err.status ?? 0;
  return s === 0 || s === 408 || s === 429 || s >= 500;
}

export function backoff(attempt: number, base = 1000): number {
  return base * 2 ** (attempt - 1);
}

export function countEntries(entries: QueueEntry[]): QueueCounts {
  const c: QueueCounts = { waiting: 0, uploading: 0, done: 0, duplicate: 0, failed: 0, missing: 0 };
  for (const e of entries) {
    if (e.status === 'resizing' || e.status === 'uploading') c.uploading++;
    else c[e.status]++;
  }
  return c;
}

const FINISHED: UploadStatus[] = ['done', 'duplicate'];
const IN_PROGRESS: UploadStatus[] = ['waiting', 'resizing', 'uploading'];

type Listener = (entries: QueueEntry[]) => void;

export class UploadQueue<F> {
  private entries: QueueEntry[] = [];
  private files = new Map<string, F>();
  private prepared = new Map<string, { blob: Blob; filename: string; sha256: string | null }>();
  private listeners = new Set<Listener>();
  private active = 0;
  private seq = 0;
  private paused = false;
  private online = true;

  constructor(private deps: QueueDeps<F>) {
    let saved: SavedEntry[] | null;
    try {
      saved = deps.store?.load() ?? null;
    } catch {
      saved = null;
    }
    if (Array.isArray(saved)) {
      // the files themselves are gone; anything not finished needs choosing again
      this.entries = saved.map((s) => ({
        id: `u${++this.seq}`, name: s.name, fileKey: s.fileKey, clientKey: s.clientKey,
        status: FINISHED.includes(s.status) ? s.status : 'missing',
        attempts: 0, error: FINISHED.includes(s.status) ? null : s.error, itemId: s.itemId ?? null,
        several: s.several ?? false, sourceId: s.sourceId ?? null,
      }));
    }
  }

  get snapshot(): QueueEntry[] {
    return this.entries;
  }

  get isPaused(): boolean {
    return this.paused;
  }

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  /** Queue files; with `several`, each is a photo of several pieces. */
  add(files: F[], opts: { several?: boolean } = {}): AddResult<F> {
    const several = opts.several ?? false;
    const result: AddResult<F> = { ids: [], files: [], skipped: 0 };
    for (const file of files) {
      const fileKey = this.deps.keyOf ? this.deps.keyOf(file) : this.deps.nameOf(file);
      const known = this.entries.find((e) => e.fileKey === fileKey);
      if (known && IN_PROGRESS.includes(known.status)) {
        result.skipped++;
        continue;
      }
      let id: string;
      if (known) {
        // An earlier row gets its file back and keeps its key, so it cannot go in twice. Rows that already
        // went in are sent again too: the server recognises the key without processing the photo again, and if that item has been
        // deleted since (or this is the other closet), the photo is added as it should be.
        id = known.id;
        this.prepared.delete(id);
        this.entries = this.entries.map((e) => (e.id === id ? { ...e, status: 'waiting', attempts: 0, error: null, several } : e));
      } else {
        id = `u${++this.seq}`;
        this.entries = [...this.entries, {
          id, name: this.deps.nameOf(file), fileKey, clientKey: this.deps.newKey(), status: 'waiting', attempts: 0, error: null, itemId: null,
          several, sourceId: null,
        }];
      }
      this.files.set(id, file);
      result.ids.push(id);
      result.files.push(file);
    }
    this.emit();
    this.pump();
    return result;
  }

  /** Try a failed upload again, with the same client key. */
  retry(id: string): void {
    const e = this.entries.find((x) => x.id === id);
    if (!e || e.status !== 'failed' || !this.files.has(id)) return;
    this.update(id, { status: 'waiting', error: null, attempts: 0 });
    this.pump();
  }

  retryFailed(): void {
    for (const e of this.entries) if (e.status === 'failed') this.retry(e.id);
  }

  /** No new uploads start; the ones already going finish. */
  pause(): void {
    this.paused = true;
    this.emit();
  }

  resume(): void {
    this.paused = false;
    this.emit();
    this.pump();
  }

  /** Drops everything not yet started (and rows waiting for their file); uploads already going finish. */
  cancel(): void {
    this.drop((e) => e.status === 'waiting' || e.status === 'failed' || e.status === 'missing');
    this.paused = false;
    this.emit();
  }

  /** While offline nothing starts, and an upload cut off by it waits instead of failing. */
  setOnline(online: boolean): void {
    if (online === this.online) return;
    this.online = online;
    this.pump();
  }

  /** Forget finished and failed rows. */
  clearFinished(): void {
    this.drop((e) => e.status === 'done' || e.status === 'duplicate' || e.status === 'failed');
    this.emit();
  }

  get busy(): boolean {
    return this.entries.some((e) => IN_PROGRESS.includes(e.status));
  }

  /** Resolves when no upload is in progress (waiting rows may remain while paused or offline). */
  async idle(): Promise<void> {
    while (this.active > 0) await new Promise((r) => setTimeout(r, 1));
  }

  private drop(remove: (e: QueueEntry) => boolean) {
    const keep = this.entries.filter((e) => !remove(e));
    for (const e of this.entries) if (!keep.includes(e)) {
      this.files.delete(e.id);
      this.prepared.delete(e.id);
    }
    this.entries = keep;
  }

  private update(id: string, patch: Partial<QueueEntry>) {
    this.entries = this.entries.map((e) => (e.id === id ? { ...e, ...patch } : e));
    this.emit();
  }

  private emit() {
    for (const l of this.listeners) l(this.entries);
    if (this.deps.store) {
      try {
        this.deps.store.save(this.entries.map(({ name, fileKey, clientKey, status, error, itemId, several, sourceId }) =>
          ({ name, fileKey, clientKey, status, error, itemId, several, sourceId })));
      } catch {
        /* storage full or blocked: the import still runs, it just cannot be resumed */
      }
    }
  }

  private pump(): void {
    const limit = this.deps.concurrency ?? 2;
    while (!this.paused && this.online && this.active < limit) {
      const next = this.entries.find((e) => e.status === 'waiting');
      if (!next) break;
      this.active++;
      this.update(next.id, { status: 'resizing' });
      void this.process(next.id).finally(() => {
        this.active--;
        this.pump();
      });
    }
  }

  private async process(id: string): Promise<void> {
    const file = this.files.get(id) as F;
    let ready = this.prepared.get(id);
    if (!ready) {
      let sha256: string | null;
      try {
        sha256 = (await this.deps.hash?.(file)) ?? null;
      } catch {
        sha256 = null;
      }
      let prepared: { blob: Blob; filename: string };
      try {
        prepared = await this.deps.prepare(file);
      } catch {
        prepared = { blob: file as unknown as Blob, filename: this.deps.nameOf(file) };
      }
      ready = { ...prepared, sha256 };
      this.prepared.set(id, ready);
    }
    const limit = this.deps.autoRetries ?? 3;
    for (;;) {
      const entry = this.entries.find((e) => e.id === id);
      if (!entry) return;
      const attempt = entry.attempts + 1;
      this.update(id, { status: 'uploading', attempts: attempt });
      try {
        const got = await this.deps.upload(ready.blob, ready.filename, entry.clientKey, ready.sha256, entry.several);
        this.update(id, { status: got.duplicate ? 'duplicate' : 'done', itemId: got.id, sourceId: got.sourceId ?? null, error: null });
        this.prepared.delete(id);
        this.files.delete(id);
        return;
      } catch (err) {
        const e = err as UploadErrorLike;
        const message = e?.message || 'The upload did not work.';
        if (isTransient(e) && !this.online) {
          // Closet went out of reach: wait for it to come back instead of using up the retries
          this.update(id, { status: 'waiting', attempts: 0, error: null });
          return;
        }
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
