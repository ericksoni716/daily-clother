import { useEffect, useId, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import {
  capitalise, changeLine, detailSummary, historyLine, historyWhen, svgSource,
  type CorrectionAnswer, type DetailChoices, type DetailOptions, type HistoryEntry,
} from '../corrections';
import type { Item } from '../types';
import './FixDetails.css';

const OFFLINE = "You're offline, so the details can't be fixed right now.";
const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';

interface Props {
  item: Item;
  /** Offline: nothing can be changed. */
  disabled: boolean;
  onSaved(item: Item, saidAs: string): void;
  onError(message: string): void;
}

/** What changes the item as a whole: when it moves, what is shown here is asked for again. */
const stampOf = (item: Item) => `${item.updated_at}|${item.tagged_at}|${item.illustration_url}`;

/** The latest error handler, without asking again each time the item page draws itself. */
function useLatest<T>(value: T) {
  const ref = useRef(value);
  useEffect(() => {
    ref.current = value;
  });
  return ref;
}

/** "Fix the details": the details for this kind of garment, picked by looking, or said in a sentence. */
export function FixDetails({ item, disabled, onSaved, onError }: Props) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<DetailOptions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);
  const [choices, setChoices] = useState<DetailChoices | null>(null);
  const [busy, setBusy] = useState(false);
  const stamp = stampOf(item);
  const id = item.id;
  const report = useLatest(onError);

  useEffect(() => {
    if (!open || disabled) return;
    let gone = false;
    api.detailOptions(id).then((o) => {
      if (gone) return;
      setOptions(o);
      setLoadError(null);
    }, (e: ApiError) => !gone && setLoadError(e.message));
    return () => void (gone = true);
  }, [open, disabled, id, stamp]);

  useEffect(() => {
    if (!open || !picking || disabled) return;
    let gone = false;
    api.detailChoices(id, picking).then((c) => !gone && setChoices(c), (e: ApiError) => !gone && report.current(e.message));
    return () => void (gone = true);
  }, [open, picking, disabled, id, stamp, report]);

  const pick = async (name: string, value: unknown, saidAs: string) => {
    setBusy(true);
    try {
      onSaved(await api.setDetails(id, { [name]: value }), saidAs);
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const alt = item.name || 'Item';
  return (
    <section className="fix" aria-label="Fix the details">
      <button type="button" className="btn btn-small fix-open" aria-expanded={open} disabled={disabled}
        title={disabled ? OFFLINE_TITLE : undefined} onClick={() => setOpen((o) => !o)}>
        {open ? 'Close the details' : 'Fix the details'}
      </button>
      {disabled && open && <p className="muted">{OFFLINE}</p>}
      {open && !disabled && (
        <div className="fix-panel">
          <div className="fix-head">
            {item.illustration_url && <img className="fix-drawing" src={item.illustration_url} alt={`${alt}, drawing as it is now`} />}
            <p className="muted">
              Tap a detail to change it. What you set here stays when Claude describes the item again, and can be undone from the history.
            </p>
          </div>
          {loadError && <p className="notice notice-warn" role="alert">{loadError}</p>}
          {options?.message && <p className="notice">{options.message}</p>}
          {options?.groups.map((g) => (
            <section key={g.id} className="fix-group" aria-label={g.title}>
              <h3 className="chip-group-title">{g.title}</h3>
              <ul className="fix-list">
                {g.details.map((d) => {
                  const on = picking === d.name;
                  return (
                    <li key={d.name}>
                      <button type="button" className={`fix-detail${on ? ' is-on' : ''}`} aria-expanded={on}
                        aria-label={`${detailSummary(d)}${d.own ? ' (set by you)' : ''}`} onClick={() => {
                          setChoices(null);
                          setPicking(on ? null : d.name);
                        }}>
                        <span className="fix-detail-title">{capitalise(d.title)}</span>
                        <span className="fix-detail-value">{d.words}{d.own && <span className="fix-own"> · set by you</span>}</span>
                      </button>
                      {on && choices?.name === d.name && (
                        <Choices item={item} choices={choices} busy={busy} hasAnswer={!!item.details}
                          onPick={(v, words) => pick(d.name, v, `${capitalise(d.title)}: ${words}`)}
                          onGiveBack={() => pick(d.name, null, `${capitalise(d.title)}: back to Claude's description`)} />
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
          {options?.kind && <SayIt item={item} onSaved={onSaved} />}
        </div>
      )}
    </section>
  );
}

interface ChoicesProps {
  item: Item;
  choices: DetailChoices;
  busy: boolean;
  hasAnswer: boolean;
  onPick(value: unknown, words: string): void;
  onGiveBack(): void;
}

function Choices({ item, choices, busy, hasAnswer, onPick, onGiveBack }: ChoicesProps) {
  const drawn = choices.choices.filter((c) => c.svg);
  const shown = drawn.length > 0;
  const worded = choices.choices.filter((c) => !c.svg && !(shown && c.current));
  const current = choices.choices.find((c) => c.current);
  return (
    <div className="fix-choices" role="group" aria-label={`Choices for the ${choices.title}`}>
      {shown && (
        <div className="fix-tiles">
          {current && (
            <button type="button" className="fix-tile is-on" aria-pressed="true" disabled={busy} onClick={() => onPick(current.value, current.words)}>
              {item.illustration_url ? <img src={item.illustration_url} alt="" /> : <span className="fix-tile-blank" />}
              <span>{current.words}</span>
            </button>
          )}
          {drawn.map((c) => (
            <button key={String(c.value)} type="button" className="fix-tile" aria-pressed="false" disabled={busy}
              onClick={() => onPick(c.value, c.words)}>
              <img src={svgSource(c.svg!)} alt="" />
              <span>{c.words}</span>
            </button>
          ))}
        </div>
      )}
      {worded.length > 0 && (
        <>
          {shown && <p className="muted fix-same">These look the same in the drawing:</p>}
          <div className="chips">
            {worded.map((c) => (
              <button key={String(c.value)} type="button" className={`chip${c.current ? ' is-on' : ''}`} aria-pressed={c.current}
                disabled={busy} onClick={() => onPick(c.value, c.words)}>{c.words}</button>
            ))}
          </div>
        </>
      )}
      {choices.own && hasAnswer && (
        <button type="button" className="btn btn-small fix-give-back" disabled={busy} onClick={onGiveBack}>
          Use what Claude saw instead
        </button>
      )}
    </div>
  );
}

function SayIt({ item, onSaved }: { item: Item; onSaved: Props['onSaved'] }) {
  const field = useId();
  const [text, setText] = useState('');
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<CorrectionAnswer | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const ask = async () => {
    setAsking(true);
    setAnswer(null);
    setProblem(null);
    try {
      setAnswer(await api.correct(item.id, text.trim()));
    } catch (e) {
      setProblem((e as ApiError).message);
    } finally {
      setAsking(false);
    }
  };

  const confirm = async () => {
    if (!answer) return;
    setAsking(true);
    try {
      const saved = await api.confirmCorrection(item.id, answer.sentence, answer.changes.map((c) => ({ name: c.name, value: c.value })));
      setAnswer(null);
      setText('');
      onSaved(saved, 'Changed as you said');
    } catch (e) {
      setProblem((e as ApiError).message);
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="fix-say">
      <form onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) void ask();
      }}>
        <label htmlFor={field} className="chip-group-title">Or say what's wrong</label>
        <div className="fix-say-row">
          <input id={field} type="text" maxLength={500} value={text} placeholder="e.g. it has three buttons" disabled={asking}
            onChange={(e) => setText(e.target.value)} />
          <button type="submit" className="btn btn-small" disabled={asking || !text.trim()}>{asking && !answer ? 'Asking Claude…' : 'Ask Claude'}</button>
        </div>
        <p className="muted fix-note">Claude is sent your sentence and the item's description; its photo only if the sentence can't be understood without it.</p>
      </form>
      {problem && <p className="notice notice-warn" role="alert">{problem}</p>}
      {answer?.state === 'understood' && (
        <div className="fix-confirm" role="status">
          <p><strong>Claude understood:</strong></p>
          <ul>{answer.changes.map((c) => <li key={c.name}>{changeLine(c)}</li>)}</ul>
          {answer.not_understood && <p className="muted">Left out: {answer.not_understood}</p>}
          {answer.sent && <p className="muted fix-note">{answer.sent}</p>}
          <div className="row">
            <button type="button" className="btn btn-primary btn-small" disabled={asking} onClick={() => void confirm()}>Make these changes</button>
            <button type="button" className="btn btn-small" disabled={asking} onClick={() => setAnswer(null)}>Cancel</button>
          </div>
        </div>
      )}
      {answer && answer.state !== 'understood' && (
        <p className="notice" role="status">
          {answer.state === 'not_understood' ? `Nothing was changed. ${answer.not_understood ?? ''}` : answer.message}
        </p>
      )}
    </div>
  );
}

/** The "History" fold: every change to the item's description, newest first, each undoable where allowed. */
export function ItemHistory({ item, disabled, onSaved, onError }: Props) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [busy, setBusy] = useState(false);
  const stamp = stampOf(item);
  const id = item.id;
  const report = useLatest(onError);

  useEffect(() => {
    if (!open || disabled) return;
    let gone = false;
    api.history(id).then((h) => !gone && setEntries(h), (e: ApiError) => !gone && report.current(e.message));
    return () => void (gone = true);
  }, [open, disabled, id, stamp, report]);

  const undo = async (entry: HistoryEntry) => {
    setBusy(true);
    try {
      const done = await api.undo(id, entry.id);
      setEntries(done.history);
      onSaved(done.item, 'Undone');
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="more fix-history" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>History</summary>
      <div className="tag-body">
        {disabled && <p className="muted">You're offline, so the history can't be shown or undone right now.</p>}
        {!disabled && entries?.length === 0 && <p className="muted">No changes to its description yet.</p>}
        {!disabled && entries && entries.length > 0 && (
          <ol className="fix-history-list">
            {entries.map((e) => {
              const line = historyLine(e);
              return (
                <li key={e.id} className={e.undone ? 'is-undone' : undefined}>
                  <div>
                    <p className="fix-history-line">{line}{e.undone ? ' (undone)' : ''}</p>
                    <p className="muted fix-note"><time dateTime={e.at}>{historyWhen(e.at)}</time>
                      {!e.can_undo && !e.undone && e.why_not && e.parts.length > 0 ? ` · ${e.why_not}` : ''}</p>
                  </div>
                  {e.can_undo && (
                    <button type="button" className="btn btn-small" disabled={busy || disabled} aria-label={`Undo: ${line}`}
                      onClick={() => void undo(e)}>Undo</button>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </details>
  );
}
