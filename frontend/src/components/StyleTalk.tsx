import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { api } from '../api';
import { queryKeys } from '../queryKeys';
import { refreshStyle } from '../settings';
import { lineText, talkPoll } from '../style';
import type { RememberHow } from '../today';
import type { QuestionAnswer, StyleLine, StyleQuestion, StyleTalk as Conversation } from '../types';
import { CheckIcon } from './Icons';
import { Talk, type TalkWords } from './Talk';
import { Button, Failed, Notice } from './ui';

const STYLE_TALK: TalkWords = {
  list: 'Your conversation with Claude about your style', box: 'Tell Claude about your style',
  placeholder: 'I run warm. No ties. Navy rather than black…', id: 'style-say-text',
};
const OFFLINE = 'Needs Nines on your computer to be reachable';

/**
 * Talking to Claude about your style (Settings, Your style): the questions the stylist cannot infer, one at a time,
 * while nothing has been said today, and the conversation, whose lines to keep are offered and kept on a tap. What is
 * kept lands in Your style, which the card behind shows.
 */
export function StyleTalk({ offline }: { offline: boolean }) {
  const qc = useQueryClient();
  const talk = useQuery({
    queryKey: queryKeys.styleTalk(), queryFn: api.styleTalk, enabled: !offline, staleTime: 0,
    refetchInterval: (q) => talkPoll(q.state.data),
  });
  // the answer just given to a question, shown with Undo above the next question
  const [answered, setAnswered] = useState<{ question: StyleQuestion; line: StyleLine | null } | null>(null);
  const data = talk.data;
  if (!data) {
    return talk.error ? <Failed query={talk} what="the conversation about your style" testId="failed-style-talk" />
      : <p className="muted" role="status">Opening the conversation…</p>;
  }
  const put = (next: Conversation) => qc.setQueryData(queryKeys.styleTalk(), next);
  const locked = offline || !!data.refused;

  async function say(text: string): Promise<string | null> {
    try {
      put(await api.sayStyle(text));
      setAnswered(null);
      return null;
    } catch (e) {
      return (e as Error).message || "Your message wasn't sent. Try again.";
    }
  }

  async function settle(turnId: string, index: number, how: RememberHow): Promise<string | null> {
    try {
      const thing = await api.rememberStyle(turnId, index, how);
      qc.setQueryData<Conversation>(queryKeys.styleTalk(), (c) => c && {
        ...c, turns: c.turns.map((t) => (t.id !== turnId ? t : { ...t, remember: t.remember.map((r, i) => (i === index ? thing : r)) })),
      });
      if (how.save || how.undo) await refreshStyle(qc);
      return null;
    } catch (e) {
      return (e as Error).message || 'That could not be saved. Try again.';
    }
  }

  async function onAnswer(question: StyleQuestion, call: () => Promise<QuestionAnswer>): Promise<string | null> {
    try {
      const got = await call();
      setAnswered({ question, line: got.line });
      qc.setQueryData<Conversation>(queryKeys.styleTalk(), (c) => c && { ...c, question: got.question });
      if (got.line) await refreshStyle(qc);
      return null;
    } catch (e) {
      return (e as Error).message || 'That could not be saved. Try again.';
    }
  }

  async function undoAnswer(): Promise<string | null> {
    if (!answered) return null;
    try {
      const got = await api.undoQuestion(answered.question.id);
      setAnswered(null);
      qc.setQueryData<Conversation>(queryKeys.styleTalk(), (c) => c && { ...c, question: got.question });
      await refreshStyle(qc);
      return null;
    } catch (e) {
      return (e as Error).message || 'That could not be taken back. Try again.';
    }
  }

  return (
    <div className="style-talk" data-testid="style-talk">
      {data.refused && <Notice as="p" tone="warning" role="status">{data.refused}</Notice>}
      {data.turns.length === 0 && (
        <p className="hint">Say how you like to dress, in your own words. Claude offers lines to keep, and nothing is kept unless you save it.</p>
      )}
      {answered && <Answered answered={answered} locked={offline} onUndo={undoAnswer} />}
      {data.question && data.turns.length === 0 && (
        <Question key={data.question.id} question={data.question} locked={offline}
          onAnswer={(how) => onAnswer(data.question!, () => api.answerQuestion(data.question!.id, how))} />
      )}
      <Talk turns={data.turns} answering={data.answering} onSay={say} locked={locked} busy={false} words={STYLE_TALK}
        lockedTitle={offline ? OFFLINE : data.refused ?? undefined}
        onSettle={(id, i, save) => settle(id, i, { save })} onUndo={(id, i) => settle(id, i, { undo: true })} />
    </div>
  );
}

/** The answer just given (or the question skipped), with Undo. */
function Answered({ answered, locked, onUndo }: {
  answered: { question: StyleQuestion; line: StyleLine | null }; locked: boolean; onUndo(): Promise<string | null>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="style-answered talk" data-testid="style-answered">
      <div className="talk-kept">
        <p className="talk-kept-line"><CheckIcon />
          {answered.line ? `Saved to Your style: “${lineText(answered.line.text)}”` : 'Skipped. You won’t be asked that again.'}
        </p>
        <Button small variant="ghost" disabled={busy || locked} onClick={async () => {
          setBusy(true);
          setError(await onUndo());
          setBusy(false);
        }}>Undo</Button>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}

/** One question the stylist cannot infer: a tap on an answer, your own words, or Skip. */
function Question({ question, locked, onAnswer }: {
  question: StyleQuestion; locked: boolean; onAnswer(how: { choice: string } | { text: string } | { skip: true }): Promise<string | null>;
}) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (how: { choice: string } | { text: string } | { skip: true }) => {
    setBusy(true);
    setError(null);
    const problem = await onAnswer(how);
    setBusy(false);
    if (problem) setError(problem);
  };
  const own = `style-question-${question.id}`;
  return (
    <section className="style-question" aria-labelledby={`${own}-ask`} data-testid="style-question">
      <h3 id={`${own}-ask`}>{question.ask}</h3>
      <p className="hint">{question.why}</p>
      <div className="style-question-choices">
        {question.choices.map((c) => (
          <Button key={c} small disabled={busy || locked} onClick={() => void run({ choice: c })}>{c}</Button>
        ))}
      </div>
      <form className="style-question-own" onSubmit={(e: FormEvent) => {
        e.preventDefault();
        if (text.trim()) void run({ text });
      }}>
        <label className="field">
          <span>Or in your own words</span>
          <input value={text} maxLength={200} disabled={busy || locked} onChange={(e) => setText(e.target.value)} />
        </label>
        <div className="style-question-actions">
          <Button small type="submit" disabled={busy || locked || !text.trim()}>Save my answer</Button>
          <Button small variant="ghost" disabled={busy || locked} onClick={() => void run({ skip: true })}>Skip</Button>
        </div>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
    </section>
  );
}
