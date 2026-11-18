import { describe, expect, it } from 'vitest';
import { STYLE_WARN_WITHIN, styleChanged, styleCount, tidyStyle } from './style';

describe('the style profile being written', () => {
  it('is tidied as the server keeps it, with the line breaks kept', () => {
    expect(tidyStyle('  I run warm.\r\n\r\nNo ties.\rNavy with brown.\n ')).toBe('I run warm.\n\nNo ties.\nNavy with brown.');
  });

  it('is a change only when the tidied text differs from the one in force', () => {
    expect(styleChanged('No ties.', 'No ties.')).toBe(false);
    expect(styleChanged('No ties.  \n', 'No ties.')).toBe(false);
    expect(styleChanged('No ties!', 'No ties.')).toBe(true);
    expect(styleChanged('', 'No ties.')).toBe(true);
  });

  it('counts its characters and warns in the last 200', () => {
    expect(styleCount(123, 4000)).toEqual({ text: '123 / 4000', warn: false });
    expect(styleCount(4000 - STYLE_WARN_WITHIN, 4000).warn).toBe(false);
    expect(styleCount(4000 - STYLE_WARN_WITHIN + 1, 4000)).toEqual({ text: '3801 / 4000', warn: true });
    expect(styleCount(4000, 4000).warn).toBe(true);
  });
});
