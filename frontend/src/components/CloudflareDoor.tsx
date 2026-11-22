import { useEffect, useState, type FormEvent } from 'react';
import { DOOR_ABOUT, DOOR_FIELDS, README_CLOUDFLARE, doorChange, doorChanged, doorStatus, doorTitle, doorValues, type DoorField } from '../cloudflare';
import { useSaveSettings } from '../settings';
import type { CloudflareDoor as Door } from '../types';
import { Fold } from './ui';

/** The door through Cloudflare, folded under Other devices on the computer: what it is, the three values, and Save. */
export function CloudflareDoor({ door, offline, toast }: { door: Door; offline: boolean; toast(message: string, kind?: 'ok' | 'error'): void }) {
  const save = useSaveSettings();
  const [typed, setTyped] = useState<Record<DoorField, string>>(() => doorValues(door));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // what is saved, again once a save (here or elsewhere) changes it; not on every read of the settings, which the
  // computer repeats every few seconds while the phone has no address, so what is being typed is kept
  const { team, aud, host } = door;
  useEffect(() => setTyped(doorValues({ team, aud, host, on: false })), [team, aud, host]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await save(doorChange(typed));
      toast('Saved');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Fold title={doorTitle(door)} className="cloudflare-door" testId="cloudflare-door">
      <p>{DOOR_ABOUT} <a href={README_CLOUDFLARE} target="_blank" rel="noreferrer">The README has the steps.</a></p>
      <p className="muted" data-testid="cloudflare-status">{doorStatus(door)}</p>
      <form onSubmit={submit}>
        {DOOR_FIELDS.map((f) => (
          <label key={f.key} className="field">
            <span>{f.label}</span>
            <input value={typed[f.key]} placeholder={f.placeholder} disabled={offline || busy} spellCheck={false}
              autoCapitalize="off" autoCorrect="off" data-testid={f.key}
              onChange={(e) => setTyped({ ...typed, [f.key]: e.target.value })} />
          </label>
        ))}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn" type="submit" disabled={offline || busy || !doorChanged(door, typed)}>Save</button>
      </form>
    </Fold>
  );
}
