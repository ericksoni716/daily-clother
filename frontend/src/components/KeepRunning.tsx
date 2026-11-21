import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api';
import { ACTION_LABEL, KEEP_ABOUT, KEEP_TITLE, keepActions, keepLine, keepPhoneLine, keepPoll, keepShows, portLine, type KeepAction, type KeepBusy } from '../keepRunning';
import { usePoll } from '../queries';
import { queryKeys } from '../queryKeys';
import type { BackgroundState, Settings } from '../types';
import { Button } from './ui';
import { StatusLine } from './Toggle';

/**
 * Windows keeping Nines running, under Phone. On the computer: the status, the port, and Keep Nines running, Start it
 * again or Turn this off. On the phone: one sentence. Nothing where it is not available (a Mac, or run from source).
 */
export function KeepRunning({ state, device, offline }: { state: BackgroundState | undefined; device: 'computer' | 'phone'; offline: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<KeepBusy>(null);
  const [error, setError] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const write = (s: BackgroundState) => qc.setQueryData<Settings>(queryKeys.settings(), (old) => (old ? { ...old, background: s } : old));
  const poll = keepPoll(state, busy);
  usePoll(poll === false ? null : poll, () => {
    api.background().then(write, () => undefined);
  });
  if (!keepShows(state)) return null;
  const s = state!;
  const shown: KeepBusy = busy === 'turning-off' && s.problem ? null : busy;   // Windows' answer is in: say it
  if (device === 'phone') return <p data-testid="keep-running">{keepPhoneLine(s)}</p>;

  async function act(action: KeepAction) {
    setError(null);
    setSaid(null);
    setBusy(action === 'off' ? 'turning-off' : action === 'on' ? 'turning-on' : 'handing-over');
    try {
      const answer = action === 'on' ? await api.backgroundOn() : action === 'off' ? await api.backgroundOff() : await api.backgroundRestart();
      write(answer);
      setSaid(answer.note ?? null);
      if (answer.handing_over) setBusy('handing-over');
      else if (!answer.turning_off) setBusy(null);   // turned off here, by this ordinary copy
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  return (
    <div className="keep-running" data-testid="keep-running">
      <h3 className="keep-running-title">{KEEP_TITLE}</h3>
      <StatusLine line={keepLine(s, shown)} testId="keep-running-status" />
      {!s.on && !shown && <p className="hint">{KEEP_ABOUT}</p>}
      <p className="muted small" data-testid="keep-running-port">{portLine(s)}</p>
      {said && <p data-testid="keep-running-note">{said}</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {keepActions(s, shown).length > 0 && (
        <div className="settings-actions">
          {keepActions(s, shown).map((a) => (
            <Button key={a} small variant={a === 'on' || a === 'restart' ? 'primary' : undefined} disabled={offline} onClick={() => void act(a)}>
              {ACTION_LABEL[a]}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
