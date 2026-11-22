import type { ReactNode } from 'react';
import { smallPicture, useShowDrawings } from '../drawing';
import { label } from '../labels';
import { ItemThumb } from './ui/ItemThumb';
import type { ItemSummary } from '../types';
import { HangerIcon } from './Icons';

/** An item's small picture on a card: the cutout, else the drawing, else the photo; the drawing first whenever
 * Settings says to show drawings instead of photos (`smallPicture`). */
export function Pic({ item, alt = itemName(item) }: { item: ItemSummary | undefined; alt?: string }): ReactNode {
  const drawings = useShowDrawings();
  const shown = item ? smallPicture(item, drawings) : 'none';
  if (!item || shown === 'none') return <span className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></span>;
  if (shown === 'drawing') return <img className="pic-illustration" src={item.illustration_url!} alt={alt} />;
  return <img className={shown === 'cutout' ? 'pic-cutout' : 'pic-photo'} src={item.thumb_url!} alt={alt} />;
}

export function itemName(item: ItemSummary | undefined): string {
  if (!item) return 'An item';
  return item.name || label('category', item.category) || 'An item';
}

/** Small pictures of items that open the item in the Wardrobe; `max` shown, then "and N more". */
export function Pieces({ ids, byId, max, label: groupLabel }: { ids: string[]; byId: Map<string, ItemSummary>; max: number; label: string }) {
  const shown = ids.slice(0, max);
  const more = ids.length - shown.length;
  return (
    <ul className="gap-thumbs" aria-label={groupLabel}>
      {shown.map((id) => {
        const item = byId.get(id);
        return (
          <li key={id}>
            <ItemThumb item={item} to={`/wardrobe/item/${encodeURIComponent(id)}`} className="gap-thumb" title={itemName(item)} testId="gap-piece" />
          </li>
        );
      })}
      {more > 0 && <li className="gap-thumb-more muted">and {more} more</li>}
    </ul>
  );
}
