import { useState, type PointerEvent, type RefObject } from 'react';
import { itemName } from './ItemPic';
import { OutfitFigure } from './OutfitFigure';
import { ChevronIcon, ChevronLeftIcon, HangerIcon } from './Icons';
import { Button, Sheet } from './ui';
import { figureVersion } from '../figure';
import { Link } from '../router';
import { joinWords, outfitIds, placeLabel, wornOrder } from '../today';
import type { ItemSummary } from '../types';
import { CANDIDATE_ID, exampleDay, outfitStep, type WouldExample, type WouldPiece } from '../wouldwork';
import './WornWith.css';

/** The names of an example outfit's pieces, in the order they are put on: yours open the piece, the new one is "This piece". */
function names(ex: WouldExample, byId: Map<string, ItemSummary>) {
  return wornOrder(ex.pieces).map(({ place, id }) => ({ place, id, name: id === CANDIDATE_ID ? 'This piece' : itemName(byId.get(id)) }));
}

/**
 * A piece not in the closet worn with your own clothes, in one example outfit: the outfit drawn as worn (the piece drawn
 * from its description, among your layers as any garment is), then the pieces in it by name. The same in the sheet a
 * find opens and in the answer of Would this work?.
 */
export function WornOutfit({ example, piece, byId, compact = false }: {
  example: WouldExample; piece: WouldPiece; byId: Map<string, ItemSummary>; compact?: boolean;
}) {
  const parts = names(example, byId);
  const ids = outfitIds(example.pieces).filter((id) => id !== CANDIDATE_ID);
  return (
    <div className={compact ? 'worn-outfit is-compact' : 'worn-outfit'} data-testid="worn-outfit">
      <OutfitFigure pieces={example.pieces} piece={piece} version={figureVersion(ids, byId)}
        alt={`${exampleDay(example)}, as worn: ${joinWords(parts.map((p) => p.name))}`} />
      <ul className="worn-outfit-names" aria-label={`What is in the outfit ${exampleDay(example).toLowerCase()}`}>
        {parts.map((p) => (
          <li key={`${p.place}-${p.id}`}>
            <span className="muted">{placeLabel(p.place)}</span>{' '}
            {p.id === CANDIDATE_ID
              ? <strong>{p.name}</strong>
              : <Link to={`/wardrobe/item/${encodeURIComponent(p.id)}`}>{p.name}</Link>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** How far a swipe goes before it counts as one, in CSS pixels. */
const SWIPE = 40;

/**
 * "See it with your clothes": the example outfits made with a piece not in the closet, one at a time, to step or swipe
 * through, with the shop's own picture of it beside the drawing to compare. `outfits` null while they are worked out:
 * the figure's space, and the step's line above it, are kept. One line says the drawing is a rough idea (`note`), once. A sheet from the bottom on a
 * phone, a popover under the button that opened it (`keep`) on a computer.
 */
export function SeeItWorn({ title, piece, outfits, image, note, error, byId, keep, onClose }: {
  title: string; piece: WouldPiece | null; outfits: WouldExample[] | null; image: string | null; note: string;
  error: string | null; byId: Map<string, ItemSummary>; keep?: RefObject<HTMLElement | null>; onClose(): void;
}) {
  const [at, setAt] = useState(0);
  const [start, setStart] = useState<number | null>(null);
  const count = outfits?.length ?? 0;
  const shown = outfits && count ? outfits[Math.min(at, count - 1)] : null;
  const go = (step: number) => setAt((i) => Math.max(0, Math.min(count - 1, i + step)));
  const swipe = {
    onPointerDown: (e: PointerEvent) => setStart(e.clientX),
    onPointerUp: (e: PointerEvent) => {
      if (start !== null && Math.abs(e.clientX - start) > SWIPE) go(e.clientX < start ? 1 : -1);
      setStart(null);
    },
  };
  return (
    <Sheet title={title} popover keep={keep} className="worn-sheet" testId="worn-sheet" onClose={onClose}>
      <p className="hint worn-sheet-note">{note}</p>
      <div className="worn-sheet-steps">
        {shown && <>
          {count > 1 && <Button variant="ghost" small aria-label="The outfit before" disabled={at === 0} onClick={() => go(-1)}><ChevronLeftIcon /></Button>}
          <p className="worn-sheet-step" aria-live="polite">
            {count > 1 ? `${outfitStep(at, count)}, ${exampleDay(shown).toLowerCase()}` : exampleDay(shown)}
          </p>
          {count > 1 && <Button variant="ghost" small aria-label="The next outfit" disabled={at >= count - 1} onClick={() => go(1)}><ChevronIcon /></Button>}
        </>}
      </div>
      <div className={image ? 'worn-sheet-view has-image' : 'worn-sheet-view'} {...swipe}>
        {image && (
          <figure className="worn-sheet-shop">
            <img src={image} alt="The shop's picture of it" loading="lazy" referrerPolicy="no-referrer" />
            <figcaption className="muted">From the shop</figcaption>
          </figure>
        )}
        {shown && piece ? (
          <WornOutfit key={at} example={shown} piece={piece} byId={byId} />
        ) : error || (outfits && !count) ? (
          <p className="muted worn-sheet-empty" role="status">{error ?? 'No outfit can be made with it from your closet as it is now.'}</p>
        ) : (
          <div className="worn-outfit" aria-busy="true">
            <span className="pic-placeholder worn-sheet-wait" role="img" aria-label="Working out the outfits"><HangerIcon /></span>
          </div>
        )}
      </div>
    </Sheet>
  );
}
