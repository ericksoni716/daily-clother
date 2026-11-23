import { useRef, useState } from 'react';
import { Button, Sheet } from './ui';
import { MoreIcon } from './Icons';
import { OutfitPics, useAllItems } from '../screens/Worn';
import { navigate } from '../router';
import { againPath, allRowsLabel, aroundOffer, aroundPath, ON_PAGE, piecesFrom, wornInWords, type WornIn } from '../pieceOutfits';
import type { Item, ItemSummary } from '../types';
import { localDay, sinceDay } from '../wears';
import './PieceOutfits.css';

const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';

/**
 * "Build an outfit around it", in the card that says whether the piece can be worn today: it opens Today built around
 * the piece. When Today could not (in the laundry, away, not described yet) one line says when it can instead; an
 * archived piece, or a kind no outfit has a place for, gets neither.
 */
export function BuildAround({ item, disabled }: { item: Item; disabled: boolean }) {
  const offer = aroundOffer(item);
  if (!offer.button && !offer.line) return null;
  return (
    <div className="wear-around" data-testid="build-around">
      {offer.button ? (
        <Button small disabled={disabled} title={disabled ? OFFLINE_TITLE : undefined}
          onClick={() => navigate(aroundPath(item.id))}>Build an outfit around it</Button>
      ) : <p className="muted wear-around-line">{offer.line}</p>}
    </div>
  );
}

/**
 * When you wore it: the piece's wears, each worn outfit once with its pieces, when (and how often) it was worn and how it
 * went; a wear with no outfit is a plain dated line. The first three are on the page, the rest behind "All N outfits" in
 * a sheet. Each row's ⋯ holds "Wear this again" (as on Worn) and removing a wear.
 */
export function WornInList({ item, disabled, onUnwear }: {
  item: Item; disabled: boolean; onUnwear(day: string, saidAs: string): void;
}) {
  const rows = item.worn_in ?? [];
  const byId = useAllItems();
  const [all, setAll] = useState(false);
  const allButton = useRef<HTMLButtonElement>(null);
  if (!rows.length) return null;
  const from = piecesFrom(window.location.pathname);
  const list = (shown: WornIn[]) => (
    <ul className="worn-in-list" aria-labelledby={`worn-in-${item.id}`}>
      {shown.map((row) => (
        <WornInRow key={row.outfit_id ? `${row.outfit_id}~${row.days[0]}` : row.days[0]} row={row} byId={byId} from={from}
          disabled={disabled} onUnwear={onUnwear} />
      ))}
    </ul>
  );
  return (
    <div className="worn-in" data-testid="worn-in">
      <p className="chip-group-title" id={`worn-in-${item.id}`}>When you wore it</p>
      {list(rows.slice(0, ON_PAGE))}
      {rows.length > ON_PAGE && (
        <button ref={allButton} type="button" className="btn btn-link worn-in-all" aria-haspopup="dialog" aria-expanded={all}
          onClick={() => setAll(true)}>{allRowsLabel(rows)}</button>
      )}
      {all && (
        <Sheet title="When you wore it" anchor={allButton} onClose={() => setAll(false)} className="worn-in-sheet" testId="worn-in-all">
          {list(rows)}
        </Sheet>
      )}
    </div>
  );
}

function WornInRow({ row, byId, from, disabled, onUnwear }: {
  row: WornIn; byId: Map<string, ItemSummary>; from: string; disabled: boolean; onUnwear(day: string, saidAs: string): void;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const today = localDay();
  const words = wornInWords(row, today);
  const title = disabled ? OFFLINE_TITLE : undefined;
  const choose = (act: () => void) => () => {
    setOpen(false);
    act();
  };
  return (
    <li className="worn-in-row" data-testid="worn-in-row">
      <div className="worn-in-head">
        <span className="worn-in-when">{words}</span>
        <button ref={button} type="button" className="btn btn-icon btn-ghost worn-in-more"
          aria-label={`More for ${row.pieces ? 'the outfit' : 'the wear'}: ${words}`} aria-haspopup="dialog" aria-expanded={open}
          onClick={() => setOpen(!open)}>
          <MoreIcon />
        </button>
      </div>
      {row.pieces && <OutfitPics outfit={{ pieces: row.pieces, gone: row.gone }} byId={byId} from={from} />}
      {open && (
        <Sheet title={row.pieces ? 'This outfit' : 'This wear'} anchor={button} onClose={() => setOpen(false)} className="worn-menu-sheet"
          testId="worn-in-menu">
          <div className="worn-menu-list">
            {row.outfit_id && (
              <Button block disabled={disabled} title={title} onClick={choose(() => navigate(againPath(row.outfit_id!)))}>Wear this again</Button>
            )}
            {row.days.map((day) => (
              <Button key={day} block variant="danger-quiet" disabled={disabled} title={title}
                onClick={choose(() => onUnwear(day, 'Wear removed'))}>
                {row.days.length === 1 ? 'Remove this wear' : `Remove the wear from ${sinceDay(day, today)}`}
              </Button>
            ))}
          </div>
        </Sheet>
      )}
    </li>
  );
}
