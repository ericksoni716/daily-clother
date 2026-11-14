import { describe, expect, it } from 'vitest';
import { categoryPlural, formatPrice, formatSize, humanize, label, measuredColours, parsePrice, ratingLabel, shadeLabel, tileCaption } from './labels';
import { messageFrom } from './api';
import { fitWithin } from './resize';
import { silhouetteGroups } from './silhouette';

describe('labels', () => {
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

  it("names the owner's shade beside the colour", () => {
    expect(shadeLabel('Grey', 'charcoal')).toBe('Grey (charcoal)');
    expect(shadeLabel('Navy', 'raw_indigo')).toBe('Navy (raw indigo)');
    expect(shadeLabel('Navy', 'navy')).toBe('Navy');
    expect(shadeLabel('Navy', null)).toBe('Navy');
  });

  it('never shows raw field names or underscores for any known value', () => {
    const values = ['smart_casual', 'light_blue', 'dress_shoes', 'needs_repair', 'top_length', 'pant_length', 'shoe_height'];
    for (const v of values) expect(label('x', v)).not.toMatch(/_/);
  });

  it('the colours measured from a pattern, in words', () => {
    expect(measuredColours([{ color: 'navy', share: 0.6 }, { color: 'light_blue', share: 0.3 }, { color: 'red', share: 0.1 }]))
      .toBe('Navy 60%, light blue 30%, red 10%');
    expect(measuredColours([])).toBe('');
    expect(measuredColours(undefined)).toBe('');
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

describe('formatSize', () => {
  it('shows sizes in plain units', () => {
    expect(formatSize(0)).toBe('0 KB');
    expect(formatSize(null)).toBe('0 KB');
    expect(formatSize(512)).toBe('512 bytes');
    expect(formatSize(1000)).toBe('1 KB');
    expect(formatSize(4_200)).toBe('4.2 KB');
    expect(formatSize(38_400_000)).toBe('38 MB');
    expect(formatSize(1_500_000_000)).toBe('1.5 GB');
    expect(formatSize(2_000_000_000_000)).toBe('2 TB');
  });

  it('moves to the next unit instead of showing 1000', () => {
    expect(formatSize(999_999)).toBe('1 MB');
    expect(formatSize(999_499)).toBe('999 KB');
    expect(formatSize(9_960)).toBe('10 KB');
  });
});
