import qrcode from 'qrcode-generator';

/** Blank modules kept around the code: the four the QR standard asks for, so a camera finds its edges. */
export const QUIET = 4;

/** The QR code of `text`, made here in the page (the address is private: no outside service), as rows of dark modules. */
export function qrMatrix(text: string): boolean[][] {
  const qr = qrcode(0, 'M');
  qr.addData(text, 'Byte');
  qr.make();
  const n = qr.getModuleCount();
  return Array.from({ length: n }, (_, r) => Array.from({ length: n }, (_, c) => qr.isDark(r, c)));
}

/** One SVG path drawing every dark module, in a square of `size + 2 * QUIET` units. */
export function qrPath(matrix: boolean[][]): string {
  const parts: string[] = [];
  matrix.forEach((row, r) => row.forEach((dark, c) => {
    if (dark) parts.push(`M${c + QUIET} ${r + QUIET}h1v1h-1z`);
  }));
  return parts.join('');
}
