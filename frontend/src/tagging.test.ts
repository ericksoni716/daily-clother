import { describe, expect, it } from 'vitest';
import { describedBy, detailLines, tagNotice } from './tagging';

describe('tagging wording', () => {
  it('says what is happening to the description', () => {
    expect(tagNotice('waiting', null)).toMatch(/^Waiting to be described by Claude/);
    expect(tagNotice('working', null)).toBe('Claude is describing this item…');
    expect(tagNotice('done', 'plan')).toBe("Suggested by Claude; change anything that's wrong.");
    expect(tagNotice('done', 'demo')).toMatch(/in advance for the demo/);
    expect(tagNotice('none', null)).toBeNull();
    expect(tagNotice('failed', null)).toBeNull();   // the failure has its own notice, with the reason
    expect(tagNotice(undefined, null)).toBeNull();
  });

  it('lists the details in plain words and leaves out what does not apply', () => {
    const lines = detailLines({
      fit_detail: 'regular', sleeve_length: 'short', neckline: 'polo_collar', collar: 'flat_knit', placket: 'polo',
      placket_buttons: 3, button_color: 'same', cuff: 'barrel_1', sleeve_construction: 'set_in', pockets: 'none', hem: 'na',
      fabric: 'pique', fiber: 'unknown', weight: 'super_heavy', knit_gauge: 'na', corduroy_wale: 'na', color_texture: 'solid',
      pattern_name: 'solid', pattern_orientation: 'all_over', trim_color: 'white', waist: 'na', pant_hem: 'na', shoe_style: 'na',
      sole_color: 'same', lace_color: 'same', features: ['contrast_stitching', 'v_insert'], other_features: ['embroidered chest logo'],
    });
    expect(lines).toEqual([
      { title: 'Fit', value: 'Regular' },
      { title: 'Sleeves', value: 'Short' },
      { title: 'Neckline', value: 'Polo collar' },
      { title: 'Collar', value: 'Flat knit' },
      { title: 'Front opening', value: 'Polo' },
      { title: 'Buttons on the front', value: '3' },
      { title: 'Cuffs', value: 'One-button barrel' },
      { title: 'Sleeve seams', value: 'Set in' },
      { title: 'Fabric', value: 'Pique' },
      { title: 'Weight', value: 'Very heavy' },
      { title: 'Trim colour', value: 'White' },
      { title: 'Also', value: 'Contrast stitching, V insert under the neck' },
    ]);
    expect(detailLines(null)).toEqual([]);
    expect(detailLines({ placket_buttons: 0, features: [] })).toEqual([]);
  });

  it('says who described it', () => {
    expect(describedBy('plan', null)).toBe('Described with your Claude plan.');
    expect(describedBy('api', null)).toBe('Described with your API key.');
    expect(describedBy('plan', '2026-11-12T10:00:00Z')).toMatch(/^Described with your Claude plan on .*2026\.$/);
    expect(describedBy('demo', '2026-11-12T10:00:00Z')).toBe('');
    expect(describedBy(null, null)).toBe('');
  });
});
