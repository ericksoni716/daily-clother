import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { api } from '../api';
import { writePart } from '../settings';
import { lineSource, lineText, removedWords } from '../style';
import type { StyleLine, StyleProfile } from '../types';
import { Button } from './ui';

type Toast = (m: string, k?: 'ok' | 'error') => void;

/** One line of Your style as the card shows it: the words, and where they came from underneath. */
export function LineWords({ line }: { line: StyleLine }) {
  return (
    <>
      <span className="style-line-text">{lineText(line.text)}</span>
      <span className="style-line-source">{lineSource(line)}</span>
    </>
  );
}

/**
 * Every line of Your style, each with where it came from, to change or remove (with Undo), and a line to add by hand.
 * What Claude reads is these lines in order.
 */
export function StyleLines({ lines, offline, toast }: { lines: StyleLine[]; offline: boolean; toast: Toast }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [adding, setAdding] = useState('');
  const [busy, setBusy] = useState(false);
  const [removed, setRemoved] = useState<{ id: number; text: string } | null>(null);

  async function run(call: () => Promise<StyleProfile>, done?: (p: StyleProfile) => void): Promise<boolean> {
    setBusy(true);
    try {
      const saved = await call();
      writePart(qc, { style_profile: saved });
      done?.(saved);
      return true;
    } catch (e) {
      toast((e as Error).message, 'error');
      return false;
    } finally {
      setBusy(false);
    }
  }

  const locked = offline || busy;
  return (
    <div className="style-lines" data-testid="style-lines">
      {removed && (
        <div className="style-removed" role="status">
          <p>{removedWords(removed.text)}</p>
          <Button small variant="ghost" disabled={locked}
            onClick={() => void run(() => api.restoreStyleLine(removed.id), () => setRemoved(null))}>Undo</Button>
        </div>
      )}
      <ol className="style-line-list" aria-label="The lines of your style">
        {lines.map((line) => (
          <li key={line.id} className="style-line" data-testid="style-line">
            {editing === line.id ? (
              <form className="style-line-edit" onSubmit={(e: FormEvent) => {
                e.preventDefault();
                void run(() => api.editStyleLine(line.id, draft), () => setEditing(null));
              }}>
                <label className="field">
                  <span className="visually-hidden">Change this line</span>
                  <input value={draft} maxLength={500} disabled={locked} autoFocus onChange={(e) => setDraft(e.target.value)} />
                </label>
                <div className="style-line-actions">
                  <Button small variant="primary" type="submit" disabled={locked || !draft.trim()}>Save</Button>
                  <Button small variant="ghost" disabled={busy} onClick={() => setEditing(null)}>Cancel</Button>
                </div>
              </form>
            ) : (
              <>
                <p className="style-line-words"><LineWords line={line} /></p>
                <div className="style-line-actions">
                  <Button small variant="ghost" disabled={locked} aria-label={`Change “${lineText(line.text)}”`}
                    onClick={() => { setEditing(line.id); setDraft(lineText(line.text)); }}>Change</Button>
                  <Button small variant="ghost" disabled={locked} aria-label={`Remove “${lineText(line.text)}”`}
                    onClick={() => void run(() => api.removeStyleLine(line.id), (p) => {
                      setRemoved('removed' in p ? { id: (p as StyleProfile & { removed: number }).removed, text: line.text } : null);
                    })}>Remove</Button>
                </div>
              </>
            )}
          </li>
        ))}
      </ol>
      <form className="style-line-add" onSubmit={(e: FormEvent) => {
        e.preventDefault();
        if (adding.trim()) void run(() => api.addStyleLine(adding), () => { setAdding(''); toast('Saved'); });
      }}>
        <label className="field">
          <span>Add a line</span>
          <input value={adding} maxLength={500} disabled={locked} placeholder="No ties unless it is a wedding."
            onChange={(e) => setAdding(e.target.value)} />
        </label>
        <Button small type="submit" disabled={locked || !adding.trim()}>Add</Button>
      </form>
    </div>
  );
}
