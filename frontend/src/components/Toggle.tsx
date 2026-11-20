import type { ReactNode } from 'react';
import type { Line } from '../settingsLines';

/** A switch with its label and, at most, a one-line hint. */
export function Toggle({ label, hint, checked, disabled, onChange }: {
  label: string; hint?: string; checked: boolean; disabled?: boolean; onChange(on: boolean): void;
}) {
  return (
    <label className="toggle">
      <span className="toggle-text">
        <span className="toggle-label">{label}</span>
        {hint && <span className="hint">{hint}</span>}
      </span>
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track" aria-hidden="true"><span className="toggle-thumb" /></span>
    </label>
  );
}

const TONE_CLASS = { ok: 'state-ready', problem: 'state-problem', waiting: 'state-waiting', quiet: '' } as const;

/** One status line from `settingsLines.ts`: a dot (green when all is well, red on a problem) and the sentence. */
export function StatusLine({ line, testId, children }: { line: Line; testId?: string; children?: ReactNode }) {
  return (
    <p className={`state-line ${TONE_CLASS[line.tone]}`} data-testid={testId} aria-busy={line.tone === 'waiting' || undefined}
      role={line.tone === 'problem' ? 'status' : undefined}>
      {line.tone !== 'quiet' && <span className="state-dot" aria-hidden="true" />}
      <span>{line.text}{children}</span>
    </p>
  );
}
