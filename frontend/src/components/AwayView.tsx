import { useState } from 'react';
import { api, ApiError } from '../api';
import { awayOrder, keptOrder, overdue, PLACE_WORDS, tileMarkLabel, whenBack } from '../away';
import { label } from '../labels';
import { itemPath, Link } from '../router';
import type { Item, ItemSummary } from '../types';
import { localDay } from '../wears';
import { AwayIcon } from './Icons';
import './Where.css';

/** The small quiet mark on a tile in the full grid for a piece away, the way a piece being worked on has one. */
export function AwayMark({ item }: { item: ItemSummary }) {
  if (!item.away) return null;
  return <span className="away-mark" role="img" aria-label={tileMarkLabel(item.away)} data-testid="away-mark"><AwayIcon /></span>;
}

/**
 * The closet's away view: each piece away with where it is and when it is expected, the soonest first, and "It's back"
 * one tap each. A piece brought back stays in its row, saying so with Undo, until the view is left: no row moves while
 * you are in it (`keptOrder`), and the order is made again when the view is next opened. The whole row opens the piece.
 * `returned` holds the pieces brought back here (kept by the closet while the view is on); `saved` writes an answer in.
 */
export function AwayView({ pieces, returned, offline, onReturned, saved, failed }: {
  pieces: ItemSummary[];
  returned: Set<string>;
  offline: boolean;
  onReturned(id: string, back: boolean): void;
  saved(item: Item): void;
  failed(message: string): void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  // a row answered here keeps the height it had, so a shorter sentence ("Back in your closet") moves no row under it
  const [heights, setHeights] = useState<Record<string, number>>({});
  const today = localDay();
  const away = awayOrder(pieces.filter((it) => it.away));
  const back = pieces.filter((it) => !it.away && returned.has(it.id));
  // the order the rows were first shown in, kept while the view is on (set while drawing: used before anything shows)
  const [shown, setShown] = useState<string[]>([]);
  const rows = keptOrder(shown, [...away, ...back]);
  const ids = rows.map((it) => it.id).join(' ');
  if (ids !== shown.join(' ')) setShown(rows.map((it) => it.id));
  const act = async (it: ItemSummary, call: () => Promise<Item>, isBack: boolean, row: HTMLElement | null) => {
    const height = row?.getBoundingClientRect().height;
    if (height && !heights[it.id]) setHeights((h) => ({ ...h, [it.id]: height }));
    setBusy(it.id);
    try {
      saved(await call());
      onReturned(it.id, isBack);
    } catch (e) {
      failed((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };
  const title = offline ? "You're offline" : undefined;
  return (
    <ul className="away-list" aria-label="Away" data-testid="away-view">
      {rows.map((it) => {
        const name = it.name || label('category', it.category) || 'Item';
        return (
          <li key={it.id} className="away-row" data-testid="away-row" style={heights[it.id] ? { minHeight: heights[it.id] } : undefined}>
            <span className="away-pic" aria-hidden="true">
              {it.thumb_url ? <img src={it.thumb_url} alt="" loading="lazy" /> : it.illustration_url ? <img src={it.illustration_url} alt="" loading="lazy" /> : null}
            </span>
            <div className="away-text">
              {/* its tap area is the whole row (Where.css), the button beside it keeping its own */}
              <Link to={itemPath(it.id, 'active')} className="away-name">{name}</Link>
              {it.away ? (
                <>
                  <span className="away-where">{PLACE_WORDS[it.away.place]}</span>
                  <span className={`away-when${overdue(it.away, today) ? ' is-late' : ''}`}>{whenBack(it.away, today)}</span>
                </>
              ) : <span className="away-where">Back in your closet</span>}
            </div>
            {it.away ? (
              <button type="button" className="btn btn-small" disabled={offline || busy === it.id} title={title}
                aria-label={`It's back: ${name}`} onClick={(e) => void act(it, () => api.itsBack(it.id), true, e.currentTarget.closest('li'))}>It's back</button>
            ) : (
              <button type="button" className="btn btn-small btn-ghost" disabled={offline || busy === it.id} title={title}
                aria-label={`Undo: ${name} is back`} onClick={(e) => void act(it, () => api.undoBack(it.id), false, e.currentTarget.closest('li'))}>Undo</button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
