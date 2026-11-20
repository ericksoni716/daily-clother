import { useId, useState } from 'react';
import { api, ApiError } from '../api';
import {
  backLabel, canCorrect, changedLine, DRAWN_DEMO, drawingShoe, drawnLine, drawnOffer, drawQuestion, NOTE_MAX, sideLine,
} from '../shoe';
import { partWords } from '../progress';
import { useItemProgress } from '../queries';
import type { Item } from '../types';
import { confirmKeys, useConfirmFocus } from './ui';
import { WarnIcon } from './Icons';
import './Shoe.css';

interface Props {
  item: Item;
  disabled: boolean;
  /** The demo closet is open: its shoes are never sent to Claude. */
  demo: boolean;
  onSaved(item: Item, saidAs: string): void;
  onError(message: string): void;
}

/** "Drawn by Claude from its photos" on a shoe's page: the shoe from its side, as the closet shows it, with what makes
 * it itself from the side, and the drawing for the outfit figure, on two legs, with how long
 * it took, how often it was checked against the photos and what it cost; what is happening while it is drawn; and
 * "Draw again", which asks first (it replaces the drawing once the new one is done, and costs something). Once it has a
 * drawing, a one-line box says what is wrong with it: Claude changes only that, checks the change against the photos
 * and says when the note goes against them; the drawing before is kept, one tap away. */
export function ShoeDrawn({ item, disabled, demo, onSaved, onError }: Props) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const back = useConfirmFocus(confirming);
  const titleId = useId();
  const askId = useId();
  const noteId = useId();
  const drawn = item.drawn;
  const progress = useItemProgress(item);
  if (!drawn) return null;
  const offer = drawnOffer(item, demo);
  const line = drawnLine(drawn);
  const sideSaid = sideLine(drawn);
  const changed = changedLine(drawn);
  const swapLabel = backLabel(drawn);
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
  const draw = (saidAs: string) => run(() => api.drawShoe(item.id), saidAs, () => setConfirming(false));
  const send = () => run(() => api.correctDrawing(item.id, note.trim()), 'Changing the drawing as you asked',
    () => setNote(''));
  const swap = () => run(() => api.drawingBack(item.id),
    drawn.previous_newer ? 'Back to the newer drawing' : 'Back to the drawing before');
  const off = disabled || busy;
  // while it is drawn or changed, in the words of the item's progress (the same as the strip on the picture)
  const message = demo && !drawn.url ? DRAWN_DEMO : partWords(progress, 'shoe', drawn.correcting ? drawn.note : null) ?? drawn.message;
  return (
    <section className="shoe-drawn" aria-labelledby={titleId} data-testid="shoe-drawn">
      <h3 className="chip-group-title" id={titleId}>Drawn by Claude from its photos</h3>
      {(drawn.url || drawn.side) && (
        <div className={`shoe-drawn-pictures${drawn.url && drawn.side ? ' is-two' : ''}`}>
          {drawn.side && (
            <img className="shoe-drawn-picture shoe-drawn-side" src={drawn.side.url} width={400} height={460}
              alt="The shoe from the side, drawn by Claude for the closet" />
          )}
          {drawn.url && (
            <img className="shoe-drawn-picture" src={drawn.url} width={440} height={400}
              alt="The shoe as Claude drew it from its photos, on two legs, as the outfit figure will wear it" />
          )}
        </div>
      )}
      {sideSaid && <p className="muted small" data-testid="shoe-drawn-side">{sideSaid}</p>}
      {line && <p className="muted small" data-testid="shoe-drawn-line">{line}</p>}
      {changed && <p className="small" data-testid="shoe-drawn-changed">{changed}</p>}
      {changed && drawn.against_photos && (
        <p className="notice shoe-drawn-against" data-testid="shoe-drawn-against">{drawn.against_photos}</p>
      )}
      {swapLabel && (
        <div className="row shoe-fix-actions">
          <button type="button" className="btn btn-small" disabled={off} onClick={() => void swap()}>{swapLabel}</button>
        </div>
      )}
      {drawn.url && drawn.photos_changed && <p className="small">The photos changed since this drawing.</p>}
      {drawn.state === 'failed' ? (
        <div className="notice notice-warn">
          <WarnIcon />
          <div>
            <p>{message}</p>
            <button type="button" className="btn btn-small" disabled={off}
              onClick={() => void draw('Trying again: the shoe is drawn from its photos')}>Try again</button>
          </div>
        </div>
      ) : message ? (
        <p className={drawingShoe(drawn) ? 'notice' : 'muted small'} role="status">{message}</p>
      ) : null}
      {(offer === 'draw' || offer === 'again') && (!confirming ? (
        <div className="row shoe-fix-actions">
          <button ref={back} type="button" className="btn btn-small" disabled={off} onClick={() => setConfirming(true)}>
            {offer === 'again' ? 'Draw again' : 'Draw it'}
          </button>
        </div>
      ) : (
        <div className="confirm" role="alertdialog" aria-labelledby={askId} onKeyDown={confirmKeys(() => setConfirming(false))}>
          <p id={askId}>
            <strong>{offer === 'again' ? 'Draw the shoe again from its photos?' : 'Draw the shoe from its photos?'}</strong>{' '}
            {drawQuestion(drawn, offer === 'again')}
          </p>
          <div className="row">
            <button type="button" className="btn btn-primary" disabled={off} autoFocus
              onClick={() => void draw('The shoe is drawn from its photos in a moment')}>
              {offer === 'again' ? 'Draw it again' : 'Draw it'}
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => setConfirming(false)}>
              {offer === 'again' ? 'Keep this drawing' : 'Not now'}
            </button>
          </div>
        </div>
      ))}
      {canCorrect(drawn, demo) && (
        <form className="shoe-drawn-say" onSubmit={(e) => {
          e.preventDefault();
          if (note.trim()) void send();
        }}>
          <label htmlFor={noteId} className="chip-group-title">What's wrong with the drawing?</label>
          <div className="shoe-drawn-say-row">
            <input id={noteId} type="text" maxLength={NOTE_MAX} value={note} disabled={off}
              placeholder="e.g. the elastic sides should be wider" onChange={(e) => setNote(e.target.value)} />
            <button type="submit" className="btn btn-small" disabled={off || !note.trim()}>Send</button>
          </div>
          <p className="muted small">
            One thing to change. Claude changes only that and checks it against the photos; this drawing is kept, so
            you can go back to it.
          </p>
        </form>
      )}
    </section>
  );
}
