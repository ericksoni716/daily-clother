import { useEffect, useId, useState } from 'react';
import { api } from '../api';
import { HangerIcon } from './Icons';
import { formatSize } from '../labels';
import { availableLine, busyLine, checkedLine, lastInstallLine, MODES, showBanner, updates, useUpdates, type UpdateMode } from '../updates';

type Toast = (m: string, k?: 'ok' | 'error') => void;

/** Asks how updates stand when the page opens, when it is back online, and every half hour. */
export function useUpdateStatus(offline: boolean) {
  useEffect(() => {
    if (offline) return;
    void updates.refresh();
    const t = window.setInterval(() => void updates.refresh(), 30 * 60 * 1000);
    return () => window.clearInterval(t);
  }, [offline]);
}

/** "Closet 0.3.0 is ready · Install", on every screen in "Ask me first" mode. */
export function UpdateBanner({ offline, toast }: { offline: boolean; toast: Toast }) {
  const { status, installing } = useUpdates();
  const [busy, setBusy] = useState(false);
  if (offline || installing || !showBanner(status) || !status?.available) return null;
  return (
    <div className="ribbon ribbon-update" role="status" data-testid="update-banner">
      <span><strong>Closet {status.available.version} is ready</strong><span className="ribbon-more"> · your closets are backed up before it is installed.</span></span>
      <button className="btn btn-small btn-on-accent" disabled={busy} onClick={async () => {
        setBusy(true);
        try {
          await updates.install(toast);
        } catch (e) {
          toast((e as Error).message, 'error');
        } finally {
          setBusy(false);
        }
      }}>Install</button>
    </div>
  );
}

/** Covers the page while Closet restarts as the new version; the page reloads by itself once it answers. */
export function Restarting() {
  const { installing } = useUpdates();
  if (!installing) return null;
  return (
    <div className="restarting" role="alertdialog" aria-modal="true" aria-labelledby="restarting-title" aria-describedby="restarting-text">
      <div className="brand-mark"><HangerIcon /></div>
      <h1 id="restarting-title">{installing.late ? "Closet hasn't come back yet" : 'Closet is restarting'}</h1>
      {installing.late ? (
        <>
          <p id="restarting-text" className="muted narrow">
            It is taking longer than it should. If Closet's icon is not near the clock or in the menu bar, open Closet again on your computer. Your closets were backed up first.
          </p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>Try again</button>
        </>
      ) : (
        <p id="restarting-text" className="muted narrow" aria-busy="true">
          Installing Closet {installing.to}. This page reconnects by itself in a moment.
        </p>
      )}
    </div>
  );
}

/** The Updates section in Settings. */
export function UpdatesSection({ offline, toast }: { offline: boolean; toast: Toast }) {
  const { status, installing } = useUpdates();
  const [checking, setChecking] = useState(false);
  const [installBusy, setInstallBusy] = useState(false);
  const group = useId();

  // while something happens in the background (a download, a backup), ask again every few seconds
  const busy = status?.busy ?? null;
  useEffect(() => {
    if (offline || !busy || installing) return;
    const t = window.setInterval(() => void updates.refresh(), 2000);
    return () => window.clearInterval(t);
  }, [offline, busy, installing]);

  if (!status) {
    return <p className="hint">{offline ? "Updates can't be checked while you're offline." : 'Finding out about new versions…'}</p>;
  }

  async function choose(mode: UpdateMode) {
    try {
      updates.set(await api.setUpdateMode(mode));
      toast('Saved');
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }

  async function checkNow() {
    setChecking(true);
    try {
      updates.set(await api.checkUpdates());
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setChecking(false);
    }
  }

  async function installNow() {
    setInstallBusy(true);
    try {
      await updates.install(toast);
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setInstallBusy(false);
    }
  }

  const release = status.available;
  const last = lastInstallLine(status);
  const locked = offline || !!busy || !!installing;
  return (
    <>
      <dl className="facts">
        <dt>This version</dt>
        <dd data-testid="update-version">{status.version}</dd>
      </dl>
      <p className="state-line" data-testid="update-checked">{checkedLine(status)}</p>
      {status.check_error && <p className="hint" data-testid="update-check-error">{status.check_error}</p>}
      {last && <p className={status.last_install?.ok ? 'hint' : 'form-error'} data-testid="update-last">{last}</p>}
      <fieldset className="update-modes" disabled={offline}>
        <legend>When a new version is out</legend>
        {MODES.map((m) => (
          <label key={m.value} className="update-mode">
            <input type="radio" name={group} value={m.value} checked={status.mode === m.value} onChange={() => void choose(m.value)} />
            <span className="toggle-text">
              <span className="toggle-label">{m.label}</span>
              <span className="hint">{m.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <button className="btn" disabled={locked || checking} onClick={checkNow}>{checking ? 'Checking…' : 'Check now'}</button>
      {busy && !installing && <p className="state-line" role="status">{busyLine(busy)}</p>}
      {availableLine(status) && <p className="state-line" data-testid="update-available"><strong>{availableLine(status)}</strong></p>}
      {release && (
        <div className="update-release" data-testid="update-release">
          {release.notes && <p className="update-notes" aria-label={`What's new in ${release.version}`}>{release.notes}</p>}
          <p className="hint">
            <a href={release.page} target="_blank" rel="noreferrer noopener">The release page</a>
            {status.download_size && status.can_install ? ` · ${formatSize(status.download_size)} download` : ''}
          </p>
          {status.problem && <p className="form-error" role="alert" data-testid="update-problem">{status.problem}</p>}
          {status.can_install && (
            <>
              <button className="btn btn-primary" disabled={locked || installBusy} onClick={installNow}>Install now</button>
              <p className="hint">Your closets are backed up first. Closet restarts as the new version and this page reconnects by itself.</p>
            </>
          )}
        </div>
      )}
      {!status.can_install && !release && (
        <p className="hint">This copy of Closet can't replace itself; new versions are only reported here, with a link to download them.</p>
      )}
    </>
  );
}
