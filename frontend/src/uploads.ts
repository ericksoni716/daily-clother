import { api, connection } from './api';
import { preparePhoto } from './resize';
import { UploadQueue, type SavedEntry } from './uploadQueue';

/** Where the import list is kept, so a closed tab or a restart can be carried on. */
export const SAVED_IMPORT_KEY = 'closet.import';

const store = {
  load(): SavedEntry[] | null {
    const raw = localStorage.getItem(SAVED_IMPORT_KEY);
    return raw ? (JSON.parse(raw) as SavedEntry[]) : null;
  },
  save(entries: SavedEntry[]): void {
    if (entries.length) localStorage.setItem(SAVED_IMPORT_KEY, JSON.stringify(entries));
    else localStorage.removeItem(SAVED_IMPORT_KEY);
  },
};

/** SHA-256 of the file as chosen, before it is shrunk; null where the browser cannot work it out. */
async function sha256(file: File): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** The one upload queue for the page; it keeps going while the owner looks at other screens. */
export const uploads = new UploadQueue<File>({
  prepare: preparePhoto,
  upload: (blob, filename, key, hash) => api.upload(blob, filename, key, hash),
  newKey: () => (typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : fallbackUuid()),
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  nameOf: (f) => f.webkitRelativePath || f.name || 'Photo',
  keyOf: (f) => `${f.name}|${f.size}|${f.lastModified}`,
  hash: sha256,
  store,
});
uploads.setOnline(!connection.offline);
connection.subscribe((off) => uploads.setOnline(!off));

/** Small preview pictures for the queue rows. */
const previews = new Map<string, string>();
/** Queues photos; returns how many were already in the list and left out. */
export function addFiles(files: File[]): number {
  const { ids, files: queued, skipped } = uploads.add(files);
  ids.forEach((id, i) => {
    const old = previews.get(id);
    if (old) URL.revokeObjectURL(old);
    previews.set(id, URL.createObjectURL(queued[i]));
  });
  return skipped;
}
export function previewOf(id: string): string | undefined {
  return previews.get(id);
}
function dropPreviews(run: () => void): void {
  const before = new Set(uploads.snapshot.map((e) => e.id));
  run();
  const after = new Set(uploads.snapshot.map((e) => e.id));
  for (const id of before) if (!after.has(id)) {
    const url = previews.get(id);
    if (url) URL.revokeObjectURL(url);
    previews.delete(id);
  }
}
export function clearFinished(): void {
  dropPreviews(() => uploads.clearFinished());
}
export function cancelImport(): void {
  dropPreviews(() => uploads.cancel());
}

function fallbackUuid(): string {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
