import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api } from '../api';
import { queryKeys } from '../queryKeys';
import { NinesMark } from './NinesMark';
import { Button, Markdown, Notice, SegmentedControl } from './ui';
import { formatSize } from '../labels';
import { busyLine, checkedLine, lastInstallLine, MODES, showBanner, updates, useUpdates, type UpdateMode, type UpdateStatus } from '../updates';
import { updatesLine } from '../settingsLines';
import { StatusLine } from './Toggle';

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

/** "Nines 0.3.0 is ready · Install", on every screen in "Ask me first" mode. */
export function UpdateBanner({ offline, toast }: { offline: boolean; toast: Toast }) {
  const { status, installing } = useUpdates();
  const [busy, setBusy] = useState(false);
  if (offline || installing || !showBanner(status) || !status?.available) return null;
  return (
    <Notice role="status" testId="update-banner" className="update-notice"
      action={<Button variant="primary" small disabled={busy} onClick={async () => {
        setBusy(true);
        try {
          await updates.install(toast);
        } catch (e) {
          toast((e as Error).message, 'error');
        } finally {
          setBusy(false);
        }
      }}>Install</Button>}>
      <strong>Nines {status.available.version} is ready</strong>
      <span className="ribbon-more"> · your closets are backed up before it is installed.</span>
    </Notice>
  );
}

/** Covers the page while Nines restarts as the new version; the page reloads by itself once it answers. */
export function Restarting() {
  const { installing } = useUpdates();
  if (!installing) return null;
  return (
    <div className="restarting" role="alertdialog" aria-modal="true" aria-labelledby="restarting-title" aria-describedby="restarting-text">
      <NinesMark className="nines-mark-screen" />
      <h1 id="restarting-title">{installing.late ? "Nines hasn't come back yet" : 'Nines is restarting'}</h1>
      {installing.late ? (
        <>
          <p id="restarting-text" className="muted narrow">
            It is taking longer than it should. If the Nines icon is not near the clock or in the menu bar, open Nines again on your computer. Your closets were backed up first.
          </p>
          <Button variant="primary" onClick={() => window.location.reload()}>Try again</Button>
        </>
      ) : (
        <p id="restarting-text" className="muted narrow" aria-busy="true">
          Installing Nines {installing.to}. This page reconnects by itself in a moment.
        </p>
      )}
    </div>
  );
}

/** While something happens in the background (a download, a backup), asks again every few seconds. */
function useWhileBusy(offline: boolean) {
  const { status, installing } = useUpdates();
  const busy = status?.busy ?? null;
  useEffect(() => {
    if (offline || !busy || installing) return;
    const t = window.setInterval(() => void updates.refresh(), 2000);
    return () => window.clearInterval(t);
  }, [offline, busy, installing]);
}

/**
 * The Updates group on the Settings page: one line ("Nines 0.4.0 · up to date", "Nines 0.4.1 is ready to
 * install."), what is new folded under it, and Install. Its status comes with the settings, which put it in the
 * page's one copy; how updates are fetched and Check now are on the Advanced screen (`UpdatesManage`).
 */
export function UpdatesLine({ offline, toast, version }: { offline: boolean; toast: Toast; version: string }) {
  const { status, installing } = useUpdates();
  const [installBusy, setInstallBusy] = useState(false);
  useWhileBusy(offline);
  const line = updatesLine(status, version, offline);
  const release = status?.available ?? null;
  const testId = status?.problem ? 'update-problem' : release ? 'update-available' : 'update-line';

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

  return (
    <>
      <StatusLine line={line} testId={testId} />
      {release?.notes.trim() && (
        <details className="more update-notes" data-testid="update-notes">
          <summary>What's new in {release.version}</summary>
          <Markdown text={release.notes} />
        </details>
      )}
      {line.action === 'install' && (
        <div className="settings-actions">
          <Button variant="primary" disabled={offline || !!status?.busy || !!installing || installBusy} onClick={installNow}>Install now</Button>
          <span className="hint">{status?.download_size ? `${formatSize(status.download_size)}. ` : ''}Your closets are backed up first.</span>
        </div>
      )}
      {line.action === 'download' && release && (
        <p className="hint"><a href={release.page} target="_blank" rel="noreferrer noopener">Download it from the release page</a></p>
      )}
    </>
  );
}

/** How updates are fetched, Check now, and how the last check and install went: on the Advanced screen. */
export function UpdatesManage({ offline, toast }: { offline: boolean; toast: Toast }) {
  const qc = useQueryClient();
  const { status, installing } = useUpdates();
  const answered = (s: UpdateStatus) => {
    updates.set(s);
    qc.setQueryData(queryKeys.updates(), s);
  };
  const [checking, setChecking] = useState(false);
  useWhileBusy(offline);

  if (!status) {
    return <p className="hint">{offline ? "Updates can't be checked while you're offline." : 'This copy of Nines has no updater.'}</p>;
  }

  async function choose(mode: UpdateMode) {
    const before = status;
    if (!before) return;
    updates.set({ ...before, mode });
    try {
      answered(await api.setUpdateMode(mode));
      toast('Saved');
    } catch (e) {
      updates.set(before);
      toast((e as Error).message, 'error');
    }
  }

  async function checkNow() {
    setChecking(true);
    try {
      answered(await api.checkUpdates());
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setChecking(false);
    }
  }

  const busy = status.busy;
  const last = lastInstallLine(status);
  const locked = offline || !!busy || !!installing;
  const mode = MODES.find((m) => m.value === status.mode);
  return (
    <>
      <dl className="facts">
        <dt>This version</dt>
        <dd data-testid="update-version">{status.version}</dd>
      </dl>
      <p className="state-line" data-testid="update-checked">{checkedLine(status)}</p>
      {status.check_error && <p className="hint" data-testid="update-check-error">{status.check_error}</p>}
      {last && (status.last_install?.ok
        ? <p className="hint" data-testid="update-last">{last}</p>
        : <Notice as="p" tone="error" testId="update-last">{last}</Notice>)}
      <div className="update-modes">
        <p className="update-modes-label">When a new version is out</p>
        <SegmentedControl label="When a new version is out" options={MODES.map((m) => ({ value: m.value, label: m.short }))}
          small value={status.mode} onChange={(m) => { if (!offline && m !== status.mode) void choose(m); }} className="update-mode-choice" />
        <p className="hint" data-testid="update-mode-hint"><strong>{mode?.label}.</strong> {mode?.hint}</p>
      </div>
      <Button disabled={locked || checking} onClick={checkNow}>{checking ? 'Checking…' : 'Check now'}</Button>
      {busy && !installing && <p className="state-line" role="status">{busyLine(busy)}</p>}
      {status.available && (
        <p className="hint"><a href={status.available.page} target="_blank" rel="noreferrer noopener">The release page</a></p>
      )}
    </>
  );
}
