import { useEffect, useId, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import type { Item } from '../types';
import { WarnIcon } from './Icons';

/** The longest line the owner can send (`tagger/adding.py` NOTE_MAX). */
export const ADD_MAX = 200;

interface Props {
  item: Item;
  /** A sentence handed over from "What's wrong with it?" that no detail could show: put in the box, not sent. `at`
   * tells one hand-over from the next. */
  given?: { text: string; at: number } | null;
  disabled: boolean;
  onSaved(item: Item, saidAs: string): void;
  onError(message: string): void;
}

/**
 * "Add to the drawing", in Fix the details: one line for what no detail shows (a patch, a panel, a tab, a line of
 * stitching). Claude draws it onto the drawing as it is, keeping the rest, checks it against the photo, and it shows on
 * the outfit figure too. It is drawn in the background, so the sheet can be closed meanwhile; the item's progress shows
 * it. What was added is listed, with how long it took and what it cost, and the drawing before the last change is one
 * tap away, as is taking every addition off. Not shown for a shoe (its drawing by Claude has its own note).
 */
export function AddToDrawing({ item, given = null, disabled, onSaved, onError }: Props) {
  const a = item.additions;
  const field = useId();
  const title = useId();
  const box = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [handed, setHanded] = useState(given);
  if (given !== handed) {   // a sentence handed over: put in the box for the owner to send
    setHanded(given);
    if (given) setText(given.text.slice(0, ADD_MAX));
  }
  useEffect(() => {
    if (given) box.current?.focus({ preventScroll: false });
  }, [given]);
  if (!a) return null;
  const drawing = a.state === 'drawing';
  const off = disabled || busy || drawing;
  const run = async (call: () => Promise<Item>, saidAs: string, after?: () => void) => {
    setBusy(true);
    try {
      onSaved(await call(), saidAs);
      after?.();
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  const send = (line: string) => run(() => api.addToDrawing(item.id, line), 'Claude is drawing it on', () => setText(''));
  return (
    <section className="fix-add" aria-labelledby={title} data-testid="add-to-drawing">
      <h3 className="fix-say-label" id={title}>Add to the drawing</h3>
      <p className="muted fix-note">
        For what no detail shows: a patch, a panel, a tab, a line of stitching. Claude draws it onto this drawing,
        keeps the rest as it is and checks it against the photo; it shows on the outfit figure too. It takes a minute
        or two, and you can close this meanwhile.
      </p>
      {a.parts.length > 0 && <p className="small" data-testid="added-parts">Added by Claude: {a.parts.join(', ')}.</p>}
      {a.parts.length > 0 && a.said && <p className="muted small">{a.said}</p>}
      {a.parts.length > 0 && a.took && <p className="muted small">{a.took}</p>}
      {a.moved && <p className="notice" role="status">{a.moved}</p>}
      {(a.can_go_back || a.can_remove) && (
        <div className="row fix-add-actions">
          {a.can_go_back && (
            <button type="button" className="btn btn-small" disabled={off}
              onClick={() => void run(() => api.additionsBack(item.id),
                a.back_newer ? 'Back to the newer drawing' : 'Back to the drawing before')}>
              {a.back_newer ? 'Go to the newer drawing' : 'Go back to the drawing before'}
            </button>
          )}
          {a.can_remove && (
            <button type="button" className="btn btn-small" disabled={off}
              onClick={() => void run(() => api.removeAdditions(item.id), "Claude's additions taken off")}>
              Take Claude's additions off
            </button>
          )}
        </div>
      )}
      {a.state === 'failed' ? (
        <div className="notice notice-warn" role="alert">
          <WarnIcon />
          <div>
            <p>{a.message}</p>
            {a.note && (
              <button type="button" className="btn btn-small" disabled={off} onClick={() => void send(a.note!)}>
                Send “{a.note}” again
              </button>
            )}
          </div>
        </div>
      ) : a.message ? (
        <p className="notice" role="status" data-testid="add-message">{a.message}</p>
      ) : null}
      <form className="fix-add-say" onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) void send(text.trim());
      }}>
        <label htmlFor={field} className="chip-group-title">What should Claude add?</label>
        <div className="fix-add-row">
          <input ref={box} id={field} type="text" maxLength={ADD_MAX} value={text} disabled={off}
            placeholder="e.g. a small red patch on the left sleeve" onChange={(e) => setText(e.target.value)} />
          <button type="submit" className="btn btn-small" disabled={off || !text.trim()}>Draw it on</button>
        </div>
      </form>
    </section>
  );
}
