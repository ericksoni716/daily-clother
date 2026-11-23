/** Your sizes (Settings, Everyday): the words of the row and of its sheet. The sizes themselves are kept by the server
 * (`sizes.py`), which also works out the size most common on your own items while none is saved. */
import type { SizeEntry, SizeKind, Sizes } from './types';

/** Each kind in a word, for the row's one line ("M tops · 32x32 trousers"). */
export const SIZE_WORDS: Record<SizeKind, string> = {
  tops: 'tops', knitwear: 'knitwear', trousers: 'trousers', jackets: 'jackets', shoes: 'shoes',
};

/** The row's line: the sizes you saved, each with its kind ("Your sizes: M tops · 32x32 trousers"), or that none is
 * saved yet. A suggestion is not a size until you save it. */
export function sizesLine(sizes: Sizes | undefined): string {
  const saved = (sizes?.kinds ?? []).filter((k) => k.size);
  if (!saved.length) return 'Your sizes are not saved yet.';
  return `Your sizes: ${saved.map((k) => `${k.size} ${SIZE_WORDS[k.kind]}`).join(' · ')}`;
}

/** Under an empty box: the size most of your own pieces of that kind carry, to confirm with a tap; null when there is
 * none to offer or a size is saved. */
export function suggestionLine(entry: SizeEntry): string | null {
  if (entry.size || !entry.suggested) return null;
  return `The size on most of your ${entry.label.toLowerCase()} is ${entry.suggested}.`;
}

/** A brand that fits differently, as its line under the kind: "In Example Brand, L". */
export function brandLine(b: { brand: string; size: string }): string {
  return `In ${b.brand}, ${b.size}`;
}
