import { describe, expect, it } from 'vitest';
import { splitPhotos } from './resize';

describe('splitPhotos', () => {
  it('keeps photos and skips everything else, hidden files included', () => {
    const f = (name: string, type = '') => ({ name, type });
    const { photos, skipped } = splitPhotos([
      f('shirt.jpg', 'image/jpeg'), f('IMG_0001.HEIC'), f('notes.txt', 'text/plain'), f('.DS_Store'),
      f('._shirt.jpg', 'image/jpeg'), f('clip.mov', 'video/quicktime'), f('scan.png', 'image/png'),
    ]);
    expect(photos.map((p) => p.name)).toEqual(['shirt.jpg', 'IMG_0001.HEIC', 'scan.png']);
    expect(skipped.map((p) => p.name)).toEqual(['notes.txt', '.DS_Store', '._shirt.jpg', 'clip.mov']);
  });
});
