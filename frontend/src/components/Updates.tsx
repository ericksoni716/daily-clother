import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api } from '../api';
import { queryKeys } from '../queryKeys';
import { useAsOpened } from '../steady';
import { NinesMark } from './NinesMark';
import { Button, Markdown, Notice, SegmentedControl } from './ui';
import { formatSize } from '../labels';
import { checkAnswer, checkedLine, lastInstallLine, MODES, showBanner, updates, useUpdates, type UpdateMode, type UpdateStatus } from '../updates';
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
export function UpdateBanner({ offline, toast, screen }: { offline: boolean; toast: Toast; screen: string }) {
  const { status: now, installing } = useUpdates();
  const [busy, setBusy] = useState(false);
  // a version that becomes ready while you read waits for the next screen (`useAsOpened`); one that goes away
  // (installed, or no longer offered) goes at once
  const [opened] = useAsOpened(showBanner(now) ? now : null, screen);
  const status = showBanner(now) ? opened : null;
  if (offline || installing || !status?.available) return null;
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
 * The Updates group on the Settings page: every fact and action about updates, each once. The line ("Nines 0.4.0 · up
 * to date", "Nines 0.4.1 is ready to install."), when it last looked with Check now beside it, the answer to a press
 * under them, what is new folded, Install now, the release page and how the last install went. Its status comes
 * with the settings, which put it in the page's one copy. Only the choice of when to install is on Advanced
 * (`UpdatesMode`). A copy with no updater shows its version and nothing to press.
 */
export function UpdatesLine({ offline, toast, version }: { offline: boolean; toast: Toast; version: string }) {
  const qc = useQueryClient();
  const { status, installing } = useUpdates();
  const [checking, setChecking] = useState(false);
  const [pressed, setPressed] = useState(false);
  useWhileBusy(offline);
  const line = updatesLine(status, version, offline);
  const release = status?.available ?? null;
  const testId = status?.problem ? 'update-problem' : release ? 'update-available' : 'update-line';
  if (!status) return <StatusLine line={line} testId={testId} />;

  async function checkNow() {
    setChecking(true);
    try {
      const s = await api.checkUpdates();
      updates.set(s);
      qc.setQueryData(queryKeys.updates(), s);
      setPressed(true);
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setChecking(false);
    }
  }

  const busy = status.busy;
  const answer = checkAnswer(status, pressed);
  const last = lastInstallLine(status);
  return (
    <>
      <StatusLine line={line} testId={testId} />
      <div className="settings-row">
        <p className="hint" data-testid="update-checked">{checkedLine(status)}</p>
        <Button small disabled={offline || !!busy || !!installing || checking} onClick={checkNow}>{checking ? 'Checking…' : 'Check now'}</Button>
      </div>
      {/* the answer to Check now comes in under it, so the button does not move; while it works, the line above says so */}
      {answer && <p className="state-line" role="status" data-testid="update-found">{answer}</p>}
      {status.check_error && <p className="hint" data-testid="update-check-error">{status.check_error}</p>}
      {release?.notes.trim() && (
        <details className="more update-notes" data-testid="update-notes">
          <summary>What's new in {release.version}</summary>
          <Markdown text={release.notes} />
        </details>
      )}
      {line.action === 'install' && <InstallNow offline={offline} toast={toast} status={status} />}
      {release && (
        <p className="hint">
          <a href={release.page} target="_blank" rel="noreferrer noopener">{status.can_install ? 'The release page' : 'Download it from the release page'}</a>
        </p>
      )}
      {last && last !== line.text && (status.last_install?.ok
        ? <p className="hint" data-testid="update-last">{last}</p>
        : <Notice as="p" tone="error" testId="update-last">{last}</Notice>)}
    </>
  );
}

/** Install now, with the download's size, under the Settings line. */
function InstallNow({ offline, toast, status }: { offline: boolean; toast: Toast; status: UpdateStatus }) {
  const { installing } = useUpdates();
  const [busy, setBusy] = useState(false);

  async function installNow() {
    setBusy(true);
    try {
      await updates.install(toast);
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-actions">
      <Button variant="primary" disabled={offline || !!status.busy || !!installing || busy} onClick={installNow}>Install now</Button>
      <span className="hint">{status.download_size ? `${formatSize(status.download_size)}. ` : ''}Your closets are backed up first.</span>
    </div>
  );
}

/** The one choice about updates made once: whether to install by itself, ask first or never look. On Advanced. */
export function UpdatesMode({ offline, toast }: { offline: boolean; toast: Toast }) {
  const qc = useQueryClient();
  const { status } = useUpdates();

  if (!status) {
    return <p className="hint">{offline ? "Updates can't be changed while you're offline." : 'This copy of Nines has no updater.'}</p>;
  }

  async function choose(mode: UpdateMode) {
    const before = status;
    if (!before) return;
    updates.set({ ...before, mode });
    try {
      const s = await api.setUpdateMode(mode);
      updates.set(s);
      qc.setQueryData(queryKeys.updates(), s);
      toast('Saved');
    } catch (e) {
      updates.set(before);
      toast((e as Error).message, 'error');
    }
  }

  const mode = MODES.find((m) => m.value === status.mode);
  return (
    <div className="update-modes">
      <p className="update-modes-label">When a new version is out</p>
      <SegmentedControl label="When a new version is out" options={MODES.map((m) => ({ value: m.value, label: m.short }))}
        small value={status.mode} onChange={(m) => { if (!offline && m !== status.mode) void choose(m); }} className="update-mode-choice" />
      <p className="hint" data-testid="update-mode-hint"><strong>{mode?.label}.</strong> {mode?.hint}</p>
    </div>
  );
}
