import { useState, type ReactNode } from 'react';
import { addedLine, addedState } from '../added';
import { itemPath, Link } from '../router';
import { useModel } from '../queries';
import type { ItemSummary } from '../types';
import { busyLabel } from '../screens/Closet';
import { ChevronIcon, ImagesIcon, WarnIcon } from './Icons';

/** The picture in a row on Add: the item's cut-out once it is ready, else its photo; `fallback` (the photo as chosen,
 *  in this browser) until Closet knows the item. A picture this browser cannot show gives the photo icon. */
export function AddedPicture({ item, fallback }: { item: ItemSummary | null; fallback?: string }) {
  const [broken, setBroken] = useState<string | null>(null);
  const src = item?.thumb_url || fallback;
  const cutout = item?.cutout_state === 'ready' && !!item.thumb_url;
  return (
    <div className="queue-thumb">
      {src && broken !== src
        ? <img className={cutout ? 'is-cutout' : undefined} src={src} alt="" loading="lazy" onError={() => setBroken(src)} />
        : <ImagesIcon />}
    </div>
  );
}

/** What the item is called once Claude has described it, or how far it has got, in the item page's words. */
export function AddedTitle({ item }: { item: ItemSummary }) {
  const model = useModel();
  const state = addedState(item);
  return (
    <span className={`queue-title is-${state}`} data-testid="queue-title">
      {(state === 'removing' || state === 'describing') && <span className="spinner" aria-hidden="true" />}
      {(state === 'failed' || state === 'cutout-failed') && <WarnIcon />}
      <span>{addedLine(item, busyLabel(model))}</span>
    </span>
  );
}

/** A row that opens the item a photo became, where it can be fixed: its picture, what it is called (or how far it has
 *  got), and `sub` in small type below. */
export function AddedRow({ item, fallback, sub, className, testId }: {
  item: ItemSummary; fallback?: string; sub?: ReactNode; className?: string; testId: string;
}) {
  return (
    <li className={`queue-row has-item${className ? ` ${className}` : ''}`} data-testid={testId}>
      <Link to={itemPath(item.id, item.status)} className="queue-item" data-testid="queue-item">
        <AddedPicture item={item} fallback={fallback} />
        <span className="queue-info">
          <AddedTitle item={item} />
          {sub && <span className="queue-sub">{sub}</span>}
        </span>
        <ChevronIcon className="queue-chevron" />
      </Link>
    </li>
  );
}
