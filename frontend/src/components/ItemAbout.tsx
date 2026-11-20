import { useEffect, useId, useRef, useState } from 'react';
import { useWhenLeaving } from '../leave';
import { lookLine, notesPatch, notesText } from '../look';
import type { Item, ItemPatch, ItemSummary } from '../types';

/** Fresh data may update an untouched field, but must not replace text still being typed. */
export function useFieldText(value: string) {
  const [text, setText] = useState(value);
  const previous = useRef(value);
  useEffect(() => {
    const before = previous.current;
    previous.current = value;
    setText((current) => current === before ? value : current);
  }, [value]);
  return [text, setText] as const;
}

/**
 * The one line under the item's name: what it is, its colour and how it sits, all read from the one description the
 * drawing was made from (src/look.ts). Each word of how it sits opens its detail in "Fix the details". The line keeps
 * its height while the item is read, so nothing under it moves when the rest arrives.
 */
export function LookLine({ item, disabled, onPick }: {
  item: Pick<ItemSummary, 'kind_name' | 'category' | 'color' | 'pattern'> & Partial<Pick<Item, 'shade' | 'as_worn'>>;
  disabled: boolean;
  onPick?(field: string): void;
}) {
  const parts = lookLine(item);
  return (
    <p className="detail-look" data-testid="look-line">
      {parts.map((p, i) => (
        <span key={p.part} className="detail-look-part">
          {i > 0 && <span className="detail-look-sep" aria-hidden="true"> · </span>}
          {p.field && onPick ? (
            <button type="button" className="btn-link detail-look-word" disabled={disabled}
              title={`Fix the ${p.text.toLowerCase()} in the details`} onClick={() => onPick(p.field!)}>{p.text}</button>
          ) : <span>{p.text}</span>}
        </span>
      ))}
    </p>
  );
}

/**
 * "Notes for you and Claude": one box for everything the owner writes about an item. It shows every note kept about
 * the item (how you wear it, older fit notes, notes and the reason for the rating), and a save keeps the whole text
 * where the stylist reads it (src/look.ts, `notesPatch`).
 */
export function NotesBox({ item, disabled, onSave }: {
  item: Pick<Item, 'wear_notes' | 'fit_notes' | 'notes' | 'rating_reason'>;
  disabled: boolean;
  onSave(patch: ItemPatch): void;
}) {
  const shown = notesText(item);
  const [text, setText] = useFieldText(shown);
  const hint = useId();
  const commit = () => {
    const patch = notesPatch(text, item);
    if (patch) onSave(patch);
  };
  useWhenLeaving(commit);
  return (
    <div className="field-with-hint">
      <label className="field">
        <span>Notes for you and Claude</span>
        <textarea value={text} rows={3} disabled={disabled} aria-describedby={hint}
          placeholder="e.g. only with the navy suit; runs small in the shoulders; great for dinners out"
          onChange={(e) => setText(e.target.value)} onBlur={commit} />
      </label>
      <p className="hint" id={hint}>Claude reads these when it chooses your outfits.</p>
    </div>
  );
}
