import jsQR from 'jsqr';
import { describe, expect, it } from 'vitest';
import { QUIET, qrMatrix, qrPath } from './qr';

/** Draws the code black on white with its quiet zone, as the page does, and reads it back like a camera. */
function read(matrix: boolean[][], scale = 4): string | undefined {
  const side = (matrix.length + 2 * QUIET) * scale;
  const pixels = new Uint8ClampedArray(side * side * 4).fill(255);
  matrix.forEach((row, r) => row.forEach((dark, c) => {
    if (!dark) return;
    for (let y = 0; y < scale; y++) {
      for (let x = 0; x < scale; x++) {
        const i = (((r + QUIET) * scale + y) * side + (c + QUIET) * scale + x) * 4;
        pixels[i] = pixels[i + 1] = pixels[i + 2] = 0;
      }
    }
  }));
  return jsQR(pixels, side, side)?.data;
}

describe('the phone address as a QR code', () => {
  it.each([
    'https://closet-pc.example-tailnet.ts.net',
    'https://closet-pc.example-tailnet.ts.net:8443',
    'https://a-much-longer-computer-name.another-example-tailnet.ts.net:10001',
  ])('encodes exactly %s', (address) => {
    expect(read(qrMatrix(address))).toBe(address);
  });

  it('draws one square per dark module, inside the quiet zone', () => {
    const matrix = qrMatrix('https://closet-pc.example-tailnet.ts.net:8443');
    const dark = matrix.flat().filter(Boolean).length;
    const path = qrPath(matrix);
    expect(path.match(/M/g)).toHaveLength(dark);
    expect(path.startsWith(`M${QUIET} ${QUIET}`)).toBe(true);
  });
});
