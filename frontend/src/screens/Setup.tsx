import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../api';
import { HangerIcon, CheckIcon } from '../components/Icons';
import type { Profile, Settings } from '../types';
import { PhoneAccess } from '../components/PhoneAccess';

const MIN = 8;

export function SetupScreen({ onDone }: { onDone(): Promise<void> }) {
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (a.length < MIN) return setError(`Choose a passphrase of at least ${MIN} characters.`);
    if (a !== b) return setError("The two passphrases don't match. Type the same one twice.");
    setBusy(true);
    setError(null);
    try {
      await api.setup(a);
      await onDone();
    } catch (err) {
      setError((err as ApiError).message);
      setBusy(false);
    }
  }

  return (
    <main className="center-screen">
      <form className="auth-card" onSubmit={submit} noValidate>
        <div className="brand-mark"><HangerIcon /></div>
        <h1>Welcome to Closet</h1>
        <p className="muted">Choose a passphrase. You'll use it to open your closet on this computer and on your phone.</p>
        <label className="field">
          <span>Passphrase</span>
          <input type="password" autoComplete="new-password" value={a} autoFocus onChange={(e) => setA(e.target.value)}
            aria-describedby="pass-hint" />
        </label>
        <p className="hint" id="pass-hint">At least {MIN} characters. A few unrelated words works well.</p>
        <label className="field">
          <span>Type it again</span>
          <input type="password" autoComplete="new-password" value={b} onChange={(e) => setB(e.target.value)} />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? 'Setting up…' : 'Set passphrase'}</button>
      </form>
    </main>
  );
}

export function ReadyScreen({ onChoose }: { onChoose(profile: Profile): Promise<void> }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [busy, setBusy] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings().then(setSettings).catch(() => undefined);
  }, []);

  async function choose(p: Profile) {
    setBusy(p);
    try {
      await onChoose(p);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  return (
    <main className="center-screen">
      <div className="auth-card">
        <div className="brand-mark brand-mark-ok"><CheckIcon /></div>
        <h1>You're set</h1>
        <p className="muted">Your passphrase is saved. Everything stays on this computer.</p>
        <section className="ready-phone">
          <h2>Use it from your iPhone</h2>
          <PhoneAccess phone={settings?.phone ?? null} />
        </section>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="stack">
          <button className="btn btn-primary btn-block" onClick={() => choose('main')} disabled={!!busy}>Start with my own closet</button>
          <button className="btn btn-block" onClick={() => choose('demo')} disabled={!!busy}>
            {busy === 'demo' ? 'Opening the demo…' : 'Open the demo closet'}
          </button>
        </div>
      </div>
    </main>
  );
}
