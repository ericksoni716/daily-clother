import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import {
  capitalise, changeLine, claudeAway, confirmedChanges, detailSummary, fixOpening, historyLine, historyWhen, stillFor,
  svgSource, type CorrectionAnswer, type DetailChoices, type DetailOptions, type FixView, type HistoryEntry,
} from '../corrections';
import { detailOptionsQuery } from '../queries';
import { describedBy } from '../tagging';
import { queryKeys } from '../queryKeys';
import { useMediaQuery } from '../router';
import type { Item } from '../types';
import { buttonClass, Failed, PHONE, Sheet } from './ui';
import { AddToDrawing } from './AddToDrawing';
import { ShoeDrawingFix } from './ShoeTrace';
import './FixDetails.css';

const OFFLINE = "You're offline, so the details can't be fixed right now.";
const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';

interface Props {
  item: Item;
  /** Offline: nothing can be changed. */
  disabled: boolean;
  onSaved(item: Item, saidAs: string): void;
  onError(message: string): void;
}

type Focus = { field: string; at: number } | null;

interface FixProps extends Props {
  /** The button's words ("Something wrong? Tell Claude"); they stay the same while the sheet is open. */
  label: string;
  /** Whether its sheet is open. */
  open: boolean;
  /** A detail to open at once (a word of the item's fit line was tapped); `at` tells a second tap on the same word
   * from the first. */
  focus?: Focus;
  /** The demo closet is open: it is never sent to Claude, so there is no box to say what's wrong. */
  demo: boolean;
  onOpen(): void;
  onClose(): void;
}

/** Claude could not be reached the last time a sentence was sent, so "Fix the details" opens on the details one by one
 * until a sentence is read again (kept while the app is open). */
let away = false;

/** The details to fix here: the kind itself is chosen in the "What is it?" row, so it is left out. */
function fixable(options: DetailOptions | null | undefined): DetailOptions['groups'] {
  return (options?.groups ?? [])
    .map((g) => ({ ...g, details: g.details.filter((d) => d.name !== 'garment') }))
    .filter((g) => g.details.length > 0);
}

/** What changes the item as a whole: when it moves, what is shown here is asked for again. */
const stampOf = (item: Item) => `${item.updated_at}|${item.tagged_at}|${item.illustration_url}`;

/**
 * "Fix the details": one button under the item's summary line ("Something wrong? Tell Claude") that opens a sheet over
 * the page (a popover under the button on a computer). The sheet opens on a box to say what's wrong; the details
 * themselves, by group, are one tap away in the same sheet. Nothing is put into the page.
 */
export function FixDetails({ item, label, open, focus = null, demo, disabled, onOpen, onClose, onSaved, onError }: FixProps) {
  const button = useRef<HTMLButtonElement>(null);
  return (
    <span className="fix-anchor">
      <button ref={button} type="button" className="btn btn-link fix-open" aria-expanded={open} aria-haspopup="dialog"
        disabled={disabled} title={disabled ? OFFLINE_TITLE : undefined} onClick={() => (open ? onClose() : onOpen())}>
        {label}
      </button>
      {open && (
        <Sheet title="Fix the details" popover keep={button} className="fix-sheet" testId="fix-details" onClose={onClose}>
          <FixBody item={item} focus={focus} demo={demo} disabled={disabled} onSaved={onSaved} onError={onError}
            onDone={onClose} />
        </Sheet>
      )}
    </span>
  );
}

/** What the sheet holds: the box to say what's wrong, or the details for this kind of garment, picked by looking. */
function FixBody({ item, focus, demo, disabled, onSaved, onError, onDone }: Props & { focus: Focus; demo: boolean; onDone(): void }) {
  const phone = useMediaQuery(PHONE);
  const [opening] = useState(() => fixOpening({ demo, away, focus: !!focus, phone }));
  const [view, setView] = useState<FixView>(opening.view);
  const [picking, setPicking] = useState<string | null>(focus?.field ?? null);
  const [focused, setFocused] = useState(focus);
  const panel = useRef<HTMLDivElement>(null);
  const back = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  if (focus !== focused) {   // a word of the fit line was tapped: open its detail
    setFocused(focus);
    if (focus) {
      setView('list');
      setPicking(focus.field);
    }
  }
  const [busy, setBusy] = useState(false);
  // a sentence no detail could show, handed from the box to "Add to the drawing"
  const [handed, setHanded] = useState<{ text: string; at: number } | null>(null);
  const id = item.id;

  // Kept in the cache by item: asked again only after a save that touches them (`TOUCHES.item`) or when the item is
  // described again, not each time the item is read while work runs.
  const optionsQuery = useQuery({ ...detailOptionsQuery(id), enabled: !disabled });
  const options: DetailOptions | null = optionsQuery.data ?? null;
  const choicesQuery = useQuery({
    queryKey: queryKeys.itemDetails(id, picking ?? ''),
    queryFn: () => api.detailChoices(id, picking as string),
    enabled: !!picking && !disabled,
  });
  const choices: DetailChoices | null = choicesQuery.data ?? null;

  useEffect(() => {   // ...and bring it into view once the details are there
    if (!focus || !options) return;
    panel.current?.querySelector(`[data-detail="${focus.field}"]`)?.scrollIntoView?.({ block: 'center' });
  }, [focus, options]);

  /** Change view in place: the sheet starts again at its top, and focus moves into the view now shown. */
  const show = (next: FixView) => {
    setView(next);
    requestAnimationFrame(() => {
      panel.current?.closest('.sheet')?.scrollTo?.({ top: 0 });
      const into = next === 'list' ? back.current ?? list.current
        : panel.current?.querySelector<HTMLElement>(phone ? '.fix-say' : '.fix-say textarea');
      into?.focus({ preventScroll: true });
    });
  };

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
  const drawing = item.illustration_url && <img className="fix-drawing" src={item.illustration_url} alt={`${alt}, drawing as it is now`} />;
  const link = buttonClass({ variant: 'link', className: 'fix-switch' });
  return (
    <div className="fix" ref={panel}>
      {disabled && <p className="muted">{OFFLINE}</p>}
      {!disabled && opening.canSay && (
        <div hidden={view !== 'say'}>
          <SayIt item={item} drawing={drawing} autofocus={opening.autofocus} onSaved={(saved, saidAs) => {
            onSaved(saved, saidAs);
            onDone();
          }} onDrawInstead={item.additions ? (text) => setHanded({ text, at: Date.now() }) : undefined} />
          <button type="button" className={link} onClick={() => show('list')}>Change the details one by one</button>
          <AddToDrawing item={item} given={handed} disabled={disabled} onSaved={onSaved} onError={onError} />
        </div>
      )}
      {!disabled && (
        <div className="fix-panel" hidden={view !== 'list'} ref={list} tabIndex={-1} aria-label="The details one by one">
          {opening.canSay && <button ref={back} type="button" className={link} onClick={() => show('say')}>Say what's wrong instead</button>}
          {opening.why && <p className="notice" role="status">{opening.why}</p>}
          <div className="fix-head">
            {drawing}
            <p className="muted">
              Tap a detail to change it. What you set here stays when Claude describes the item again, and can be undone from the history.
            </p>
          </div>
          {describedBy(item.tag_route, item.tagged_at) && <p className="muted fix-note" data-testid="described-by">{describedBy(item.tag_route, item.tagged_at)}</p>}
          {item.trace && <ShoeDrawingFix item={item} disabled={disabled} onSaved={onSaved} onError={onError} />}
          {/* a failed read is said in the app's words, with Try again (as every screen's, `Failed`) */}
          <Failed query={optionsQuery} what="the details" testId="details-failed" />
          {options?.message && <p className="notice">{options.message}</p>}
          {fixable(options).map((g) => (
            <section key={g.id} className="fix-group" aria-label={g.title}>
              <h3 className="chip-group-title">{g.title}</h3>
              <ul className="fix-list">
                {g.details.map((d) => {
                  const on = picking === d.name;
                  return (
                    <li key={d.name} data-detail={d.name}>
                      <button type="button" className={`fix-detail${on ? ' is-on' : ''}`} aria-expanded={on}
                        aria-label={`${detailSummary(d)}${d.own ? ' (set by you)' : ''}`} onClick={() => setPicking(on ? null : d.name)}>
                        <span className="fix-detail-title">{capitalise(d.title)}</span>
                        <span className="fix-detail-value">{d.words}{d.own && <span className="fix-own"> · set by you</span>}</span>
                      </button>
                      {on && !choicesQuery.data && <Failed query={choicesQuery} what={`the choices for the ${d.title}`} testId="choices-failed" />}
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
        </div>
      )}
    </div>
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

/** The box to say what's wrong in a sentence: Claude reads it, says what it understood, and nothing changes until the
 * owner says so. */
function SayIt({ item, drawing, autofocus, onSaved, onDrawInstead }: {
  item: Item; drawing: ReactNode; autofocus: boolean; onSaved: Props['onSaved'];
  /** Hands the sentence to "Add to the drawing" when no detail could show (part of) it; absent for a shoe. */
  onDrawInstead?: (text: string) => void;
}) {
  const field = useId();
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!autofocus) return;
    // after the sheet has taken focus for itself (its own effect runs after this one)
    const frame = requestAnimationFrame(() => box.current?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(frame);
  }, [autofocus]);
  const [text, setText] = useState('');
  const [asking, setAsking] = useState(false);
  const [asked, setAsked] = useState<{ answer: CorrectionAnswer; stamp: string } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const stamp = stampOf(item);
  // what Claude understood is for the item as it was; once the item changes it is no longer offered
  const answer = stillFor(asked?.answer ?? null, asked?.stamp ?? null, stamp);
  const stale = asked !== null && answer === null;
  // The box and its button are off while Claude reads, which drops focus: once it answers, focus goes to what to do
  // next (Make these changes when it understood, else the box again to say it another way), not to the page.
  const make = useRef<HTMLButtonElement>(null);
  const wasAsking = useRef(false);
  useEffect(() => {
    if (wasAsking.current && !asking) {
      const lost = !document.activeElement || document.activeElement === document.body;
      if (lost) (answer?.state === 'understood' ? make.current : box.current)?.focus({ preventScroll: true });
    }
    wasAsking.current = asking;
  }, [asking, answer]);

  const ask = async () => {
    setAsking(true);
    setAsked(null);
    setProblem(null);
    const at = stamp;
    try {
      const got = await api.correct(item.id, text.trim());
      away = claudeAway(got);
      setAsked({ answer: got, stamp: at });
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
      const saved = await api.confirmCorrection(item.id, answer.sentence, confirmedChanges(answer.changes));
      setAsked(null);
      setText('');
      onSaved(saved, 'Changed as you said');
    } catch (e) {
      setAsked(null);
      setProblem((e as ApiError).message);
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="fix-say" tabIndex={-1}>
      <form onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) void ask();
      }}>
        <div className="fix-say-head">
          {drawing}
          <label htmlFor={field} className="fix-say-label">What's wrong with it?</label>
        </div>
        <textarea ref={box} id={field} rows={3} maxLength={500} value={text} placeholder="e.g. it has three buttons" disabled={asking}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => {
            // Enter sends the sentence, as a one-line box did; Shift+Enter starts a new line
            if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return;
            e.preventDefault();
            e.currentTarget.form?.requestSubmit();
          }} />
        <button type="submit" className={`btn fix-ask${answer?.state === 'understood' ? '' : ' btn-primary'}`} disabled={asking || !text.trim()}>{asking && !answer ? 'Asking Claude…' : 'Ask Claude'}</button>
        <p className="muted fix-note">Claude is sent your sentence and the item's description; its photo only if the sentence can't be understood without it.</p>
      </form>
      {problem && <p className="notice notice-warn" role="alert">{problem}</p>}
      {answer?.state === 'understood' && (
        <div className="fix-confirm" role="status">
          <p><strong>Claude understood:</strong></p>
          <ul>{answer.changes.map((c) => <li key={c.name}>{changeLine(c)}</li>)}</ul>
          {answer.not_understood && <p className="muted">Left out: {answer.not_understood}</p>}
          {answer.not_understood && onDrawInstead && (
            <button type="button" className={buttonClass({ variant: 'link', className: 'fix-switch' })}
              onClick={() => onDrawInstead(answer.sentence)}>Have Claude draw what was left out onto the drawing</button>
          )}
          {answer.sent && <p className="muted fix-note">{answer.sent}</p>}
          <div className="row">
            <button ref={make} type="button" className="btn btn-primary btn-small" disabled={asking} onClick={() => void confirm()}>Make these changes</button>
            <button type="button" className="btn btn-small" disabled={asking} onClick={() => { setAsked(null); box.current?.focus(); }}>Cancel</button>
          </div>
        </div>
      )}
      {stale && asked?.answer.state === 'understood' && (
        <p className="notice" role="status">The item changed after Claude read your sentence, so those changes were put aside. Ask again.</p>
      )}
      {answer && answer.state !== 'understood' && (
        <p className="notice" role="status">
          {answer.state === 'not_understood' ? `Nothing was changed. ${answer.not_understood ?? ''}` : answer.message}
        </p>
      )}
      {answer?.state === 'not_understood' && onDrawInstead && (
        <button type="button" className={buttonClass({ variant: 'link', className: 'fix-switch' })}
          onClick={() => onDrawInstead(answer.sentence)}>Have Claude draw it onto the drawing instead</button>
      )}
    </div>
  );
}

/** The "History" fold: every change to the item's description, newest first, each undoable where allowed. */
export function ItemHistory({ item, disabled, onSaved, onError }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const id = item.id;
  const qc = useQueryClient();
  const history = useQuery({ queryKey: queryKeys.history(id), queryFn: () => api.history(id), enabled: open && !disabled });
  const entries: HistoryEntry[] | null = history.data ?? null;

  const undo = async (entry: HistoryEntry) => {
    setBusy(true);
    try {
      const done = await api.undo(id, entry.id);
      qc.setQueryData(queryKeys.history(id), done.history);
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
        {!disabled && <Failed query={history} what="its history" testId="failed-history" />}
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
