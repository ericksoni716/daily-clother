import { useRef, useState } from 'react';
import { ChevronIcon } from './Icons';
import { KindPicker, type KindItem } from './KindPicker';
import { kindDrawing, kindLine, type KindGroup, type KindInfo } from '../kinds';
import { kindWho } from '../review';
import { SAVE_WORDS, Sheet, type SaveState } from './ui';
import type { Item } from '../types';

const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';

/**
 * "What is it?": the item's kind from the owner's taxonomy, with its small drawing, and who said it (how sure Claude
 * was when it is Claude's word). Tapping it opens the kinds to choose from: a sheet on a phone, a popover on a wider
 * screen. The item page saves the choice at once; the review keeps it until "That's right".
 */
export function WhatItIs({ item, groups, disabled, busy = false, kept = 'idle', onPick }: {
  item: KindItem & Pick<Item, 'kind_name' | 'category' | 'kind_by' | 'kind_confidence'>;
  groups: KindGroup[] | undefined;
  disabled: boolean;
  busy?: boolean;
  /** how saving the choice went, said beside it (the item page's "Saved"; the review saves on "That's right") */
  kept?: SaveState;
  /** resolves true once the choice is kept, and the sheet closes */
  onPick?(kind: KindInfo): Promise<boolean> | boolean;
}) {
  const button = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const shown = open && !disabled && !!onPick;
  const said = kindLine(item, groups);
  const line = said || 'Not said';
  const who = kindWho(item);
  return (
    <div className={`detail-row kind-row${shown ? ' is-open' : ''}`}>
      <button ref={button} type="button" className="detail-row-button" aria-expanded={shown} aria-haspopup="dialog"
        aria-label={`What is it?: ${line}${who ? `. ${who}` : ''}${kept !== 'idle' ? `. ${SAVE_WORDS[kept]}` : ''}`} disabled={disabled || !onPick}
        title={disabled ? OFFLINE_TITLE : undefined} data-testid="what-is-it" onClick={() => setOpen(!shown)}>
        <span className="detail-row-label">What is it?</span>{' '}
        <span className={`detail-row-value${said ? '' : ' is-empty'}`}>
          {item.kind && <img className="kind-row-pic" src={kindDrawing(item.kind, item.color_hex)} alt="" data-testid="kind-pic" />}
          <span className="kind-row-words">
            <span className="detail-row-text is-wrapping">{line}</span>{' '}
            {who && <span className="kind-row-sure">{who}</span>}
          </span>
        </span>
        {kept !== 'idle' && <>{' '}<span className="save-status kept" data-testid="kept-kind">{SAVE_WORDS[kept]}</span></>}
        <ChevronIcon className="detail-row-chevron" />
      </button>
      {shown && (
        <Sheet title="What is it?" popover keep={button} className="detail-editor kind-sheet" testId="kind-picker"
          onClose={() => setOpen(false)}>
          <KindPicker item={item} busy={busy} onPick={async (kind) => {
            if (await onPick(kind)) setOpen(false);
          }} />
        </Sheet>
      )}
    </div>
  );
}
