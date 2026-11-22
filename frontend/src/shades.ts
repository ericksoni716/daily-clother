/**
 * Choosing an item's colour on its page: one of the colour words, which outfits, gaps and "Would this work?" reason
 * with, and then, more exactly, one of the owner's named shades of that colour. The shades come from the server
 * (`GET /api/vocab`, from the taxonomy), so the page and the server always agree on them.
 */
import { SWATCH } from './labels';
import type { ItemPatch, NamedShade } from './types';

/** The shades of one colour word, in the taxonomy's order; none for a colour without shades (multicolour), for no
 * colour, or when the shades are not known (a vocabulary saved before there were any). */
export function shadesOf(shades: NamedShade[] | undefined, color: string | null | undefined): NamedShade[] {
  return color ? (shades ?? []).filter((s) => s.color === color) : [];
}

/** What choosing a colour word saves: the word, drawn in its swatch (null clears both). A shade of another colour
 * the owner chose before is put aside by the server. */
export function colourPatch(color: string | null): ItemPatch {
  const swatch = color ? SWATCH[color] : undefined;
  return { color, color_hex: swatch?.startsWith('#') ? swatch : null };
}

/** What choosing a shade saves: the shade, with its colour word and its colour. The server sets those two from the
 * shade as well; sending them shows the choice at once, before it answers. */
export function shadePatch(shade: NamedShade): ItemPatch {
  return { shade: shade.name, color: shade.color, color_hex: shade.hex };
}
