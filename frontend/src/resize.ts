export const MAX_EDGE = 2400;
export const JPEG_QUALITY = 0.9;

/** Size that fits within maxEdge on the long side, keeping the shape. */
export function fitWithin(width: number, height: number, maxEdge = MAX_EDGE): { width: number; height: number } {
  const long = Math.max(width, height);
  if (long <= maxEdge) return { width, height };
  const scale = maxEdge / long;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

function jpegName(name: string): string {
  const base = name.replace(/\.[^.]+$/, '') || 'photo';
  return `${base}.jpg`;
}

/**
 * Shrinks a photo to at most 2400px on the long edge and re-encodes it as JPEG.
 * If this browser cannot read the file (HEIC on desktop Chrome, say), the original goes up unchanged.
 */
export async function preparePhoto(file: File): Promise<{ blob: Blob; filename: string }> {
  const original = { blob: file as Blob, filename: file.name || 'photo' };
  if (typeof createImageBitmap !== 'function') return original;
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    return original;
  }
  try {
    const { width, height } = fitWithin(bitmap.width, bitmap.height);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return original;
    ctx.fillStyle = '#ffffff'; // JPEG has no transparency
    ctx.fillRect(0, 0, width, height);
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(bitmap, 0, 0, width, height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
    if (!blob) return original;
    return { blob, filename: jpegName(file.name || 'photo') };
  } finally {
    bitmap.close();
  }
}

const IMAGE_EXT = /\.(jpe?g|png|webp|heic|heif|gif|bmp|tiff?|avif)$/i;

export function looksLikePhoto(file: File): boolean {
  return file.type.startsWith('image/') || IMAGE_EXT.test(file.name);
}

/** Files from a drop, walking into dropped folders. */
export async function filesFromDrop(dt: DataTransfer): Promise<File[]> {
  const entries: FileSystemEntry[] = [];
  for (const item of Array.from(dt.items ?? [])) {
    const entry = item.kind === 'file' && typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null;
    if (entry) entries.push(entry);
  }
  if (!entries.length) return Array.from(dt.files ?? []);
  const out: File[] = [];
  const walk = async (entry: FileSystemEntry, inFolder: boolean): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File | null>((res) => (entry as FileSystemFileEntry).file(res, () => res(null)));
      // inside a dropped folder, skip things that are clearly not photos (.DS_Store, notes…)
      if (file && (!inFolder || looksLikePhoto(file))) out.push(file);
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((res) => reader.readEntries(res, () => res([])));
        if (!batch.length) break;
        for (const child of batch) await walk(child, true);
      }
    }
  };
  for (const e of entries) await walk(e, false);
  return out;
}
