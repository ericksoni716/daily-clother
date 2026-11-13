import { useCallback, useEffect, useRef, useState } from 'react';
import { api, clearSavedData, connection, UNREACHABLE } from './api';
import { Shell } from './Shell';
import { ClosetProvider } from './store';
import type { Profile, Session } from './types';
import { navigate } from './router';
import { SetupScreen, ReadyScreen } from './screens/Setup';
import { LoginScreen } from './screens/Login';
import { forgetLanding } from './landing';
import { ClosedScreen, UnreachableScreen, LoadingScreen } from './screens/Static';

type Toast = { id: number; message: string; kind: 'ok' | 'error' };

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [justSetUp, setJustSetUp] = useState(false);
  const [closed, setClosed] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastSeq = useRef(0);

  const loadSession = useCallback(async () => {
    try {
      const s = await api.session();
      setSession(s);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
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

  // Any 401 means the session ended: go to the login screen.
  useEffect(() => connection.onUnauthorized(() => {
    setSession((s) => (s ? { ...s, authenticated: false } : s));
  }), []);

  const toast = useCallback((message: string, kind: 'ok' | 'error' = 'ok') => {
    const id = ++toastSeq.current;
    setToasts((t) => [...t.filter((x) => x.message !== message), { id, message, kind }].slice(-3));
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 6000 : 1800);
  }, []);

  const onProfile = useCallback((profile: Profile) => {
    setSession((s) => (s ? { ...s, profile } : s));
    navigate('/');
  }, []);

  const onLogout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      await clearSavedData().catch(() => undefined);
      setSession((s) => (s ? { ...s, authenticated: false } : s));
      navigate('/', { replace: true });
    }
  }, []);

  const onQuit = useCallback(async () => {
    await api.quit();
    setClosed(true);
  }, []);

  let screen;
  if (closed) screen = <ClosedScreen />;
  else if (!session) screen = unreachable ? <UnreachableScreen message={UNREACHABLE} onRetry={loadSession} /> : <LoadingScreen />;
  else if (session.setup_required) {
    screen = <SetupScreen onDone={async () => {
      setJustSetUp(true);
      await loadSession();
    }} />;
  } else if (!session.authenticated) {
    screen = <LoginScreen onDone={() => {
      forgetLanding();
      return loadSession();
    }} />;
  } else if (justSetUp) {
    screen = <ReadyScreen onChoose={async (profile) => {
      if (profile === 'demo') await api.setProfile('demo');
      setSession((s) => (s ? { ...s, profile } : s));
      setJustSetUp(false);
      navigate('/', { replace: true });
    }} />;
  } else {
    screen = (
      <ClosetProvider key={session.profile} profile={session.profile} onProfile={onProfile} onLogout={onLogout} onQuit={onQuit} toast={toast}>
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
