/**
 * Advanced settings, at /settings/advanced: what is set once and rarely looked at again. Its code is fetched only
 * when the screen is opened (Shell.tsx). It reads the same settings as the main page, from the cache when the main
 * page was open before, and gates once on them.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { StatusLine, Toggle } from '../components/Toggle';
import { UpdatesMode } from '../components/Updates';
import { Button, Failed, Fold, Notice, PageHeader } from '../components/ui';
import { deviceOf } from '../here';
import { formatSize } from '../labels';
import { stale, touch, useEdit, useModel } from '../queries';
import { queryKeys } from '../queryKeys';
import { settingsQuery, settingsSaved, storageQuery, taggingQuery, useSaveSettings, writePart } from '../settings';
import { apiKeyShows, backupLine, claudeLead, computerOnly, modelAddresses, modelLines, storageLine, type ComputerOnly, type ModelAddress as ModelAddressLine } from '../settingsLines';
import { apiKeyLine, apiKeySavedLine, dayName, earlierMonths, formatUsd, monthName, monthSpentLine, readCents, requestsLine, ROUTE_ORDERS, suggestionLine, turnedOffLine, waitingLine } from '../spend';
import { useApp } from '../store';
import type { ModelInfo, Profile, RouteOrder, Settings, TaggingSpend } from '../types';
import { README_CLAUDE_CODE, Section, type Toast } from './Settings';

export function AdvancedScreen() {
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
          : read.error ? <Failed query={read} what="the advanced settings" /> : <p className="hint" aria-busy="true">Opening the advanced settings…</p>}
      </div>
    );
  }

  return (
    <div className="settings">
      {header}
      {offline && <Notice as="p">You're offline, so settings can't be shown or changed right now.</Notice>}
      {!offline && <Failed query={read} what="the advanced settings" />}

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
          <UpdatesMode offline={offline} toast={toast} />
        </Section>

        <BackupSection settings={settings} profile={profile} only={only} toast={toast} disabled={offline} />
        <StorageSection offline={offline} profile={profile} dataDir={only.dataFolder ? settings.data_dir : null} />
        <ModelAddress model={model ?? settings.model} only={only} toast={toast} disabled={offline} />

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

/** The two background-removal models, a line each with how it stands and Download or Try again when it is missing
 * or failed; then, in one fold, where each is downloaded from (to change) and, on the computer, where its file goes. */
function ModelAddress({ model, only, toast, disabled }: { model: ModelInfo; only: ComputerOnly; toast: Toast; disabled: boolean }) {
  const qc = useQueryClient();
  const edit = useEdit('model');
  const [starting, setStarting] = useState(false);
  const addresses = modelAddresses(model, only.modelFiles);

  async function download() {
    setStarting(true);
    try {
      qc.setQueryData(queryKeys.model(), await edit(() => api.downloadModel()));
      toast('Downloading the files for cutting the clothes out');
    } catch (err) {
      toast((err as Error).message, 'error');
    } finally {
      setStarting(false);
    }
  }

  async function saveUrl(which: ModelAddressLine['id'], value: string): Promise<boolean> {
    try {
      const info = await api.setModelUrl(value, which);
      writePart(qc, { model: info });
      void touch(qc, 'model', ['model']);
      toast('Saved');
      return true;
    } catch (err) {
      toast((err as ApiError).message, 'error');
      return false;
    }
  }

  return (
    <Section title="Background removal" id="s-model">
      {modelLines(model).map((line) => (
        <StatusLine key={line.id} line={line} testId={`model-${line.id}`}>
          {line.action && (
            <>
              {' '}
              <Button variant="link" small disabled={disabled || starting} aria-label={line.actionLabel ?? undefined}
                onClick={download}>
                {line.action === 'retry' ? 'Try again' : 'Download'}
              </Button>
            </>
          )}
        </StatusLine>
      ))}
      <details className="more model-addresses" data-testid="model-addresses">
        <summary>If a download keeps failing</summary>
        <p className="hint">{addresses.intro}</p>
        {addresses.sets.map((set) => <ModelAddressForm key={set.id} set={set} disabled={disabled} onSave={saveUrl} />)}
      </details>
    </Section>
  );
}

/** One set's address, with Save and Use default, and where its file goes on the computer. */
function ModelAddressForm({ set, disabled, onSave }: {
  set: ModelAddressLine; disabled: boolean; onSave(which: ModelAddressLine['id'], url: string): Promise<boolean>;
}) {
  const [url, setUrl] = useState(set.url);
  useEffect(() => setUrl(set.url), [set.url]);
  const name = set.id === 'main' ? 'the first set' : 'the second set';
  return (
    <form className="model-address" data-testid={`model-address-${set.id}`}
      onSubmit={(e) => { e.preventDefault(); void onSave(set.id, url); }}>
      <label className="field">
        <span>{set.label}</span>
        <input type="url" value={url} disabled={disabled} onChange={(e) => setUrl(e.target.value)} spellCheck={false} />
      </label>
      <div className="row">
        <button className="btn btn-small" type="submit" disabled={disabled || url.trim() === set.url} aria-label={`Save ${name}'s address`}>Save</button>
        <button className="btn btn-small btn-ghost" type="button" disabled={disabled} aria-label={`Use the default for ${name}`}
          onClick={() => void onSave(set.id, '')}>Use default</button>
      </div>
      {set.path && <p className="hint" data-testid={`model-path-${set.id}`}>On this computer, its file goes here: <code className="path">{set.path}</code></p>}
    </form>
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
    <Section title="Backups" id="s-backup" hint="A copy every day to a folder you choose, such as a folder your computer copies to the cloud, or a USB drive.">
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

/** The space used (a slow walk of the closet's folders, so the rows are drawn at once and filled in when it is done),
 * then where the closet is kept, on the computer. */
function StorageSection({ offline, profile, dataDir }: { offline: boolean; profile: Profile; dataDir: string | null }) {
  const storageQ = useQuery({ ...storageQuery(), enabled: !offline });
  const { data: storage, error } = storageQ;

  const folder = dataDir && <p data-testid="data-folder">Your closet is stored in <code className="path">{dataDir}</code></p>;
  let body: ReactNode;
  if (offline) body = <><p className="hint">Storage details aren't available while you're offline.</p>{folder}</>;
  else if (error && !storage) {
    body = (
      <>
        <Failed query={storageQ} what="how much space Nines uses" testId="failed-storage" />
        {folder}
      </>
    );
  } else {
    const size = (bytes: (s: NonNullable<typeof storage>) => number) => (storage ? formatSize(bytes(storage)) : '…');
    const rows: [string, (s: NonNullable<typeof storage>) => number][] = [
      ['Photos', (s) => s.photos_bytes],
      ['Cutouts', (s) => s.cutouts_bytes],
      ['Thumbnails', (s) => s.thumbnails_bytes],
      ['Backups on this computer', (s) => s.backups_bytes],
      ['Cutting the clothes out of photos', (s) => s.model_bytes],
      ['Everything else', (s) => Math.max(0, s.total_bytes - s.photos_bytes - s.cutouts_bytes - s.thumbnails_bytes - s.backups_bytes - s.model_bytes)],
    ];
    body = (
      <>
        <p className="storage-total" aria-busy={!storage} data-testid="storage-line">
          {storage ? storageLine(formatSize(storage.total_bytes), storage.items, storage.free_bytes !== null ? formatSize(storage.free_bytes) : null)
            : <span className="muted">Adding up how much space Nines uses…</span>}
        </p>
        {folder}
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
          {profile === 'demo' && <p className="hint">These are the demo closet's own pictures. The files for cutting the clothes out, backups and logs are shared with your own closet.</p>}
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


interface TaggingProps {
  offline: boolean;
  settings: Settings;
  toast: Toast;
}

/**
 * How Nines reaches Claude: one line saying how it does now, with Check again; the plan's line; and the API key, with,
 * once a key is saved, its monthly limit and spending in view, the switch that allows it and which to use first. Whether
 * Claude Code is signed in is a slow lookup of its own, asked once each time the page opens and again when a key or the
 * order changes; what it last said stays on screen meanwhile.
 */
function TaggingSection({ offline, settings, toast }: TaggingProps) {
  const qc = useQueryClient();
  const tagging = useQuery({ ...taggingQuery(), enabled: !offline });
  const spend = useQuery<TaggingSpend>({ queryKey: queryKeys.spend(), queryFn: api.tagSpend, enabled: false }).data ?? settings.tagging_spend;
  const status = tagging.data ?? null;
  const error = tagging.error ? tagging.error.message : null;
  const waiting = settings.pending_tags;
  const lead = claudeLead(settings, spend, status, error, offline);
  const shows = apiKeyShows(settings);
  const plan = status?.routes.find((r) => r.id === 'plan');
  const planText = error ? 'Not checked.' : !status ? 'Checking…' : plan?.available ? 'Ready to use.' : plan?.detail || 'Not available.';
  const install = <a href={README_CLAUDE_CODE} target="_blank" rel="noreferrer">install Claude Code and sign in</a>;

  return (
    <Section title="Claude" id="s-tagging">
      {offline ? <p className="hint">How Nines reaches Claude can't be checked while you're offline.</p> : (
        <>
          <div className="claude-lead">
            <StatusLine line={lead} testId="claude-lead">
              {lead.action === 'install' && <> <a href={README_CLAUDE_CODE} target="_blank" rel="noreferrer">Install Claude Code and sign in</a>, then check again.</>}
            </StatusLine>
            <Button small disabled={tagging.isFetching} onClick={() => {
              void tagging.refetch();
              void stale(qc, queryKeys.settings(), { exact: true });   // the items waiting
            }}>Check again</Button>
          </div>
          <div className="claude-route" data-testid="route-plan">
            <h3 className="route-name">Your Claude plan</h3>
            <p className={`state-line ${plan?.available ? 'state-ready' : plan ? 'state-missing' : ''}`}>
              <span className="state-dot" aria-hidden="true" />
              <span>{planText}</span>
            </p>
            <p className="hint">
              {plan && !plan.available && lead.action !== 'install' ? <>To use your plan, {install}.</> : 'Costs nothing extra; it counts toward your plan’s limits.'}
            </p>
          </div>
          <div className="claude-route" data-testid="route-api">
            <h3 className="route-name">An API key</h3>
            <ApiKeyBox offline={offline} settings={settings} toast={toast} />
            {shows.spending
              ? <ApiKeySpend offline={offline} settings={settings} spend={spend} toast={toast} />
              : shows.order && <RouteOrderChoice offline={offline} settings={settings} toast={toast} />}
          </div>
        </>
      )}
      {waiting > 0 && (
        <p className="hint" data-testid="tags-waiting">{`${waiting} ${waiting === 1 ? 'item is' : 'items are'} waiting to be described.`}</p>
      )}
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
        <span>{apiKeyLine(info, deviceOf(window.location.hostname) === 'computer')}</span>
      </p>
      {askForKey && (
        <form className="field-row field-row-inline" onSubmit={(e) => void save(e)}>
          <label className="field">
            <span>{info.source === 'keychain' ? 'New API key' : 'Paste your API key'}</span>
            <input type="password" autoComplete="off" spellCheck={false} placeholder="sk-ant-…" value={key}
              disabled={offline || busy} onChange={(e) => setKey(e.target.value)} />
          </label>
          <div className="row">
            <button className="btn" type="submit" disabled={offline || busy || key.trim() === ''}>{busy ? 'Checking…' : 'Save key'}</button>
            {replacing && <button className="btn" type="button" disabled={busy} onClick={() => { setReplacing(false); setKey(''); setError(null); }}>Cancel</button>}
          </div>
        </form>
      )}
      {askForKey && (
        <p className="hint">
          Make one under <a href={ANTHROPIC_KEYS} target="_blank" rel="noreferrer">API keys in your Anthropic account</a>; Nines checks it for free, keeps it in {info.where} and never shows it again.
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
          <p className="row">
            <button className="btn btn-small" type="button" disabled={offline} onClick={() => { setReplacing(true); setError(null); }}>Replace key</button>
            <button className="btn btn-small" type="button" disabled={offline} onClick={() => setRemoving(true)}>Remove key</button>
          </p>
        )
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}

/** Which way to Claude is tried first, as one choice. Choices that put the key first need a key; the key is still only
 * used once it is allowed with a monthly limit. */
function RouteOrderChoice({ offline, settings, toast }: { offline: boolean; settings: Settings; toast: Toast }) {
  const saveSettings = useSaveSettings();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    <div className="route-order" data-testid="route-order">
      <label className="field">
        <span>Which to use</span>
        <select value={settings.tagging_route_order} disabled={offline || busy}
          onChange={(e) => void choose(e.target.value as RouteOrder)}>
          {ROUTE_ORDERS.map((o) => (
            <option key={o.value} value={o.value} disabled={o.needsKey && !hasKey && o.value !== settings.tagging_route_order}>{o.label}</option>
          ))}
        </select>
      </label>
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}

/** Once a key is saved: its monthly limit and this month's spending, in view; the switch that allows it; which to use
 * first; and, folded, the earlier months and how costs are worked out. The spending comes with the settings, so it is
 * drawn with them and follows every save. */
function ApiKeySpend({ offline, settings, spend, toast }: { offline: boolean; settings: Settings; spend: TaggingSpend | null; toast: Toast }) {
  const saveSettings = useSaveSettings();
  const [cap, setCap] = useState(settings.tagging_api_cap_usd !== null ? String(settings.tagging_api_cap_usd) : '');
  const [capError, setCapError] = useState<string | null>(null);
  const saved = settings.tagging_api_cap_usd;

  useEffect(() => setCap(saved !== null ? String(saved) : ''), [saved]);

  /** The limit typed, in dollars, or null after saying what is wrong. */
  function typedCap(): number | null {
    const cents = readCents(cap);
    if (cents === null || cents === undefined || cents <= 0) {
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
  const earlier = spend ? earlierMonths(spend) : [];
  return (
    <div className="api-spend" data-testid="api-spend">
      {settings.tagging_api_off && <p className="form-error" role="alert">{turnedOffLine(settings.tagging_api_off)}</p>}
      <form className="api-limit" onSubmit={(e) => {
        e.preventDefault();
        const limit = typedCap();
        if (limit !== null) void save({ tagging_api_cap_usd: limit }, 'Saved');
      }}>
        <label className="field">
          <span>Monthly limit (US dollars)</span>
          <input inputMode="decimal" value={cap} placeholder={placeholder} disabled={offline}
            onChange={(e) => setCap(e.target.value)} />
        </label>
        <button className="btn" type="submit" disabled={offline || cap.trim() === '' || readCents(cap) === Math.round((saved ?? -1) * 100)}>Save limit</button>
      </form>
      {capError && <p className="form-error" role="alert">{capError}</p>}
      {spend && <p className="hint" data-testid="spend-month">{monthSpentLine(spend)}</p>}
      {spend?.allowed && spend.reached && (
        <p className="notice" role="status">
          This month's limit is reached, so the API key won't be used again until next month or until you raise the limit. Your plan is still used whenever it can be.
        </p>
      )}
      <Toggle label="Allow the API key"
        hint="Each photo is then billed to your Anthropic account, and Nines stops before the month would pass the limit."
        checked={settings.tagging_api_enabled} disabled={offline}
        onChange={(on) => {
          if (!on) return void save({ tagging_api_enabled: false }, 'The API key will not be used');
          const limit = typedCap();
          if (limit !== null) void save({ tagging_api_enabled: true, tagging_api_cap_usd: limit }, `The API key may be used, up to ${formatUsd(limit)} a month`);
        }} />
      <RouteOrderChoice offline={offline} settings={settings} toast={toast} />
      {spend && waitingLine(spend.waiting) && <p className="hint" data-testid="spend-waiting">{waitingLine(spend.waiting)}</p>}
      {spend && (
        <Fold title="Spending so far" testId="spend-more">
          <p className="hint" data-testid="spend-requests">{requestsLine(spend)}</p>
          {saved === null && <p className="hint">{suggestionLine(spend.suggested_cap_usd, spend.per_photo_usd, spend.prices_checked)}</p>}
          {earlier.length > 0 && (
            <dl className="storage-list" aria-label="Spent with the API key, by month" data-testid="spend-history">
              {earlier.map((m) => (
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
        </Fold>
      )}
    </div>
  );
}
