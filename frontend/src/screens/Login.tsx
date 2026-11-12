import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../api';
import { HangerIcon } from '../components/Icons';

export function LoginScreen({ onDone }: { onDone(): Promise<void> | void }) {
  const [pass, setPass] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!pass) {
      setError('Enter your passphrase.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.login(pass);
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
        <h1>Welcome back</h1>
        <p className="muted">Enter your passphrase to open your closet.</p>
        <label className="field">
          <span>Passphrase</span>
          <input type="password" autoComplete="current-password" value={pass} autoFocus
            onChange={(e) => setPass(e.target.value)} aria-invalid={!!error} aria-describedby={error ? 'login-error' : undefined} />
        </label>
        {error && <p className="form-error" id="login-error" role="alert">{error}</p>}
        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? 'Opening…' : 'Open my closet'}</button>
        <p className="muted small">Forgot it? The README's "Forgotten passphrase" section shows how to set a new one. Your clothes stay as they are.</p>
      </form>
    </main>
  );
}
