import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, connection, UNREACHABLE } from './api';
import { Shell } from './Shell';
import { ClosetProvider } from './store';
import type { Profile, Session } from './types';
import { navigate } from './router';
import { ClosedScreen, RefusedScreen, UnreachableScreen, LoadingScreen } from './screens/Static';

type Toast = { id: number; message: string; kind: 'ok' | 'error' };

/** How long a toast stays: long enough to read a fault's sentence; a short "Saved". */
export const TOAST_MS = 1800;
export const TOAST_ERROR_MS = 5000;

/** Whether an error is the door turning this device away (backend/closet/gate.py), not the computer being out of reach. */
export function refusedBy(e: unknown): string | null {
  return e instanceof ApiError && (e.status === 401 || e.status === 403) ? e.message : null;
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  // the sentence the door answered with, when it turned this device away (a page kept by the service worker, say)
  const [refused, setRefused] = useState<string | null>(null);
  const [closed, setClosed] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastSeq = useRef(0);

  const loadSession = useCallback(async () => {
    try {
      const s = await api.session();
      setSession(s);
      setUnreachable(false);
      setRefused(null);
    } catch (e) {
      const why = refusedBy(e);
      if (why) setRefused(why);
      else setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  // Not reachable and nothing saved: keep trying quietly.
  useEffect(() => {
    if (!unreachable) return;
    const t = window.setInterval(() => void loadSession(), 5000);
    return () => window.clearInterval(t);
  }, [unreachable, loadSession]);

  // A 401 on any call means this device's way in no longer holds (the window's key, Cloudflare's sign-in, Tailscale's
  // word): say what the server said, instead of a page whose every call fails.
  useEffect(() => connection.onUnauthorized((message) => setRefused(message)), []);

  // At most one toast of each kind: a new one takes the place of the last, so several faults in a row are one toast
  // (the latest), not a pile. Where it sits, covering nothing you are about to tap: styles.css, "toasts".
  const toast = useCallback((message: string, kind: 'ok' | 'error' = 'ok') => {
    const id = ++toastSeq.current;
    setToasts((t) => [...t.filter((x) => x.kind !== kind), { id, message, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? TOAST_ERROR_MS : TOAST_MS);
  }, []);

  const onProfile = useCallback((profile: Profile) => {
    setSession((s) => (s ? { ...s, profile } : s));
    navigate('/');
  }, []);

  const onQuit = useCallback(async () => {
    await api.quit();
    setClosed(true);
  }, []);

  let screen;
  if (closed) screen = <ClosedScreen />;
  else if (refused) screen = <RefusedScreen message={refused} onReload={() => window.location.reload()} />;
  else if (!session) screen = unreachable ? <UnreachableScreen message={UNREACHABLE} onRetry={loadSession} /> : <LoadingScreen />;
  else {
    screen = (
      <ClosetProvider key={session.profile} profile={session.profile} onProfile={onProfile} onQuit={onQuit} toast={toast}>
        <Shell version={session.version} />
      </ClosetProvider>
    );
  }

  return (
    <>
      {screen}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>{t.message}</div>
        ))}
      </div>
    </>
  );
}
