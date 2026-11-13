import { api } from './api';
import type { FigurePieces } from './today';

/** One mounted figure owns its request and URL; even a late response cannot outlive it. */
export function loadOutfitFigure(pieces: FigurePieces, ready: (url: string) => void, failed: (message: string) => void): () => void {
  const controller = new AbortController();
  let url: string | null = null;
  void api.figure(pieces, controller.signal).then((blob) => {
    if (controller.signal.aborted) return;
    url = URL.createObjectURL(blob);
    ready(url);
  }).catch((error: unknown) => {
    if (controller.signal.aborted) return;
    failed(error instanceof Error ? error.message : "The drawing couldn't be loaded.");
  });
  return () => {
    controller.abort();
    if (url) URL.revokeObjectURL(url);
  };
}
