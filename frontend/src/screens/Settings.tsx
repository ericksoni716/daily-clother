import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { ModelProgress, modelStateText } from '../components/ModelBanner';
import { PhoneAccess } from '../components/PhoneAccess';
import { formatDateTime, formatSize } from '../labels';
import { useCloset } from '../store';
import type { ModelInfo, Profile, Settings, Storage } from '../types';

function Section({ title, children, id }: { title: string; children: ReactNode; id: string }) {
  return (
    <section className="settings-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

export function SettingsScreen({ version }: { version: string }) {
  const { offline, model, refreshModel, profile, switchProfile, logout, quit, toast } = useCloset();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSettings(await api.settings());
      setLoadError(null);
    } catch (e) {
      setLoadError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
    void refreshModel();
  }, [load, refreshModel]);

  return (
    <div className="settings">
      <header className="page-header"><h1>Settings</h1></header>
      {offline && <p className="notice">You're offline, so settings can't be shown or changed right now.</p>}
      {!offline && loadError && <p className="form-error" role="alert">{loadError}</p>}

      <div className="settings-columns">
        <div className="settings-col">
          {model && <ModelSection model={model} refresh={refreshModel} toast={toast} disabled={offline} />}
          {settings && <BackupSection settings={settings} onChange={setSettings} toast={toast} disabled={offline} />}
          <StorageSection offline={offline} profile={profile} />
        </div>
        <div className="settings-col">
          {settings && (
            <Section title="Phone access" id="s-phone">
              <PhoneAccess phone={settings.phone} />
            </Section>
          )}
          <Section title="Demo closet" id="s-demo">
            <Toggle
              label="Show the demo closet"
              hint="About 30 sample clothes to try things out with. Your own closet is kept separately and is not touched."
              checked={profile === 'demo'}
              disabled={offline}
              onChange={(on) => switchProfile(on ? 'demo' : 'main').catch((e) => toast((e as Error).message, 'error'))}
            />
          </Section>

          {settings && settings.autostart !== null && (
            <Section title="Starting up" id="s-start">
              <Toggle label="Start Closet when I log in" hint="Closet opens quietly in the background when you sign in to this computer."
                checked={settings.autostart} disabled={offline}
                onChange={async (on) => {
                  try {
                    setSettings(await api.putSettings({ autostart: on }));
                    toast('Saved');
                  } catch (e) {
                    toast((e as Error).message, 'error');
                  }
                }} />
            </Section>
          )}

          <Section title="About" id="s-about">
            <dl className="facts">
              <dt>Your closet is stored in</dt>
              <dd><code className="path">{settings?.data_dir ?? '…'}</code></dd>
              <dt>Version</dt>
              <dd>{settings?.version ?? version}</dd>
            </dl>
          </Section>

          <Section title="Leave" id="s-leave">
            <div className="stack">
              <button className="btn btn-block" onClick={() => void logout()}>Log out</button>
              <QuitButton onQuit={quit} disabled={offline} toast={toast} />
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

function ModelSection({ model, refresh, toast, disabled }: { model: ModelInfo; refresh(): Promise<void>; toast(m: string, k?: 'ok' | 'error'): void; disabled: boolean }) {
  const [url, setUrl] = useState(model.url);
  const [busy, setBusy] = useState(false);
  useEffect(() => setUrl(model.url), [model.url]);

  async function download() {
    setBusy(true);
    try {
      await api.downloadModel();
      await refresh();
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function saveUrl(e: FormEvent | null, value: string) {
    e?.preventDefault();
    try {
      const info = await api.setModelUrl(value);
      setUrl(info.url);
      await refresh();
      toast('Saved');
    } catch (err) {
      toast((err as ApiError).message, 'error');
    }
  }

  return (
    <Section title="Background removal" id="s-model">
      <p className={`state-line state-${model.state}`}><span className="state-dot" aria-hidden="true" />{modelStateText(model)}</p>
      {model.state === 'failed' && model.error && <p className="form-error">{model.error}</p>}
      {model.state === 'downloading' && <ModelProgress model={model} />}
      {model.state !== 'ready' && model.state !== 'downloading' && (
        <button className="btn btn-primary" disabled={busy || disabled} onClick={download}>
          {model.state === 'failed' ? 'Try the download again' : 'Download the model'}
        </button>
      )}
      <form className="field-row" onSubmit={(e) => saveUrl(e, url)}>
        <label className="field">
          <span>Download address</span>
          <input type="url" value={url} disabled={disabled} onChange={(e) => setUrl(e.target.value)} spellCheck={false} />
        </label>
        <div className="row">
          <button className="btn" type="submit" disabled={disabled || url === model.url}>Save address</button>
          <button className="btn btn-ghost" type="button" disabled={disabled} onClick={() => saveUrl(null, '')}>Use default</button>
        </div>
      </form>
      <p className="hint">Can't download here? Get the file from that address on another computer and put it here, then come back to this page:</p>
      <p><code className="path">{model.path}</code></p>
    </Section>
  );
}

function BackupSection({ settings, onChange, toast, disabled }: { settings: Settings; onChange(s: Settings): void; toast(m: string, k?: 'ok' | 'error'): void; disabled: boolean }) {
  const [folder, setFolder] = useState(settings.backup_folder ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setFolder(settings.backup_folder ?? ''), [settings.backup_folder]);
  const last = settings.last_backup;

  async function saveFolder(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      onChange(await api.putSettings({ backup_folder: folder.trim() || null }));
      toast('Saved');
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function backupNow() {
    setBusy(true);
    setError(null);
    try {
      await api.backup();
      toast('Backed up');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      onChange(await api.settings().catch(() => settings));
      setBusy(false);
    }
  }

  return (
    <Section title="Backups" id="s-backup">
      <p className="hint">Closet copies your clothes and photos to a folder you choose, such as a USB drive or a synced folder (OneDrive, iCloud Drive, Dropbox). The demo closet is never backed up.</p>
      <form className="field-row field-row-inline" onSubmit={saveFolder}>
        <label className="field">
          <span>Backup folder</span>
          <input value={folder} disabled={disabled} placeholder="e.g. D:\Closet backups" onChange={(e) => setFolder(e.target.value)} spellCheck={false} />
        </label>
        <button className="btn" type="submit" disabled={disabled || folder.trim() === (settings.backup_folder ?? '')}>Save</button>
      </form>
      <p className="state-line">
        {settings.last_good_backup ? <>Last good backup: <strong>{formatDateTime(settings.last_good_backup)}</strong></> : 'No backup yet'}
      </p>
      {last && !last.ok && last.error && <p className="form-error">The last backup didn't work ({formatDateTime(last.at)}): {last.error}</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="btn btn-primary" disabled={busy || disabled || !settings.backup_folder} onClick={backupNow}>
        {busy ? 'Backing up…' : 'Back up now'}
      </button>
      {!settings.backup_folder && <p className="hint">Choose a backup folder first.</p>}
    </Section>
  );
}

function StorageSection({ offline, profile }: { offline: boolean; profile: Profile }) {
  const [storage, setStorage] = useState<Storage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (offline) return;
    let current = true;
    setStorage(null);
    setError(null);
    api.storage().then(
      (s) => current && setStorage(s),
      (e) => current && setError((e as Error).message),
    );
    return () => {
      current = false;
    };
  }, [offline, profile, attempt]);

  let body: ReactNode;
  if (offline) body = <p className="hint">Storage details aren't available while you're offline.</p>;
  else if (error) {
    body = (
      <>
        <p className="form-error" role="alert">Couldn't work out how much space Closet uses: {error}</p>
        <button className="btn" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
      </>
    );
  } else if (!storage) body = <p className="hint">Adding up how much space Closet uses…</p>;
  else {
    const shown = storage.photos_bytes + storage.cutouts_bytes + storage.thumbnails_bytes + storage.backups_bytes + storage.model_bytes;
    const rows: [string, number][] = [
      ['Photos', storage.photos_bytes],
      ['Cutouts', storage.cutouts_bytes],
      ['Thumbnails', storage.thumbnails_bytes],
      ['Backups on this computer', storage.backups_bytes],
      ['Background-removal model', storage.model_bytes],
      ['Everything else', Math.max(0, storage.total_bytes - shown)],
    ];
    body = (
      <>
        <p className="storage-total">
          <strong data-testid="storage-total">{formatSize(storage.total_bytes)}</strong> used by{' '}
          {storage.items === 1 ? '1 item' : `${storage.items} items`}
        </p>
        <dl className="storage-list">
          {rows.map(([name, bytes]) => (
            <div key={name}>
              <dt>{name}</dt>
              <dd>{formatSize(bytes)}</dd>
            </div>
          ))}
        </dl>
        {storage.free_bytes !== null && <p className="hint">{formatSize(storage.free_bytes)} free on this disk.</p>}
        {profile === 'demo' && <p className="hint">These are the demo closet's own pictures and list of clothes. The model, backups and the program's logs are shared with your own closet.</p>}
      </>
    );
  }

  return (
    <Section title="Storage" id="s-storage">
      {body}
    </Section>
  );
}

function Toggle({ label, hint, checked, disabled, onChange }: { label: string; hint?: string; checked: boolean; disabled?: boolean; onChange(on: boolean): void }) {
  return (
    <label className="toggle">
      <span className="toggle-text">
        <span className="toggle-label">{label}</span>
        {hint && <span className="hint">{hint}</span>}
      </span>
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track" aria-hidden="true"><span className="toggle-thumb" /></span>
    </label>
  );
}

function QuitButton({ onQuit, disabled, toast }: { onQuit(): Promise<void>; disabled: boolean; toast(m: string, k?: 'ok' | 'error'): void }) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) return <button className="btn btn-block btn-danger-quiet" disabled={disabled} onClick={() => setConfirming(true)}>Quit Closet</button>;
  return (
    <div className="confirm" role="alertdialog" aria-labelledby="quit-q">
      <p id="quit-q"><strong>Quit Closet?</strong> Your phone won't be able to reach it until you start it again on this computer.</p>
      <div className="row">
        <button className="btn btn-danger" autoFocus onClick={() => onQuit().catch((e) => toast((e as Error).message, 'error'))}>Quit</button>
        <button className="btn" onClick={() => setConfirming(false)}>Cancel</button>
      </div>
    </div>
  );
}
