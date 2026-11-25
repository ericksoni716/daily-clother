import { useState, type FormEvent, type RefObject } from 'react';
import { canChoose, choiceNote, dayChoices, MAX_AHEAD_DAYS, TOO_FAR, type Plan } from '../plans';
import { addDays, daysAhead } from '../today';
import type { TripSummary } from '../trips';
import { Button, Sheet } from './ui';
import './DaySheet.css';

/**
 * Another day to dress for, in a sheet: tomorrow and the next days by name, each marked when it has an outfit planned
 * or is part of a trip, then a date of your choice. Choosing one calls `onChoose` with the date.
 */
export function DaySheet({ today, plans, trips, anchor, onClose, onChoose, title = 'Dress for another day' }: {
  today: string; plans: readonly Plan[] | null | undefined; trips: readonly TripSummary[] | null | undefined;
  anchor: RefObject<HTMLElement | null>; onClose(): void; onChoose(day: string): void; title?: string;
}) {
  const [date, setDate] = useState('');
  const choices = dayChoices(today, plans, trips);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (canChoose(date, today)) onChoose(date);
  }

  return (
    <Sheet title={title} anchor={anchor} onClose={onClose} className="day-sheet" testId="another-day-sheet">
      <ul className="day-sheet-days" aria-label="The next days">
        {choices.map((c) => {
          const note = choiceNote(c);
          return (
            <li key={c.day}>
              <button type="button" className="day-sheet-day" onClick={() => onChoose(c.day)}>
                <span className="day-sheet-name">{c.label}</span>
                {note && <span className={`day-sheet-note${c.planned ? ' is-planned' : ''}`}>{note}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      <form className="day-sheet-other" onSubmit={submit}>
        <label className="field">
          <span>Another date</span>
          <input type="date" value={date} min={addDays(today, 1)} max={addDays(today, MAX_AHEAD_DAYS)}
            onChange={(e) => setDate(e.target.value)} data-testid="another-date" />
        </label>
        <Button type="submit" disabled={!canChoose(date, today)}>Dress for this day</Button>
      </form>
      {/* a date past the furthest says why the button is off, rather than leave it off without a word */}
      {/^\d{4}-\d{2}-\d{2}$/.test(date) && daysAhead(today, date) > MAX_AHEAD_DAYS && (
        <p className="hint day-sheet-far" role="status" data-testid="too-far-date">{TOO_FAR}</p>
      )}
    </Sheet>
  );
}
