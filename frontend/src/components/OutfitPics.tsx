import { ItemThumb } from './ui';
import { Pic } from './ItemPic';
import { label } from '../labels';
import type { ItemSummary } from '../types';
import { pieceName, wornIds, type WornOutfit } from '../worn';
import './OutfitPics.css';

/** The pieces of a worn outfit, each opening its item unless `linked` is false (a small preview, as on Today's question).
 * `from` is the page it is on, whose own address the item opens at, so the item's back link goes back there ('' for the
 * closet's own item page, from a piece's page there). */
export function OutfitPics({ outfit, byId, linked = true, from = '/today' }: {
  outfit: Pick<WornOutfit, 'pieces' | 'gone'>; byId: Map<string, ItemSummary>; linked?: boolean; from?: string;
}) {
  const ids = wornIds(outfit.pieces);
  return (
    <ul className="worn-pics" aria-label="Pieces">
      {ids.map((id) => {
        const deleted = (outfit.gone ?? []).includes(id);
        const item = byId.get(id);
        const name = nameOf(item, deleted);
        return (
          <li key={id}>
            {deleted || !linked ? (
              <ItemThumb className={`worn-pic${deleted ? ' is-gone' : item?.status === 'archived' ? ' is-archived' : ''}`} title={name}
                picture={<Pic item={deleted ? undefined : item} alt={name} />} />
            ) : (
              <ItemThumb to={item?.status === 'archived' ? `/archived/item/${encodeURIComponent(id)}` : `${from}/item/${encodeURIComponent(id)}`}
                className={`worn-pic${item?.status === 'archived' ? ' is-archived' : ''}`} title={name} picture={<Pic item={item} alt={name} />} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** What a piece of a worn outfit is called (`pieceName`, with the category's plain word). */
export function nameOf(item: ItemSummary | undefined, deleted: boolean): string {
  return pieceName(item, deleted, (c) => label('category', c));
}
