import { api } from './api';
import { preparePhoto } from './resize';
import { UploadQueue } from './uploadQueue';

/** The one upload queue for the page; it keeps going while the owner looks at other screens. */
export const uploads = new UploadQueue<File>({
  prepare: preparePhoto,
  upload: (blob, filename, key) => api.upload(blob, filename, key),
  newKey: () => (typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : fallbackUuid()),
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  nameOf: (f) => f.name || 'Photo',
});

/** Small preview pictures for the queue rows. */
const previews = new Map<string, string>();
export function addFiles(files: File[]): void {
  const ids = uploads.add(files);
  ids.forEach((id, i) => previews.set(id, URL.createObjectURL(files[i])));
}
export function previewOf(id: string): string | undefined {
  return previews.get(id);
}
export function clearFinished(): void {
  const before = new Set(uploads.snapshot.map((e) => e.id));
  uploads.clearFinished();
  const after = new Set(uploads.snapshot.map((e) => e.id));
  for (const id of before) if (!after.has(id)) {
    const url = previews.get(id);
    if (url) URL.revokeObjectURL(url);
    previews.delete(id);
  }
}

function fallbackUuid(): string {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
