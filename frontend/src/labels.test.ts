import { describe, expect, it } from 'vitest';
import { categoryPlural, formatBytes, formatPrice, humanize, label, parsePrice, ratingLabel, tileCaption } from './labels';
import { messageFrom } from './api';
import { fitWithin } from './resize';
import { silhouetteGroups } from './silhouette';

describe('labels', () => {
  it.each([
    [null, '0 B'], [undefined, '0 B'], [0, '0 B'], [1, '1 B'], [999, '999 B'],
    [1000, '1 KB'], [1500, '1.5 KB'], [1_000_000, '1 MB'], [12_345_678, '12.3 MB'],
    [1_000_000_000, '1 GB'], [1_500_000_000, '1.5 GB'], [1_000_000_000_000, '1 TB'],
  ])('formats %s bytes as %s', (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });

  it('turns vocabulary values into plain words', () => {
    expect(label('formality', 'smart_casual')).toBe('Smart casual');
    expect(label('color', 'light_blue')).toBe('Light blue');
    expect(label('category', 'dress_shoes')).toBe('Dress shoes');
    expect(label('category', 'tee')).toBe('T-shirt');
    expect(label('condition', 'needs_repair')).toBe('Needs repair');
    expect(label('neck', 'v')).toBe('V-neck');
    expect(label('sleeve', 'none')).toBe('Sleeveless');
    expect(label('season', 'all')).toBe('All year');
    expect(label('color', 'multi')).toBe('Multicolour');
    expect(label('color', null)).toBe('');
    expect(humanize('some_new_value')).toBe('Some new value');
  });

  it('never shows raw field names or underscores for any known value', () => {
    const values = ['smart_casual', 'light_blue', 'dress_shoes', 'needs_repair', 'top_length', 'pant_length', 'shoe_height'];
    for (const v of values) expect(label('x', v)).not.toMatch(/_/);
  });

  it('plural categories for filter chips', () => {
    expect(categoryPlural('tee')).toBe('T-shirts');
    expect(categoryPlural('scarf')).toBe('Scarves');
    expect(categoryPlural('jeans')).toBe('Jeans');
  });

  it('ratings and captions', () => {
    expect(ratingLabel('meh')).toBe('Meh');
    expect(tileCaption('sweater', 'navy')).toBe('Sweater · Navy');
    expect(tileCaption(null, 'navy')).toBe('Navy');
    expect(tileCaption(null, null)).toBe('');
  });

  it('prices are shown in dollars and stored in cents', () => {
    expect(formatPrice(4500)).toBe('45');
    expect(formatPrice(4550)).toBe('45.50');
    expect(formatPrice(null)).toBe('');
    expect(parsePrice('45')).toBe(4500);
    expect(parsePrice('$45.5')).toBe(4550);
    expect(parsePrice('1,200.99')).toBe(120099);
    expect(parsePrice('')).toBeNull();
    expect(parsePrice('forty')).toBeUndefined();
    expect(parsePrice('1.234')).toBeUndefined();
  });

  it('reads server error messages, including validation lists', () => {
    expect(messageFrom({ detail: 'That passphrase is not right.' }, 'x')).toBe('That passphrase is not right.');
    expect(messageFrom({ detail: [{ msg: 'Field required' }] }, 'x')).toBe('Field required');
    expect(messageFrom(null, 'fallback')).toBe('fallback');
  });
});

describe('silhouette groups', () => {
  it('tops get sleeve, neck, length and fit', () => {
    for (const c of ['tee', 'shirt', 'polo', 'sweater', 'hoodie', 'jacket', 'coat']) {
      expect(silhouetteGroups(c)).toEqual(['sleeve', 'neck', 'top_length', 'fit']);
    }
  });
  it('trousers, jeans and shorts get leg and length', () => {
    for (const c of ['trousers', 'jeans', 'shorts']) expect(silhouetteGroups(c)).toEqual(['leg', 'pant_length']);
  });
  it('shoes get height', () => {
    for (const c of ['sneakers', 'boots', 'dress_shoes', 'sandals']) expect(silhouetteGroups(c)).toEqual(['shoe_height']);
  });
  it('everything else gets none', () => {
    for (const c of ['bag', 'belt', 'hat', 'scarf', 'other', null, undefined]) expect(silhouetteGroups(c)).toEqual([]);
  });
});

describe('resizing', () => {
  it('fits the long edge within 2400px and keeps the shape', () => {
    expect(fitWithin(4032, 3024)).toEqual({ width: 2400, height: 1800 });
    expect(fitWithin(3024, 4032)).toEqual({ width: 1800, height: 2400 });
    expect(fitWithin(1200, 800)).toEqual({ width: 1200, height: 800 });
  });
});
