import { useState } from 'react';
import { api, ApiError } from '../api';
import { awayOrder, overdue, PLACE_WORDS, tileMarkLabel, whenBack } from '../away';
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
 * one tap each. A piece brought back stays in the list, saying so with Undo, until the view is left.
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
  const today = localDay();
  const away = awayOrder(pieces.filter((it) => it.away));
  const back = pieces.filter((it) => !it.away && returned.has(it.id));
  const act = async (it: ItemSummary, call: () => Promise<Item>, isBack: boolean) => {
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
      {[...away, ...back].map((it) => {
        const name = it.name || label('category', it.category) || 'Item';
        return (
          <li key={it.id} className="away-row" data-testid="away-row">
            <Link to={itemPath(it.id, 'active')} className="away-pic" aria-label={name}>
              {it.thumb_url ? <img src={it.thumb_url} alt="" loading="lazy" /> : it.illustration_url ? <img src={it.illustration_url} alt="" loading="lazy" /> : null}
            </Link>
            <div className="away-text">
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
                aria-label={`It's back: ${name}`} onClick={() => void act(it, () => api.itsBack(it.id), true)}>It's back</button>
            ) : (
              <button type="button" className="btn btn-small btn-ghost" disabled={offline || busy === it.id} title={title}
                aria-label={`Undo: ${name} is back`} onClick={() => void act(it, () => api.undoBack(it.id), false)}>Undo</button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
