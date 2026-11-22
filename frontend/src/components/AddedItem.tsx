import { useState, type ReactNode } from 'react';
import { rowTitle } from '../progress';
import { useItemProgress } from '../queries';
import { itemPath, Link } from '../router';
import type { ItemSummary, Progress } from '../types';
import { ChevronIcon, ImagesIcon } from './Icons';
import { StepMark } from './Progress';

/** What a row needs of an item: a summary from the closet's list, or an entry of the work under way. */
type RowItem = Pick<ItemSummary, 'id' | 'name' | 'category' | 'color' | 'status' | 'thumb_url'> &
  Partial<Pick<ItemSummary, 'cutout_state' | 'progress'>>;

/** The picture in a row on Add: the item's cut-out once it is ready, else its photo; `fallback` (the photo as chosen,
 *  in this browser) until Nines knows the item. A picture this browser cannot show gives the photo icon. */
export function AddedPicture({ item, fallback }: { item: RowItem | null; fallback?: string }) {
  const [broken, setBroken] = useState<string | null>(null);
  const src = item?.thumb_url || fallback;
  const cutout = !!item?.thumb_url && (item.cutout_state === 'ready' || (!item.cutout_state && (item.progress?.step ?? 1) > 1));
  return (
    <div className="queue-thumb">
      {src && broken !== src
        ? <img className={cutout ? 'is-cutout' : undefined} src={src} alt="" loading="lazy" onError={() => setBroken(src)} />
        : <ImagesIcon />}
    </div>
  );
}

/** What is happening to the item, while there is something to say (with the step's mark), else what it is called. */
export function AddedTitle({ item, progress }: { item: RowItem; progress: Progress | null }) {
  return (
    <span className={`queue-title${progress ? ` is-${progress.state}` : ' is-named'}`}>
      {progress && <StepMark progress={progress} small />}
      <span data-testid="queue-title">{rowTitle(item, progress)}</span>
    </span>
  );
}

/** A row that opens the item a photo became, where it can be fixed: its picture, what it is called (or how far it has
 *  got), and `sub` in small type below. `progress` is the item's when the caller already has it. */
export function AddedRow({ item, progress, fallback, sub, className, testId }: {
  item: RowItem; progress?: Progress | null; fallback?: string; sub?: ReactNode; className?: string; testId: string;
}) {
  const own = useItemProgress(progress === undefined ? item : null);
  const p = progress === undefined ? own : progress;
  return (
    <li className={`queue-row has-item${className ? ` ${className}` : ''}`} data-testid={testId}>
      <Link to={itemPath(item.id, item.status)} className="queue-item" data-testid="queue-item">
        <AddedPicture item={item} fallback={fallback} />
        <span className="queue-info">
          <AddedTitle item={item} progress={p} />
          {sub && <span className="queue-sub">{sub}</span>}
        </span>
        <ChevronIcon className="queue-chevron" />
      </Link>
    </li>
  );
}
