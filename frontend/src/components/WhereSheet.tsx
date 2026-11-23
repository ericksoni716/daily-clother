import { useState, type FormEvent, type RefObject } from 'react';
import { AWAY_PLACES, PLACE_WORDS } from '../away';
import type { Away, AwayPlace } from '../types';
import { localDay } from '../wears';
import { Button, Sheet } from './ui';

export type WhereChoice = { place: 'home' } | { place: AwayPlace; until: string | null; note: string | null };

const NOTE_MAX = 120;

/** "Where it is", in a sheet: in your closet or one of the places away, then, when away, the day you expect it back
 * and a note of your own (kept on this computer). Saves only with its own button. */
export function WhereSheet({ away, anchor, onCancel, onSave }: {
  away: Away | null;
  anchor: RefObject<HTMLElement | null>;
  onCancel(): void;
  onSave(choice: WhereChoice): void;
}) {
  const [place, setPlace] = useState<AwayPlace | 'home'>(away?.place ?? 'home');
  const [until, setUntil] = useState(away?.until ?? '');
  const [note, setNote] = useState(away?.note ?? '');
  const today = localDay();
  const choices: { value: AwayPlace | 'home'; label: string }[] = [
    { value: 'home', label: 'In your closet' }, ...AWAY_PLACES.map((p) => ({ value: p, label: PLACE_WORDS[p] })),
  ];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSave(place === 'home' ? { place } : { place, until: until || null, note: note.trim() || null });
  };

  return (
    <Sheet title="Where it is" anchor={anchor} closeLabel="Cancel" onClose={onCancel} className="where-sheet" testId="where-sheet">
      <form className="where-form" onSubmit={submit} aria-label="Where it is">
        <div className="chips" role="group" aria-label="Where it is">
          {choices.map((c) => (
            <button key={c.value} type="button" className={`chip${place === c.value ? ' is-on' : ''}`} aria-pressed={place === c.value}
              onClick={() => setPlace(c.value)}>{c.label}</button>
          ))}
        </div>
        {place !== 'home' && (
          <>
            <label className="field">
              <span>When do you expect it back? (if you know)</span>
              <input type="date" value={until} min={today} onChange={(e) => setUntil(e.target.value)} />
            </label>
            <label className="field">
              <span>A note for you</span>
              <input type="text" value={note} maxLength={NOTE_MAX} placeholder="For the hem" autoComplete="off"
                onChange={(e) => setNote(e.target.value)} />
            </label>
            <p className="hint">The note stays on this computer. Claude never reads it.</p>
          </>
        )}
        <Button variant="primary" block type="submit">
          {place === 'home' ? (away ? "It's back" : 'Keep it in your closet') : 'Save'}
        </Button>
      </form>
    </Sheet>
  );
}
