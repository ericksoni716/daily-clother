/** Plain words for an item being described by Claude, and for what Claude saw. */
import { humanize } from './labels';
import type { TagState } from './types';

/** What the item page says about describing the item, or null when there is nothing to say.
 *  `error`, while it waits, is why it can't go yet (the API key's monthly limit was reached). */
export function tagNotice(state: TagState | undefined, route: string | null, error: string | null = null): string | null {
  switch (state) {
    case 'waiting':
      if (error) return `Waiting to be described by Claude. ${error}`;
      return 'Waiting to be described by Claude. It starts by itself once Claude can be reached.';
    case 'working':
      return 'Claude is describing this item…';
    case 'done':
      return route === 'demo'
        ? 'Described in advance for the demo; change anything you like.'
        : "Suggested by Claude; change anything that's wrong.";
    default:
      return null;
  }
}

const TITLES: Record<string, string> = {
  garment: 'Kind',
  fit_detail: 'Fit',
  sleeve_length: 'Sleeves',
  neckline: 'Neckline',
  collar: 'Collar',
  placket: 'Front opening',
  placket_buttons: 'Buttons on the front',
  button_color: 'Button colour',
  cuff: 'Cuffs',
  sleeve_construction: 'Sleeve seams',
  pockets: 'Pockets',
  hem: 'Hem',
  fabric: 'Fabric',
  fiber: 'Fibre',
  weight: 'Weight',
  knit_gauge: 'Knit',
  corduroy_wale: 'Corduroy ridges',
  color_texture: 'Colour',
  pattern_name: 'Pattern',
  pattern_orientation: 'Pattern direction',
  trim_color: 'Trim colour',
  waist: 'Waist',
  pant_hem: 'Trouser hem',
  shoe_style: 'Shoe style',
  sole_color: 'Sole colour',
  lace_color: 'Lace colour',
  footwear: 'Kind of shoe',
  footwear_height: 'Height',
  toe_shape: 'Toe shape',
  toe_treatment: 'Toe',
  lacing: 'Fastening',
  eyelets: 'Eyelets',
  laces: 'Laces',
  sole: 'Sole',
  heel: 'Heel',
  shoe_construction: 'Sole attached by',
  upper_material: 'Upper',
  waistband: 'Waistband',
  fly: 'Fly',
  trouser_front: 'Front',
  rise: 'Rise',
  leg_shape: 'Leg',
  trouser_break: 'Break',
  hem_finish: 'Hem finish',
  crease: 'Crease',
  trouser_pockets: 'Pockets',
  back_details: 'Back and build',
  denim_wash: 'Wash',
  denim_fades: 'Fades',
  distressing: 'Wear and repairs',
  inseam: 'Inseam (inches)',
  shade: 'Shade',
  features: 'Also',
};

const WORDS: Record<string, string> = {
  barrel_1: 'one-button barrel',
  barrel_2: 'two-button barrel',
  set_in: 'set in',
  five_pocket_jean: 'five-pocket jean',
  turn_up: 'turned up',
  v_insert: 'V insert under the neck',
  super_heavy: 'very heavy',
  lug_commando: 'lug (commando)',
  eva_foam_midsole: 'foam midsole',
  boot_6in: '6-inch boot',
  boot_8in_plus: '8 inches or taller',
  no_break: 'no break',
  single_pleat: 'one pleat',
  double_pleat: 'two pleats',
  t_shirt: 'T-shirt',
  ocbd: 'oxford button-down',
  two_in_one_shorts: 'two-in-one shorts',
  open_hem_sweatpants: 'open-hem sweatpants',
};

/** Values that say only "nothing to see here". */
const NOTHING = new Set(['na', 'none', 'same', 'unknown']);
/** Values that are simply the usual, for the fields where that is not worth a line. */
const USUAL: Record<string, string> = { color_texture: 'solid', pattern_name: 'solid', pattern_orientation: 'all_over' };

function words(value: string): string {
  return WORDS[value] ?? value.replace(/_/g, ' ');
}

/** The stored construction details as plain lines, e.g. {title: "Collar", value: "Button down"}; skips what does not apply. */
export function detailLines(details: Record<string, unknown> | null | undefined): { title: string; value: string }[] {
  if (!details) return [];
  const out: { title: string; value: string }[] = [];
  for (const [key, title] of Object.entries(TITLES)) {
    const v = details[key];
    if (Array.isArray(v)) {
      const list = v.filter((x): x is string => typeof x === 'string' && x !== '').map(words);
      if (list.length) out.push({ title, value: humanize(list.join(', ')) });
    } else if (typeof v === 'number') {
      if (v > 0) out.push({ title, value: String(v) });
    } else if (typeof v === 'string' && v && !NOTHING.has(v) && USUAL[key] !== v) {
      out.push({ title, value: humanize(words(v)) });
    }
  }
  return out;
}

/** "Described with your Claude plan, 12 Nov 2026" and the like; empty when it has not been described. */
export function describedBy(route: string | null, at: string | null): string {
  if (!route || route === 'demo') return '';
  const how = route === 'api' ? 'with your API key' : route === 'plan' ? 'with your Claude plan' : '';
  const when = at ? new Date(at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  return ['Described', how, when && `on ${when}`].filter(Boolean).join(' ') + '.';
}
