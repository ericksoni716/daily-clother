import { useCallback, useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { ModelProgress, modelStateText } from '../components/ModelBanner';
import { PhoneAccess } from '../components/PhoneAccess';
import { WhereYouAre } from '../components/WhereYouAre';
import { LifeQuestions } from '../components/LifeQuestions';
import { UpdatesSection } from '../components/Updates';
import { confirmKeys, Notice, PageHeader, Section as UiSection, SegmentedControl, useConfirmFocus } from '../components/ui';
import { formatDateTime, formatSize, parsePrice } from '../labels';
import { Link } from '../router';
import { apiKeyLine, apiKeySavedLine, dayName, firstRouteLine, formatUsd, monthName, ROUTE_ORDERS, spentLine, suggestionLine, turnedOffLine, waitingLine } from '../spend';
import { useCloset } from '../store';
import { applyTheme, loadTheme, saveTheme, THEME_CHOICES, type Theme } from '../theme';
import { MAX_REWEAR, REWEAR_KINDS, rewearWords } from '../trips';
import type { ModelInfo, Profile, RewearKind, RouteOrder, Settings, Storage, TaggingRoute, TaggingSpend, TaggingStatus } from '../types';

/** One group of settings: a card with a heading. */
function Section({ title, hint, children, id }: { title: string; hint?: string; children: ReactNode; id: string }) {
  return <UiSection id={id} title={title} hint={hint} className="settings-section">{children}</UiSection>;
}

/** A part of a group, under its own smaller heading. */
function Sub({ title, children, id }: { title: string; children: ReactNode; id: string }) {
  return (
    <section className="settings-sub" aria-labelledby={id}>
      <h3 id={id}>{title}</h3>
      {children}
    </section>
  );
}

/** Light, dark or the device's own setting; kept on this device only, so it works offline too. */
function LookSection() {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  return (
    <UiSection id="s-look" title="Look" hint="Light or dark, on this device." className="settings-section">
      <SegmentedControl label="Look" options={THEME_CHOICES} value={theme} className="settings-look"
        onChange={(t) => { setTheme(t); saveTheme(t); applyTheme(t); }} />
    </UiSection>
  );
}

export function SettingsScreen({ version }: { version: string }) {
  const { offline, model, refreshModel, profile, switchProfile, logout, quit, toast } = useCloset();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lifeOpen, setLifeOpen] = useState(false);

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
      <PageHeader title="Settings" />
      {offline && <Notice as="p">You're offline, so settings can't be shown or changed right now.</Notice>}
      {!offline && loadError && <p className="form-error" role="alert">{loadError}</p>}

      <div className="settings-groups">
        <Section title="Your closet" id="s-closet">
          <Toggle
            label="Show the demo closet"
            hint="About 30 sample clothes to try things out with. Your own closet is kept separately and is not touched."
            checked={profile === 'demo'}
            disabled={offline}
            onChange={(on) => switchProfile(on ? 'demo' : 'main').catch((e) => toast((e as Error).message, 'error'))}
          />
          {settings && settings.autostart !== null && (
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
          )}
          {model && <ModelSection model={model} refresh={refreshModel} toast={toast} disabled={offline} />}
          {settings?.rewear && <RewearSection settings={settings} onChange={setSettings} toast={toast} disabled={offline} />}
          {settings && <BackupSection settings={settings} onChange={setSettings} toast={toast} disabled={offline} />}
          <StorageSection offline={offline} profile={profile} />
        </Section>

        <Section title="Where you are" id="s-place">
          <WhereYouAre place={settings ? settings.place : undefined} home={settings?.home_place} offline={offline} onChange={setSettings} toast={toast} />
          <p className="hint">Going away? <Link to="/trips">Plan a trip</Link> and Closet says what to pack for the weather there.</p>
        </Section>
        <Section title="How you live" id="s-life">
          <p className="hint">Tell What's missing about work, everyday life and time away. Change your answers whenever life changes.</p>
          {lifeOpen && settings ? (
            <LifeQuestions initial={settings.life ?? null} locked={offline} demo={profile === 'demo'}
              onSaved={(saved) => { setSettings(saved); toast('Your answers are saved'); }} onClose={() => setLifeOpen(false)} />
          ) : <button className="btn" disabled={!settings || offline} onClick={() => setLifeOpen(true)}>
            {profile === 'demo' ? 'See example answers' : settings?.life ? 'Edit my answers' : 'Tell it how you live'}
          </button>}
        </Section>

        <LookSection />

        <TaggingSection offline={offline} settings={settings} onChange={setSettings} reload={load} toast={toast} />

        <Section title="Updates" id="s-updates" hint="New versions of Closet, from its GitHub releases.">
          <UpdatesSection offline={offline} toast={toast} />
        </Section>

        {settings && (
          <Section title="Phone access" id="s-phone">
            <PhoneAccess phone={settings.phone} />
          </Section>
        )}

        <details className="card settings-advanced" id="s-advanced">
          <summary>Advanced</summary>
          <div className="settings-advanced-body">
            {model && <ModelAddress model={model} refresh={refreshModel} toast={toast} disabled={offline} />}
            <dl className="facts">
              <dt>Your closet is stored in</dt>
              <dd><code className="path">{settings?.data_dir ?? '…'}</code></dd>
              <dt>Version</dt>
              <dd>{settings?.version ?? version}</dd>
            </dl>
          </div>
        </details>

        <div className="settings-leave" role="group" aria-label="Leave">
          <button className="btn" onClick={() => void logout()}>Log out</button>
          <QuitButton onQuit={quit} disabled={offline} toast={toast} />
        </div>
      </div>
    </div>
  );
}

function ModelSection({ model, refresh, toast, disabled }: { model: ModelInfo; refresh(): Promise<void>; toast(m: string, k?: 'ok' | 'error'): void; disabled: boolean }) {
  const [busy, setBusy] = useState(false);

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

  return (
    <Sub title="Background removal" id="s-model">
      <p className={`state-line state-${model.state}`}><span className="state-dot" aria-hidden="true" />{modelStateText(model)}</p>
      {model.state === 'failed' && model.error && <p className="form-error">{model.error}</p>}
      {model.state === 'downloading' && <ModelProgress model={model} />}
      {model.state !== 'ready' && model.state !== 'downloading' && (
        <button className="btn btn-primary" disabled={busy || disabled} onClick={download}>
          {model.state === 'failed' ? 'Try the download again' : 'Download the model'}
        </button>
      )}
    </Sub>
  );
}

/** Where the background-removal model is downloaded from, and where to put it by hand. */
function ModelAddress({ model, refresh, toast, disabled }: { model: ModelInfo; refresh(): Promise<void>; toast(m: string, k?: 'ok' | 'error'): void; disabled: boolean }) {
  const [url, setUrl] = useState(model.url);
  useEffect(() => setUrl(model.url), [model.url]);

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
    <Sub title="Background-removal model" id="s-model-address">
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
    </Sub>
  );
}

/** "Before it needs washing": how often each kind of clothing is worn on a trip before it needs a wash. */
function RewearSection({ settings, onChange, toast, disabled }: { settings: Settings; onChange(s: Settings): void; toast(m: string, k?: 'ok' | 'error'): void; disabled: boolean }) {
  const [busy, setBusy] = useState(false);
  const rewear = settings.rewear!;

  async function save(kind: RewearKind, value: string) {
    setBusy(true);
    try {
      onChange(await api.putSettings({ rewear: { [kind]: value === '' ? null : Number(value) } }));
      toast('Saved');
    } catch (err) {
      toast((err as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sub title="Before it needs washing" id="s-rewear">
      <p className="hint">How many times you wear each kind on a trip before it needs washing. Trip packing counts with these; on a hot or humid day, what is worn next to the skin is worn once.</p>
      <div className="settings-rewear">
        {REWEAR_KINDS.map(({ kind, label }) => {
          const n = rewear[kind];
          const choices = Array.from({ length: MAX_REWEAR }, (_, i) => i + 1);
          if (n !== null && !choices.includes(n)) choices.push(n);
          return (
            <label key={kind} className="field">
              <span>{label}</span>
              <select value={n === null ? '' : String(n)} disabled={disabled || busy} onChange={(e) => void save(kind, e.target.value)}>
                {choices.map((c) => <option key={c} value={c}>{rewearWords(c)}</option>)}
                <option value="">{rewearWords(null)}</option>
              </select>
            </label>
          );
        })}
      </div>
    </Sub>
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
    <Sub title="Backups" id="s-backup">
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
    </Sub>
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
    <Sub title="Storage" id="s-storage">
      {body}
    </Sub>
  );
}

const README_CLAUDE_CODE = 'https://github.com/ericksoni716/daily-clother#installing-claude-code';

const ROUTE_TEXT: Record<TaggingRoute['id'], { name: string; hint: string }> = {
  plan: { name: 'Your Claude plan, through Claude Code', hint: 'Costs nothing extra; counts against your plan’s usage limits.' },
  api: { name: 'An API key', hint: 'Billed per photo; only used if you allow it below, and never past your monthly limit.' },
};

interface TaggingProps {
  offline: boolean;
  settings: Settings | null;
  onChange(s: Settings): void;
  reload(): Promise<void>;
  toast(m: string, k?: 'ok' | 'error'): void;
}

function TaggingSection({ offline, settings, onChange, reload, toast }: TaggingProps) {
  const [status, setStatus] = useState<TaggingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const keySource = settings?.api_key?.source ?? null;   // a key saved or removed changes what is ready
  const chosenOrder = settings?.tagging_route_order ?? null;     // so does the order chosen below

  useEffect(() => {
    if (offline) return;
    let current = true;
    setStatus(null);
    setError(null);
    api.tagging().then(
      (s) => current && setStatus(s),
      (e) => current && setError((e as Error).message),
    );
    return () => {
      current = false;
    };
  }, [offline, attempt, keySource, chosenOrder]);

  const checkAgain = <button className="btn" onClick={() => { setAttempt((n) => n + 1); void reload(); }}>Check again</button>;
  const apiAllowed = !!settings?.tagging_api_enabled;
  const waiting = settings?.pending_tags ?? 0;
  const byId = new Map((status?.routes ?? []).map((r) => [r.id, r]));
  const order: TaggingRoute['id'][] = status?.order ?? ['plan', 'api'];
  let routeState: ReactNode = null;
  if (error) {
    routeState = (
      <>
        <p className="form-error" role="alert">Couldn't check how Closet can reach Claude: {error}</p>
        <button className="btn" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
      </>
    );
  } else if (status) {
    const routes = order.map((id) => byId.get(id)).filter((r): r is TaggingRoute => !!r);
    const none = !routes.some((r) => r.available && (r.id !== 'api' || apiAllowed));
    const apiOnlyOff = none && byId.get('api')?.available && !apiAllowed;
    const planMissing = byId.get('plan')?.available === false;
    const planInOrder = status.order.includes('plan');
    const first = firstRouteLine(status.order, status.routes, apiAllowed);
    routeState = (
      <>
        {first && <p className="hint" data-testid="route-first">{first}</p>}
        {!planInOrder && none ? (
          <p className="form-error">
            Closet can't reach Claude yet: you chose to use only the API key, and it isn't ready. Allow it below with a monthly limit, or choose to use your Claude plan.
          </p>
        ) : apiOnlyOff ? (
          <p className="form-error">
            Closet can't reach Claude yet: your API key is set but not allowed below. <a href={README_CLAUDE_CODE} target="_blank" rel="noreferrer">Install Claude Code and sign in</a> to use your plan instead, or allow the key.
          </p>
        ) : none ? (
          <p className="form-error">
            Closet can't reach Claude yet. <a href={README_CLAUDE_CODE} target="_blank" rel="noreferrer">Install Claude Code and sign in</a>, then check again.
          </p>
        ) : planMissing && (
          <p className="hint">
            To use your plan instead of paying per photo, <a href={README_CLAUDE_CODE} target="_blank" rel="noreferrer">install Claude Code and sign in</a>.
          </p>
        )}
        {checkAgain}
      </>
    );
  }

  /** Each route once, with one line saying whether it can be used: the plan as Claude Code reports it, the key as it is kept. */
  function routeLine(id: TaggingRoute['id']): ReactNode {
    if (id === 'api' && settings) {
      return <ApiKeyBox offline={offline} settings={settings} onChange={onChange} toast={toast} />;
    }
    const r = byId.get(id);
    const text = error ? 'Not checked' : !r ? 'Checking…' : r.available ? 'Ready to use.' : r.detail || 'Not available.';
    return (
      <p className={`state-line ${r?.available ? 'state-ready' : r ? 'state-missing' : ''}`}>
        <span className="state-dot" aria-hidden="true" />
        <span>{text}</span>
      </p>
    );
  }

  return (
    <Section title="Describing clothes" id="s-tagging">
      {offline ? <p className="hint">How Closet reaches Claude can't be checked while you're offline.</p> : (
        <>
          <p className="hint">Closet asks Claude to describe your clothes. It tries these in this order and uses the first one that works:</p>
          <ol className="route-list">
            {order.map((id) => (
              <li key={id} data-testid={`route-${id}`}>
                <h3 className="route-name">{ROUTE_TEXT[id]?.name ?? id}</h3>
                {routeLine(id)}
                <p className="hint">{ROUTE_TEXT[id]?.hint}</p>
              </li>
            ))}
          </ol>
          {settings && !order.includes('api') && (
            <div className="route-unused" data-testid="route-api-unused">
              <h3 className="route-name">{ROUTE_TEXT.api.name}</h3>
              <ApiKeyBox offline={offline} settings={settings} onChange={onChange} toast={toast} />
              <p className="hint">Not used: you chose to use only your Claude plan.</p>
            </div>
          )}
          {routeState}
        </>
      )}
      {settings && (
        <>
          <p className="hint" data-testid="tags-waiting">
            {waiting === 0 ? 'No items are waiting to be described.'
              : `${waiting} ${waiting === 1 ? 'item is' : 'items are'} waiting to be described.`}
          </p>
          <ApiKeySpend offline={offline} settings={settings} onChange={onChange} toast={toast} />
        </>
      )}
    </Section>
  );
}

const ANTHROPIC_KEYS = 'https://console.anthropic.com/settings/keys';

/** Paste an API key: Closet checks it with Anthropic and keeps it in the computer's keychain. The page never
 * receives the key back, so once saved it is only ever described, never shown. */
function ApiKeyBox({ offline, settings, onChange, toast }: { offline: boolean; settings: Settings; onChange(s: Settings): void; toast(m: string, k?: 'ok' | 'error'): void }) {
  const info = settings.api_key;
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replacing, setReplacing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const askForKey = info.can_save && (info.source !== 'keychain' || replacing);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await api.saveApiKey(key.trim());
      setKey('');
      setReplacing(false);
      onChange(saved);
      toast(apiKeySavedLine(saved.api_key, saved.tagging_api_enabled));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const after = await api.removeApiKey();
      setRemoving(false);
      onChange(after);
      toast(after.api_key.set ? 'Key removed from the keychain. The one in ANTHROPIC_API_KEY is still used.' : 'Key removed');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="api-key" data-testid="api-key">
      <p className={`state-line ${info.set ? 'state-ready' : 'state-missing'}`}>
        <span className="state-dot" aria-hidden="true" />
        <span>{apiKeyLine(info)}</span>
      </p>
      {askForKey && (
        <form className="field-row field-row-inline" onSubmit={(e) => void save(e)}>
          <label className="field">
            <span>{info.source === 'keychain' ? 'New API key' : 'Paste your API key'}</span>
            <input type="password" autoComplete="off" spellCheck={false} placeholder="sk-ant-…" value={key}
              disabled={offline || busy} onChange={(e) => setKey(e.target.value)} />
          </label>
          <button className="btn" type="submit" disabled={offline || busy || key.trim() === ''}>{busy ? 'Checking…' : 'Save key'}</button>
          {replacing && <button className="btn" type="button" disabled={busy} onClick={() => { setReplacing(false); setKey(''); setError(null); }}>Cancel</button>}
        </form>
      )}
      {askForKey && (
        <p className="hint">
          Make one in your <a href={ANTHROPIC_KEYS} target="_blank" rel="noreferrer">Anthropic account, under API keys</a>, and paste it here. Closet checks it with Anthropic (this costs nothing) and keeps it in {info.where}. It is never shown again, not even here.
        </p>
      )}
      {!info.can_save && !info.set && (
        <p className="hint">This computer has no keychain Closet can keep a key in. Set ANTHROPIC_API_KEY on the computer instead.</p>
      )}
      {info.source === 'keychain' && !replacing && (
        removing ? (
          <p className="field-row field-row-inline">
            <span>Remove the key from {info.where}?</span>
            <button className="btn btn-danger" type="button" disabled={offline || busy} onClick={() => void remove()}>Remove</button>
            <button className="btn" type="button" disabled={busy} onClick={() => setRemoving(false)}>Keep it</button>
          </p>
        ) : (
          <p className="field-row field-row-inline">
            <button className="btn" type="button" disabled={offline} onClick={() => { setReplacing(true); setError(null); }}>Replace key</button>
            <button className="btn" type="button" disabled={offline} onClick={() => setRemoving(true)}>Remove key</button>
          </p>
        )
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}

/** Which route to Claude is tried first. Choices that put the key first need a key; the key is still only used once
 * it is allowed with a monthly limit. */
function RouteOrderChoice({ offline, settings, onChange, toast }: { offline: boolean; settings: Settings; onChange(s: Settings): void; toast(m: string, k?: 'ok' | 'error'): void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const group = useId();
  const hasKey = settings.api_key.set;

  async function choose(order: RouteOrder) {
    setBusy(true);
    setError(null);
    try {
      onChange(await api.putSettings({ tagging_route_order: order }));
      toast('Saved');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <fieldset className="route-order" data-testid="route-order" disabled={offline || busy}>
      <legend>Which to use</legend>
      {ROUTE_ORDERS.map((o) => (
        <label key={o.value} className="route-order-choice">
          <input type="radio" name={group} value={o.value} checked={settings.tagging_route_order === o.value}
            disabled={o.needsKey && !hasKey} onChange={() => void choose(o.value)} />
          <span>{o.label}{o.needsKey && !hasKey && <span className="muted"> (save an API key first)</span>}</span>
        </label>
      ))}
      <p className="hint">The API key is only used once you turn on Allow the API key below and set a monthly limit.</p>
      {error && <p className="form-error" role="alert">{error}</p>}
    </fieldset>
  );
}

function ApiKeySpend({ offline, settings, onChange, toast }: { offline: boolean; settings: Settings; onChange(s: Settings): void; toast(m: string, k?: 'ok' | 'error'): void }) {
  const [spend, setSpend] = useState<TaggingSpend | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cap, setCap] = useState(settings.tagging_api_cap_usd !== null ? String(settings.tagging_api_cap_usd) : '');
  const [capError, setCapError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const saved = settings.tagging_api_cap_usd;

  useEffect(() => {
    if (offline) return;
    let current = true;
    api.tagSpend().then(
      (s) => { if (current) { setSpend(s); setLoadError(null); } },
      (e) => current && setLoadError((e as Error).message),
    );
    return () => {
      current = false;
    };
  }, [offline, settings]);
  useEffect(() => setCap(saved !== null ? String(saved) : ''), [saved]);

  /** The limit typed, in dollars, or null after saying what is wrong. */
  function typedCap(): number | null {
    const cents = parsePrice(cap);
    if (cents === null || cents === undefined || cents <= 0) {
      setOpen(true);
      setCapError('Type a monthly limit in dollars, such as 5 or 2.50.');
      return null;
    }
    setCapError(null);
    return cents / 100;
  }

  async function save(changes: { tagging_api_enabled?: boolean; tagging_api_cap_usd?: number }, said: string) {
    try {
      onChange(await api.putSettings(changes));
      setCapError(null);
      toast(said);
    } catch (e) {
      setCapError((e as Error).message);
    }
  }

  const placeholder = spend ? String(spend.suggested_cap_usd) : '';
  return (
    <div className="api-spend" data-testid="api-spend">
      {settings.tagging_api_off && <p className="form-error" role="alert">{turnedOffLine(settings.tagging_api_off)}</p>}
      <RouteOrderChoice offline={offline} settings={settings} onChange={onChange} toast={toast} />
      <Toggle label="Allow the API key"
        hint="Lets Closet use your API key, in the order chosen above. Each photo is billed to your Anthropic account, and Closet stops before this month's spending would pass the limit below."
        checked={settings.tagging_api_enabled} disabled={offline}
        onChange={(on) => {
          if (!on) return void save({ tagging_api_enabled: false }, 'The API key will not be used');
          const limit = typedCap();
          if (limit !== null) void save({ tagging_api_enabled: true, tagging_api_cap_usd: limit }, `The API key may be used, up to ${formatUsd(limit)} a month`);
        }} />
      <details className="more settings-spend" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>
          <span>Monthly limit and spending</span>
          {saved !== null && <span className="muted settings-spend-cap">{formatUsd(saved)} a month</span>}
        </summary>
        <div className="settings-spend-body">
          <form className="field-row field-row-inline" onSubmit={(e) => {
            e.preventDefault();
            const limit = typedCap();
            if (limit !== null) void save({ tagging_api_cap_usd: limit }, 'Saved');
          }}>
            <label className="field">
              <span>Monthly limit for the API key (US dollars)</span>
              <input inputMode="decimal" value={cap} placeholder={placeholder} disabled={offline}
                onChange={(e) => setCap(e.target.value)} />
            </label>
            <button className="btn" type="submit" disabled={offline || cap.trim() === '' || parsePrice(cap) === Math.round((saved ?? -1) * 100)}>Save limit</button>
          </form>
          {loadError && <p className="form-error">Couldn't work out what the API key has cost: {loadError}</p>}
          {spend && (
            <>
              {saved === null && <p className="hint">{suggestionLine(spend.suggested_cap_usd, spend.per_photo_usd, spend.prices_checked)}</p>}
              <p className="state-line" data-testid="spend-month"><span><strong>{monthName(spend.month)}:</strong> {spentLine(spend)}</span></p>
              {spend.history.length > 0 && (
                <dl className="storage-list" aria-label="Spent with the API key, by month" data-testid="spend-history">
                  {spend.history.map((m) => (
                    <div key={m.month}>
                      <dt>{monthName(m.month)}</dt>
                      <dd>{formatUsd(m.spent_usd)}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <p className="hint">
                Costs are worked out from Anthropic's prices as written down on {dayName(spend.prices_checked)}. Prices change, so check them on Anthropic's pricing page before relying on these figures; your Anthropic account shows what was really charged.
              </p>
              <details className="more">
                <summary>Details</summary>
                <div className="tag-body">
                  <dl className="storage-list">
                    <div><dt>Model</dt><dd>{spend.model}</dd></div>
                    <div><dt>Sent this month (tokens)</dt><dd>{spend.input_tokens.toLocaleString('en-US')}</dd></div>
                    <div><dt>Received this month (tokens)</dt><dd>{spend.output_tokens.toLocaleString('en-US')}</dd></div>
                    <div><dt>Most one photo should cost</dt><dd>${spend.per_photo_usd.toFixed(4)}</dd></div>
                    {spend.left_usd !== null && <div><dt>Left this month</dt><dd>{formatUsd(spend.left_usd)}</dd></div>}
                    {spend.history.map((m) => (
                      <div key={m.month}>
                        <dt>{monthName(m.month)}</dt>
                        <dd>{`${m.api_calls} with the key (${m.input_tokens.toLocaleString('en-US')} in, ${m.output_tokens.toLocaleString('en-US')} out), ${m.plan_calls} with your plan`}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </details>
            </>
          )}
        </div>
      </details>
      {capError && <p className="form-error" role="alert">{capError}</p>}
      {spend?.allowed && spend.reached && (
        <p className="notice" role="status">
          This month's limit is reached, so the API key won't be used again until next month or until you raise the limit. Your plan is still used whenever it can be.
        </p>
      )}
      {spend && waitingLine(spend.waiting) && <p className="hint" data-testid="spend-waiting">{waitingLine(spend.waiting)}</p>}
    </div>
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
  const back = useConfirmFocus(confirming);
  if (!confirming) return <button ref={back} className="btn btn-block btn-danger-quiet" disabled={disabled} onClick={() => setConfirming(true)}>Quit Closet</button>;
  return (
    <div className="confirm" role="alertdialog" aria-labelledby="quit-q" onKeyDown={confirmKeys(() => setConfirming(false))}>
      <p id="quit-q"><strong>Quit Closet?</strong> Your phone won't be able to reach it until you start it again on this computer.</p>
      <div className="row">
        <button className="btn btn-danger" autoFocus onClick={() => onQuit().catch((e) => toast((e as Error).message, 'error'))}>Quit</button>
        <button className="btn" onClick={() => setConfirming(false)}>Cancel</button>
      </div>
    </div>
  );
}
