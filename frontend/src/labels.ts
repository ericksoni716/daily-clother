/** Plain-language words for the vocabulary the server uses. */

const SPECIAL: Record<string, Record<string, string>> = {
  category: { tee: 'T-shirt', dress_shoes: 'Dress shoes', other: 'Other' },
  color: { multi: 'Multicolour', grey: 'Grey' },
  season: { warm: 'Warm weather', cool: 'Cool weather', all: 'All year' },
  location: { closet: 'Closet', drawer: 'Drawer', laundry: 'In the laundry', storage: 'In storage' },
  condition: { needs_repair: 'Needs repair' },
  sleeve: { none: 'Sleeveless', short: 'Short sleeves', long: 'Long sleeves' },
  neck: { crew: 'Crew neck', v: 'V-neck', collar: 'Collar', hood: 'Hood', turtle: 'Turtleneck' },
  top_length: { cropped: 'Cropped', regular: 'Regular', long: 'Long' },
  pant_length: { short: 'Short', ankle: 'Ankle', full: 'Full length' },
  shoe_height: { low: 'Low', high: 'High' },
};

const PLURAL: Record<string, string> = {
  tee: 'T-shirts', shirt: 'Shirts', polo: 'Polos', sweater: 'Sweaters', hoodie: 'Hoodies', jacket: 'Jackets',
  coat: 'Coats', jeans: 'Jeans', trousers: 'Trousers', shorts: 'Shorts', sneakers: 'Sneakers', boots: 'Boots',
  dress_shoes: 'Dress shoes', sandals: 'Sandals', bag: 'Bags', belt: 'Belts', hat: 'Hats', scarf: 'Scarves',
  other: 'Other',
};

/** "smart_casual" -> "Smart casual". */
export function humanize(value: string): string {
  const words = value.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The label for a value of a field (field is a vocab key or a silhouette key). */
export function label(field: string, value: string | null | undefined): string {
  if (!value) return '';
  return SPECIAL[field]?.[value] ?? humanize(value);
}

/** Category name for filter chips, e.g. "Sweaters". */
export function categoryPlural(value: string): string {
  return PLURAL[value] ?? humanize(value);
}

export const FIELD_TITLES: Record<string, string> = {
  category: 'Category',
  color: 'Colour',
  pattern: 'Pattern',
  formality: 'Formality',
  season: 'Season',
  location: 'Where it lives',
  condition: 'Condition',
  rating: 'How you feel about it',
  sleeve: 'Sleeves',
  neck: 'Neckline',
  top_length: 'Length',
  fit: 'Fit',
  leg: 'Leg',
  pant_length: 'Length',
  shoe_height: 'Height',
};

/** Swatch colours for the colour chips (the item's own color_hex wins where shown). */
export const SWATCH: Record<string, string> = {
  black: '#1f1f1f', white: '#fbfaf7', grey: '#8f8f8c', navy: '#27344f', blue: '#3c69b0', light_blue: '#9cc3e6',
  green: '#3f7a4c', olive: '#6b6a3a', tan: '#c9a97c', brown: '#6e4a2f', cream: '#eee3c8', red: '#b8322e',
  burgundy: '#6d1f2c', pink: '#e6a1b3', orange: '#e07b2e', yellow: '#e9c547', purple: '#6d4c8f',
  multi: 'conic-gradient(#b8322e, #e9c547, #3f7a4c, #3c69b0, #6d4c8f, #b8322e)',
};

/** The swatch colour for a garment colour, grey for one without a swatch. */
export function swatchOf(color: string): string {
  return SWATCH[color] ?? '#cccccc';
}

const RATING_WORDS: Record<string, string> = { love: 'Love', like: 'Like', meh: 'Meh', dislike: 'Dislike' };
export function ratingLabel(value: string): string {
  return RATING_WORDS[value] ?? humanize(value);
}

/** Short description under a tile: "Sweater · Navy". */
export function tileCaption(category: string | null, color: string | null): string {
  return [label('category', category), label('color', color)].filter(Boolean).join(' · ');
}

/** "$12.50" from 1250; empty for null. */
export function formatPrice(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '';
  const dollars = cents / 100;
  return Number.isInteger(dollars) ? String(dollars) : dollars.toFixed(2);
}

/** Cents from what the owner typed ("12", "$12.50", "1,200"). undefined if it is not a price. */
export function parsePrice(text: string): number | null | undefined {
  const cleaned = text.replace(/[$,\s]/g, '');
  if (!cleaned) return null;
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return undefined;
  return Math.round(parseFloat(cleaned) * 100);
}

/** "12 Nov 2026, 14:05" in the viewer's locale. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const SIZE_UNITS = ['KB', 'MB', 'GB', 'TB'];

/** A size in words: "512 bytes", "4.2 KB", "38 MB", "1.5 GB" (1 KB = 1000 bytes). */
export function formatSize(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n) || n <= 0) return '0 KB';
  if (n < 1000) return `${Math.round(n)} bytes`;
  const shown = (v: number) => (v < 9.95 ? v.toFixed(1) : v.toFixed(0)).replace(/\.0$/, '');
  let value = n / 1000;
  let unit = 0;
  while (unit < SIZE_UNITS.length - 1 && Number(shown(value)) >= 1000) {
    value /= 1000;
    unit += 1;
  }
  return `${shown(value)} ${SIZE_UNITS[unit]}`;
}

/** "12.3 MB" */
export function formatBytes(n: number | null | undefined): string {
  if (!n) return '0 MB';
  return `${(n / 1_000_000).toFixed(n < 10_000_000 ? 1 : 0)} MB`;
}
