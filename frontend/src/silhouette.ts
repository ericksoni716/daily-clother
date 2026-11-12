/** Which silhouette questions make sense for a category. */

const TOPS = new Set(['tee', 'shirt', 'polo', 'sweater', 'hoodie', 'jacket', 'coat']);
const BOTTOMS = new Set(['trousers', 'jeans', 'shorts']);
const SHOES = new Set(['sneakers', 'boots', 'dress_shoes', 'sandals']);

export function silhouetteGroups(category: string | null | undefined): string[] {
  if (!category) return [];
  if (TOPS.has(category)) return ['sleeve', 'neck', 'top_length', 'fit'];
  if (BOTTOMS.has(category)) return ['leg', 'pant_length'];
  if (SHOES.has(category)) return ['shoe_height'];
  return [];
}
