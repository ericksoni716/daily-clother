import { useId, useState } from 'react';
import { api, ApiError } from '../api';
import { DRAWN_DEMO, drawingShoe, drawnLine, drawnOffer, drawQuestion } from '../shoe';
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

/** "Drawn for the outfit figure" on a shoe's page: the drawing Claude made from its photos, on two legs, with how long
 * it took, how often it was checked against the photos and what it cost; what is happening while it is drawn; and
 * "Draw again", which asks first (it replaces the drawing once the new one is done, and costs something). */
export function ShoeDrawn({ item, disabled, demo, onSaved, onError }: Props) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const back = useConfirmFocus(confirming);
  const titleId = useId();
  const askId = useId();
  const drawn = item.drawn;
  if (!drawn) return null;
  const offer = drawnOffer(item, demo);
  const line = drawnLine(drawn);
  const draw = async (saidAs: string) => {
    setBusy(true);
    try {
      onSaved(await api.drawShoe(item.id), saidAs);
      setConfirming(false);
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  const off = disabled || busy;
  const message = demo && !drawn.url ? DRAWN_DEMO : drawn.message;
  return (
    <section className="shoe-drawn" aria-labelledby={titleId} data-testid="shoe-drawn">
      <h3 className="chip-group-title" id={titleId}>Drawn for the outfit figure</h3>
      {drawn.url && (
        <img className="shoe-drawn-picture" src={drawn.url} width={440} height={400}
          alt="The shoe as Claude drew it from its photos, on two legs, as the outfit figure will wear it" />
      )}
      {line && <p className="muted small" data-testid="shoe-drawn-line">{line}</p>}
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
    </section>
  );
}
