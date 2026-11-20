import { useRef, useState, type FormEvent } from 'react';
import { canSay, MAX_SAY, rememberWords, savedLine, type RememberThing, type TalkTurn } from '../today';
import { CheckIcon } from './Icons';
import { Button } from './ui';
import './Talk.css';

/** What a conversation with Claude is called where it is shown: the list, the box and its hint, and the box's id. */
export interface TalkWords {
  list: string;
  box: string;
  placeholder: string;
  id: string;
}

export interface TalkProps {
  turns: TalkTurn[];
  /** The message Claude is answering now, or null. */
  answering: string | null;
  /** Sends a message; resolves to why it was not sent, or null. */
  onSay(text: string): Promise<string | null>;
  /** Keeps (`save`) or not a thing Claude offered to remember; resolves to why it could not, or null. */
  onSettle(turnId: string, index: number, save: boolean): Promise<string | null>;
  /** Takes back a thing kept; resolves to why it could not, or null. */
  onUndo(turnId: string, index: number): Promise<string | null>;
}

/**
 * Talking to Claude: the day's messages and Claude's answers, the things it offered to remember (kept only on a tap,
 * and taken back with Undo), and the box to write in. Shared by Today (about the outfits on the page) and Settings
 * (about your style). Read-only when `locked` (offline, or a copy saved earlier), with `lockedTitle` saying why.
 */
export function Talk({ turns, answering, onSay, onSettle, onUndo, locked, busy, words, lockedTitle }: TalkProps & {
  locked: boolean; busy: boolean; words: TalkWords; lockedTitle?: string;
}) {
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  // while a message is sent or answered (or the outfits are being asked for) nothing more can be sent; the box is
  // read-only rather than disabled then, so it keeps the focus for the next message
  const held = sending || busy || !!answering || turns.some((t) => t.state === 'working');
  const title = locked ? lockedTitle : undefined;
  const errorId = `${words.id}-error`;

  async function send(what: string, fromBox: boolean) {
    if (!canSay(what) || held || locked) return;
    // the focus stays in the box (it is read-only, not disabled, while Claude answers), ready for the next message
    if (fromBox) box.current?.focus();
    setSending(true);
    setError(null);
    const problem = await onSay(what.trim());
    setSending(false);
    if (problem) setError(problem);
    else if (fromBox) setText('');
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void send(text, true);
  }

  return (
    <div className="talk">
      <div aria-live="polite">
        {turns.length > 0 && (
          <ol className="talk-list" aria-label={words.list} data-testid="talk">
            {turns.map((t, at) => (
              <li key={t.id} className="talk-turn" data-testid="talk-turn">
                <div className="talk-said">
                  <span className="talk-who">You</span>
                  <p>{t.said}</p>
                </div>
                {t.state === 'working' && !locked && (
                  <p className="talk-answering muted" role="status">
                    <span className="talk-mark" aria-hidden="true"><span /><span /><span /></span>
                    Claude is answering…
                  </p>
                )}
                {t.state === 'ready' && t.reply && (
                  <div className="talk-reply">
                    <span className="talk-who">Claude</span>
                    <p>{t.reply}</p>
                  </div>
                )}
                {t.state === 'ready' && t.remember.map((thing, i) => (
                  <Keep key={i} thing={thing} locked={locked} title={title}
                    onSettle={(save) => onSettle(t.id, i, save)} onUndo={() => onUndo(t.id, i)} />
                ))}
                {t.state === 'failed' && (
                  <div className="talk-failed">
                    <p>{t.message}</p>
                    {/* only the newest message can be sent again: an earlier one has been followed by another */}
                    {at === turns.length - 1 && (
                      <Button small disabled={locked || held} title={title} onClick={() => void send(t.said, false)}>Send again</Button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
      <form className="talk-say" onSubmit={submit}>
        <label className="talk-say-label" htmlFor={words.id}>{words.box}</label>
        <div className="talk-say-row">
          <textarea id={words.id} ref={box} rows={2} maxLength={MAX_SAY} value={text}
            placeholder={words.placeholder} disabled={locked} title={title}
            readOnly={!locked && held} aria-disabled={!locked && held ? true : undefined}
            aria-invalid={error ? true : undefined} aria-describedby={error ? errorId : undefined}
            onChange={(e) => {
              setText(e.target.value);
              if (error) setError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void send(text, true);
              }
            }} />
          <Button variant="primary" type="submit" disabled={locked || held || !canSay(text)} title={title}>Send</Button>
        </div>
        {error && <p className="form-error talk-say-error" id={errorId} role="alert">{error}</p>}
      </form>
    </div>
  );
}

/** A thing Claude offered to remember: kept only when the owner says so, and taken back with Undo. */
function Keep({ thing, locked, title, onSettle, onUndo }: {
  thing: RememberThing; locked: boolean; title?: string; onSettle(save: boolean): Promise<string | null>; onUndo(): Promise<string | null>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(call: () => Promise<string | null>) {
    setBusy(true);
    setError(null);
    const problem = await call();
    setBusy(false);
    if (problem) setError(problem);
  }
  if (thing.state === 'dismissed') return null;
  const failed = error && <p className="form-error talk-keep-error" role="alert">{error}</p>;
  if (thing.state === 'saved') {
    return (
      <div className="talk-kept">
        <p className="talk-kept-line" data-testid="talk-kept"><CheckIcon />{savedLine(thing)}</p>
        <Button small variant="ghost" disabled={busy || locked} title={title} onClick={() => void run(onUndo)}>Undo</Button>
        {failed}
      </div>
    );
  }
  const words = rememberWords(thing);
  return (
    <div className="talk-keep" role="group" aria-label={words.question} data-testid="talk-keep">
      <p className="talk-keep-question">{words.question}</p>
      <p className="talk-keep-text"><q>{thing.text}</q></p>
      <div className="talk-keep-actions">
        <Button small disabled={busy || locked} title={title} onClick={() => void run(() => onSettle(true))}>{words.save}</Button>
        <Button small variant="ghost" disabled={busy || locked} title={title} onClick={() => void run(() => onSettle(false))}>No thanks</Button>
      </div>
      {failed}
    </div>
  );
}
