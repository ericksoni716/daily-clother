import { useEffect, useState } from 'react';
import { api } from '../api';
import { useAsOpened } from '../steady';
import type { RestoreNotice as Told } from '../types';
import { Button, Notice } from './ui';

type Toast = (m: string, k?: 'ok' | 'error') => void;

/** "A restore was interrupted; …": what Nines did about it when it started, on every screen until the owner says OK. */
export function RestoreNotice({ offline, toast, screen }: { offline: boolean; toast: Toast; screen: string }) {
  const [told, setNotice] = useState<Told | null>(null);
  // shown from the next screen on when it arrives after this one opened (`useAsOpened`); gone at once on OK
  const [notice, take] = useAsOpened(told, screen);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (offline) return;
    let live = true;
    api.restoreNotice().then((r) => live && setNotice(r.notice)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [offline]);
  if (!notice) return null;
  return (
    <Notice role="status" tone={notice.outcome === 'finished' ? 'info' : 'warning'} testId="restore-notice" className="update-notice"
      action={<Button small disabled={busy || offline} onClick={async () => {
        setBusy(true);
        try {
          await api.dismissRestoreNotice();
          setNotice(null);
          take();
        } catch (e) {
          toast((e as Error).message, 'error');
        } finally {
          setBusy(false);
        }
      }}>OK</Button>}>
      {notice.message}
    </Notice>
  );
}
