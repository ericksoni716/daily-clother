import type { ReactNode } from 'react';
import { label } from '../labels';
import { ItemThumb } from './ui/ItemThumb';
import type { ItemSummary } from '../types';
import { HangerIcon } from './Icons';

/** An item's small picture, as the closet grid shows it: the cutout, else the drawing, else the photo. */
export function Pic({ item }: { item: ItemSummary | undefined }): ReactNode {
  const alt = itemName(item);
  if (!item) return <span className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></span>;
  if (item.cutout_state === 'ready' && item.thumb_url) return <img className="pic-cutout" src={item.thumb_url} alt={alt} />;
  if (item.illustration_url) return <img className="pic-illustration" src={item.illustration_url} alt={alt} />;
  if (item.thumb_url) return <img className="pic-photo" src={item.thumb_url} alt={alt} />;
  return <span className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></span>;
}

export function itemName(item: ItemSummary | undefined): string {
  if (!item) return 'An item';
  return item.name || label('category', item.category) || 'An item';
}

/** Small pictures of items that open the item on the What's missing screen; `max` shown, then "and N more". */
export function Pieces({ ids, byId, max, label: groupLabel }: { ids: string[]; byId: Map<string, ItemSummary>; max: number; label: string }) {
  const shown = ids.slice(0, max);
  const more = ids.length - shown.length;
  return (
    <ul className="gap-thumbs" aria-label={groupLabel}>
      {shown.map((id) => {
        const item = byId.get(id);
        return (
          <li key={id}>
            <ItemThumb item={item} to={`/missing/item/${encodeURIComponent(id)}`} className="gap-thumb" title={itemName(item)} testId="gap-piece" />
          </li>
        );
      })}
      {more > 0 && <li className="gap-thumb-more muted">and {more} more</li>}
    </ul>
  );
}
