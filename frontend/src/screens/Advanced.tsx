/**
 * Advanced settings, at /settings/advanced: what is set once and rarely looked at again. Its code is fetched only
 * when the screen is opened (Shell.tsx). It reads the same settings as the main page, from the cache when the main
 * page was open before, and gates once on them.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { StatusLine, Toggle } from '../components/Toggle';
import { UpdatesManage } from '../components/Updates';
import { Notice, PageHeader } from '../components/ui';
import { deviceOf } from '../here';
import { formatSize, parsePrice } from '../labels';
import { touch, useModel } from '../queries';
import { queryKeys } from '../queryKeys';
import { routeIds, settingsQuery, settingsSaved, storageQuery, taggingQuery, useSaveSettings, writePart } from '../settings';
import { backupLine, computerOnly, storageLine, type ComputerOnly } from '../settingsLines';
import { apiKeyLine, apiKeySavedLine, dayName, firstRouteLine, formatUsd, monthName, ROUTE_ORDERS, spentLine, suggestionLine, turnedOffLine, waitingLine } from '../spend';
import { useApp } from '../store';
import type { ModelInfo, Profile, RouteOrder, Settings, TaggingRoute, TaggingSpend } from '../types';
import { README_CLAUDE_CODE, Section, type Toast } from './Settings';

export function AdvancedScreen({ version }: { version: string }) {
  const { offline, profile, switchProfile, toast } = useApp();
  const saveSettings = useSaveSettings();
  const model = useModel();
  const device = deviceOf(window.location.hostname);
  const only = computerOnly(device);
  const read = useQuery({ ...settingsQuery(), enabled: !offline });
  // the slow lookups start at once, beside it, and each fills a row of its own
  useQuery({ ...taggingQuery(), enabled: !offline });
  useQuery({ ...storageQuery(), enabled: !offline });

  const header = <PageHeader title="Advanced" back={{ to: '/settings', label: 'Settings' }} />;
  const settings = read.data;
  if (!settings) {
    return (
      <div className="settings">
        {header}
        {offline ? <Notice as="p">You're offline, so settings can't be shown or changed right now.</Notice>
          : read.error ? (
            <>
              <p className="form-error" role="alert">{read.error.message}</p>
              <button className="btn" onClick={() => void read.refetch()}>Try again</button>
            </>
          ) : <p className="hint" aria-busy="true">Opening the advanced settings…</p>}
      </div>
    );
  }

  return (
    <div className="settings">
      {header}
      {offline && <Notice as="p">You're offline, so settings can't be shown or changed right now.</Notice>}
      {!offline && read.error && <p className="form-error" role="alert">{read.error.message}</p>}

      <div className="settings-groups">
        {only.autostart && settings.autostart !== null && (
          <Section title="Starting Nines" id="s-start">
            <Toggle label="Start Nines when I log in" hint="Nines opens quietly in the background when you sign in to this computer."
              checked={settings.autostart} disabled={offline}
              onChange={async (on) => {
                try {
                  await saveSettings({ autostart: on });
                  toast('Saved');
                } catch (e) {
                  toast((e as Error).message, 'error');
                }
              }} />
          </Section>
        )}

        <TaggingSection offline={offline} settings={settings} toast={toast} />

        <Section title="Updates" id="s-updates">
          <UpdatesManage offline={offline} toast={toast} />
        </Section>

        <BackupSection settings={settings} profile={profile} only={only} toast={toast} disabled={offline} />
        <StorageSection offline={offline} profile={profile} />
        <ModelAddress model={model ?? settings.model} only={only} toast={toast} disabled={offline} />

        <Section title="This copy of Nines" id="s-about">
          <dl className="facts">
            {only.dataFolder && (
              <>
                <dt>Your closet is stored in</dt>
                <dd><code className="path">{settings.data_dir}</code></dd>
              </>
            )}
            <dt>Version</dt>
            <dd>{settings.version ?? version}</dd>
          </dl>
        </Section>

        {/* last: once your own clothes are in, the sample closet is rarely wanted; while it shows, the strip at the
            top of every screen has Leave, so the way back never depends on finding this */}
        <Section title="The demo closet" id="s-demo">
          <Toggle
            label="Show the demo closet"
            hint="About 50 sample clothes to try things out with. Your own closet is kept apart and not touched."
            checked={profile === 'demo'}
            disabled={offline}
            onChange={(on) => switchProfile(on ? 'demo' : 'main').catch((e) => toast((e as Error).message, 'error'))}
          />
        </Section>
      </div>
    </div>
  );
}

/** Where the background-removal model is downloaded from, and, on the computer, where to put it by hand. */
function ModelAddress({ model, only, toast, disabled }: { model: ModelInfo; only: ComputerOnly; toast: Toast; disabled: boolean }) {
  const qc = useQueryClient();
  const [url, setUrl] = useState(model.url);
  useEffect(() => setUrl(model.url), [model.url]);

  async function saveUrl(e: FormEvent | null, value: string) {
    e?.preventDefault();
    try {
      const info = await api.setModelUrl(value);
      setUrl(info.url);
      writePart(qc, { model: info });
      void touch(qc, 'model', ['model']);
      toast('Saved');
    } catch (err) {
      toast((err as ApiError).message, 'error');
    }
  }

  return (
    <Section title="Background removal" id="s-model" hint="The files that cut your clothes out of their photos.">
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
      {only.modelFiles && (
        <details className="more">
          <summary>Put the files in place by hand</summary>
          <p className="hint">Get the file from the address above on another computer and put it here, then come back to this page:</p>
          <p><code className="path">{model.path}</code></p>
          {model.second && (
            <>
              <p className="hint">The second file works the same way. It is at this address:</p>
              <p><code className="path">{model.second.url}</code></p>
              <p className="hint">and goes here:</p>
              <p><code className="path">{model.second.path}</code></p>
            </>
          )}
        </details>
      )}
    </Section>
  );
}



/** Backups: the folder (typed on the computer only: it is the computer's path), the last one, and Back up now. */
function BackupSection({ settings, profile, only, toast, disabled }: {
  settings: Settings; profile: Profile; only: ComputerOnly; toast: Toast; disabled: boolean;
}) {
  const qc = useQueryClient();
  const saveSettings = useSaveSettings();
  const [folder, setFolder] = useState(settings.backup_folder ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setFolder(settings.backup_folder ?? ''), [settings.backup_folder]);

  async function saveFolder(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await saveSettings({ backup_folder: folder.trim() || null });
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
      // done or not, the last backup is recorded, and the space used changes
      await touch(qc, 'backup');
      setBusy(false);
    }
  }

  return (
    <Section title="Backups" id="s-backup" hint="A copy every day to a folder you choose, such as a synced folder or a USB drive.">
      <StatusLine line={backupLine(settings, profile, only.backupFolder ? 'computer' : 'phone')} testId="backup-status" />
      {only.backupFolder && (
        <form className="field-row field-row-inline" onSubmit={saveFolder}>
          <label className="field">
            <span>Backup folder</span>
            <input value={folder} disabled={disabled} onChange={(e) => setFolder(e.target.value)} spellCheck={false} />
          </label>
          <button className="btn" type="submit" disabled={disabled || folder.trim() === (settings.backup_folder ?? '')}>Save</button>
        </form>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
      {profile !== 'demo' && settings.backup_folder && (
        <button className="btn btn-primary" disabled={busy || disabled} onClick={backupNow}>
          {busy ? 'Backing up…' : 'Back up now'}
        </button>
      )}
    </Section>
  );
}

/** The space used: a slow walk of the closet's folders, so the rows are drawn at once and filled in when it is done. */
function StorageSection({ offline, profile }: { offline: boolean; profile: Profile }) {
  const { data: storage, error, refetch, isFetching } = useQuery({ ...storageQuery(), enabled: !offline });

  let body: ReactNode;
  if (offline) body = <p className="hint">Storage details aren't available while you're offline.</p>;
  else if (error && !storage) {
    body = (
      <>
        <p className="form-error" role="alert">Couldn't work out how much space Nines uses: {error.message}</p>
        <button className="btn" disabled={isFetching} onClick={() => void refetch()}>Try again</button>
      </>
    );
  } else {
    const size = (bytes: (s: NonNullable<typeof storage>) => number) => (storage ? formatSize(bytes(storage)) : '…');
    const rows: [string, (s: NonNullable<typeof storage>) => number][] = [
      ['Photos', (s) => s.photos_bytes],
      ['Cutouts', (s) => s.cutouts_bytes],
      ['Thumbnails', (s) => s.thumbnails_bytes],
      ['Backups on this computer', (s) => s.backups_bytes],
      ['Background-removal model', (s) => s.model_bytes],
      ['Everything else', (s) => Math.max(0, s.total_bytes - s.photos_bytes - s.cutouts_bytes - s.thumbnails_bytes - s.backups_bytes - s.model_bytes)],
    ];
    body = (
      <>
        <p className="storage-total" aria-busy={!storage} data-testid="storage-line">
          {storage ? storageLine(formatSize(storage.total_bytes), storage.items, storage.free_bytes !== null ? formatSize(storage.free_bytes) : null)
            : <span className="muted">Adding up how much space Nines uses…</span>}
        </p>
        <details className="more">
          <summary>What takes the space</summary>
          <dl className="storage-list">
            {rows.map(([name, bytes]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{size(bytes)}</dd>
              </div>
            ))}
          </dl>
          {profile === 'demo' && <p className="hint">These are the demo closet's own pictures. The model, backups and logs are shared with your own closet.</p>}
        </details>
      </>
    );
  }

  return (
    <Section title="Storage" id="s-storage">
      {body}
    </Section>
  );
}


const ROUTE_TEXT: Record<TaggingRoute['id'], { name: string; hint: string }> = {
  plan: { name: 'Your Claude plan, through Claude Code', hint: 'Costs nothing extra; counts against your plan’s usage limits.' },
  api: { name: 'An API key', hint: 'Billed per photo; only used if you allow it below, and never past your monthly limit.' },
};

interface TaggingProps {
  offline: boolean;
  settings: Settings;
  toast: Toast;
}

/** How Nines reaches Claude. Whether Claude Code is signed in is a slow lookup of its own, asked once each time the
 * page opens and again when a key or the order changes; what it last said stays on screen meanwhile. */
function TaggingSection({ offline, settings, toast }: TaggingProps) {
  const qc = useQueryClient();
  const tagging = useQuery({ ...taggingQuery(), enabled: !offline });
  const status = tagging.data ?? null;
  const error = tagging.error ? tagging.error.message : null;

  const checkAgain = (
    <button className="btn" disabled={tagging.isFetching} onClick={() => {
      void tagging.refetch();
      void qc.invalidateQueries({ queryKey: queryKeys.settings(), exact: true });   // the items waiting
    }}>Check again</button>
  );
  const apiAllowed = settings.tagging_api_enabled;
  const waiting = settings.pending_tags;
  const byId = new Map((status?.routes ?? []).map((r) => [r.id, r]));
  // in the order chosen, known with the settings, so the list does not reorder when the lookup lands
  const order: TaggingRoute['id'][] = routeIds(settings.tagging_route_order);
  let routeState: ReactNode;
  if (error) {
    routeState = (
      <>
        <p className="form-error" role="alert">Couldn't check how Nines can reach Claude: {error}</p>
        <button className="btn" disabled={tagging.isFetching} onClick={() => void tagging.refetch()}>Try again</button>
      </>
    );
  } else if (!status) {
    // the same shape as the answer (a line, then the button), so nothing below moves when it lands
    routeState = (
      <>
        <p className="hint" aria-busy="true">Checking how Nines can reach Claude…</p>
        {checkAgain}
      </>
    );
  } else {
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
            Nines can't reach Claude yet: you chose to use only the API key, and it isn't ready. Allow it below with a monthly limit, or choose to use your Claude plan.
          </p>
        ) : apiOnlyOff ? (
          <p className="form-error">
            Nines can't reach Claude yet: your API key is set but not allowed below. <a href={README_CLAUDE_CODE} target="_blank" rel="noreferrer">Install Claude Code and sign in</a> to use your plan instead, or allow the key.
          </p>
        ) : none ? (
          <p className="form-error">
            Nines can't reach Claude yet. <a href={README_CLAUDE_CODE} target="_blank" rel="noreferrer">Install Claude Code and sign in</a>, then check again.
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
    if (id === 'api') {
      return <ApiKeyBox offline={offline} settings={settings} toast={toast} />;
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
    <Section title="Claude" id="s-tagging">
      {offline ? <p className="hint">How Nines reaches Claude can't be checked while you're offline.</p> : (
        <>
          <p className="hint">Nines tries these in this order and uses the first one that works.</p>
          <ol className="route-list">
            {order.map((id) => (
              <li key={id} data-testid={`route-${id}`}>
                <h3 className="route-name">{ROUTE_TEXT[id]?.name ?? id}</h3>
                {routeLine(id)}
                <p className="hint">{ROUTE_TEXT[id]?.hint}</p>
              </li>
            ))}
          </ol>
          {!order.includes('api') && (
            <div className="route-unused" data-testid="route-api-unused">
              <h3 className="route-name">{ROUTE_TEXT.api.name}</h3>
              <ApiKeyBox offline={offline} settings={settings} toast={toast} />
              <p className="hint">Not used: you chose to use only your Claude plan.</p>
            </div>
          )}
          {routeState}
        </>
      )}
      {waiting > 0 && (
        <p className="hint" data-testid="tags-waiting">{`${waiting} ${waiting === 1 ? 'item is' : 'items are'} waiting to be described.`}</p>
      )}
      <ApiKeySpend offline={offline} settings={settings} toast={toast} />
    </Section>
  );
}

const ANTHROPIC_KEYS = 'https://console.anthropic.com/settings/keys';

/** Paste an API key: Nines checks it with Anthropic and keeps it in the computer's keychain. The page never
 * receives the key back, so once saved it is only ever described, never shown. */
function ApiKeyBox({ offline, settings, toast }: { offline: boolean; settings: Settings; toast: Toast }) {
  const qc = useQueryClient();
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
      settingsSaved(qc, saved, 'apiKey');
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
      settingsSaved(qc, after, 'apiKey');
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
          Make one in your <a href={ANTHROPIC_KEYS} target="_blank" rel="noreferrer">Anthropic account, under API keys</a>, and paste it here. Nines checks it with Anthropic (this costs nothing) and keeps it in {info.where}. It is never shown again, not even here.
        </p>
      )}
      {!info.can_save && !info.set && (
        <p className="hint">This computer has no keychain Nines can keep a key in. Set ANTHROPIC_API_KEY on the computer instead.</p>
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
function RouteOrderChoice({ offline, settings, toast }: { offline: boolean; settings: Settings; toast: Toast }) {
  const saveSettings = useSaveSettings();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const group = useId();
  const hasKey = settings.api_key.set;

  async function choose(order: RouteOrder) {
    setBusy(true);
    setError(null);
    try {
      await saveSettings({ tagging_route_order: order });
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

/** The API key's monthly limit and what it has cost. The spending comes with the settings, so it is drawn with them
 * and follows every save. */
function ApiKeySpend({ offline, settings, toast }: { offline: boolean; settings: Settings; toast: Toast }) {
  const saveSettings = useSaveSettings();
  const spend = useQuery<TaggingSpend>({ queryKey: queryKeys.spend(), queryFn: api.tagSpend, enabled: false }).data ?? settings.tagging_spend;
  const [cap, setCap] = useState(settings.tagging_api_cap_usd !== null ? String(settings.tagging_api_cap_usd) : '');
  const [capError, setCapError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const saved = settings.tagging_api_cap_usd;

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
      await saveSettings(changes);
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
      <RouteOrderChoice offline={offline} settings={settings} toast={toast} />
      <Toggle label="Allow the API key"
        hint="Lets Nines use your API key, in the order chosen above. Each photo is billed to your Anthropic account, and Nines stops before this month's spending would pass the limit below."
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
                Costs are worked out from Anthropic's prices as written down on {dayName(spend.prices_checked)}. Your Anthropic account shows what was really charged.
              </p>
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

