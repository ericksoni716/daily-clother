import { dots, markLabel, settingsFix, stepWords, stripNote } from '../progress';
import { Link } from '../router';
import type { Progress } from '../types';
import { WarnIcon } from './Icons';
import './Progress.css';

/**
 * The item page's one line about the work on it, laid over the bottom of its picture so nothing moves when it comes
 * and goes: three dots for the three steps, what is happening now, and where it runs and how long it takes (or why it
 * waits). Shown only while the work is on its way; a failure has its own notice, with Try again.
 */
export function ProgressStrip({ progress }: { progress: Progress }) {
  return (
    <div className={`progress-strip is-${progress.state}`} role="status" data-testid="progress-strip">
      <div className="progress-strip-head">
        <span className="progress-dots" aria-hidden="true">
          {dots(progress).map((d, i) => <span key={i} className={`progress-dot is-${d}`} />)}
        </span>
        <span className="progress-step">{stepWords(progress)}</span>
      </div>
      <p className="progress-words" data-testid="progress-words">{progress.words}</p>
      <p className="progress-note">
        {stripNote(progress)}
        {settingsFix(progress) && <> <Link to="/settings">Open Settings</Link></>}
      </p>
    </div>
  );
}

/** A small round mark with the step's number: turning while it is being done, still while it is next in line, a
 * dashed ring while it waits, a warning when it failed. Its words are there for a screen reader; `small` (before the
 * same words in a row) is only a picture. */
export function StepMark({ progress, small }: { progress: Progress; small?: boolean }) {
  return (
    <span className={`step-mark is-${progress.state}${small ? ' is-small' : ''}`} data-testid="step-mark" title={progress.words}
      aria-hidden={small || undefined}>
      {progress.state === 'failed' ? <WarnIcon aria-hidden="true" /> : <span aria-hidden="true">{progress.step}</span>}
      {!small && <span className="visually-hidden">{progress.state === 'failed' ? `${progress.words}.` : markLabel(progress)}</span>}
    </span>
  );
}
