import { useRef, useState } from 'react';
import { api } from '../api';
import { cameBackSentence, homeSentence, whereSentence } from '../away';
import type { Item } from '../types';
import { localDay } from '../wears';
import { WhereSheet, type WhereChoice } from './WhereSheet';
import './Where.css';

const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';

/**
 * Where the piece is, one row in the card that answers "can I wear it today" (with wearing and washing): in your
 * closet, or away at the cleaner's, at the tailor's or lent out, in a sentence. "Change" opens the choices in a sheet;
 * while it is away the row's first button is "It's back". A return today is said once, with Undo.
 * `run` sends a change and answers with the saved item (the item page's own `act`, which says it and keeps the page).
 */
export function WhereItIs({ item, disabled, run }: {
  item: Item;
  disabled: boolean;
  run(call: () => Promise<Item>, saidAs: string): Promise<Item | undefined>;
}) {
  const [open, setOpen] = useState(false);
  const change = useRef<HTMLButtonElement>(null);
  const today = localDay();
  const title = disabled ? OFFLINE_TITLE : undefined;
  const away = item.away ?? null;
  const back = !away ? item.came_back ?? null : null;
  const mending = item.condition === 'needs_repair';

  const choose = async (c: WhereChoice) => {
    setOpen(false);
    if (c.place === 'home') {
      if (away) await run(() => api.itsBack(item.id), "It's back");
      return;
    }
    await run(() => api.sendAway(item.id, { place: c.place, until: c.until, note: c.note }), 'Saved');
  };

  return (
    <div className="where" data-testid="where-it-is">
      <div className="where-text">
        <p className="where-line" data-testid="where-line">
          {away ? whereSentence(away, today) : back ? cameBackSentence(back) : homeSentence(item.condition)}
        </p>
        {away?.note && <p className="muted where-note">{away.note}</p>}
      </div>
      <div className="row where-actions">
        {away && (
          <button type="button" className="btn btn-small" disabled={disabled} title={title}
            onClick={() => void run(() => api.itsBack(item.id), "It's back")}>It's back</button>
        )}
        {back && (
          <button type="button" className="btn btn-small" disabled={disabled} title={title} aria-label="Undo: it's back"
            onClick={() => void run(() => api.undoBack(item.id), 'Undone')}>Undo</button>
        )}
        {!away && !back && mending && (
          <button type="button" className="btn btn-small" disabled={disabled} title={title}
            onClick={() => void run(() => api.sendAway(item.id, { place: 'tailor' }), "At the tailor's")}>Take it to the tailor's</button>
        )}
        <button ref={change} type="button" className="btn btn-small btn-ghost" disabled={disabled} title={title}
          aria-haspopup="dialog" aria-expanded={open} aria-label="Change where it is" onClick={() => setOpen((o) => !o)}>Change</button>
      </div>
      {open && <WhereSheet away={away} anchor={change} onCancel={() => setOpen(false)} onSave={(c) => void choose(c)} />}
    </div>
  );
}
