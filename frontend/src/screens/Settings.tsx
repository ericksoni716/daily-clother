import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { PhoneAccess } from '../components/PhoneAccess';
import { ADD_TO_HOME_SCREEN, fromHomeScreen, phoneAccessShows } from '../here';
import { WhereYouAre } from '../components/WhereYouAre';
import { LifeQuestions } from '../components/LifeQuestions';
import { UpdatesSection } from '../components/Updates';
import { confirmKeys, Notice, PageHeader, Section as UiSection, SegmentedControl, useConfirmFocus } from '../components/ui';
import { formatDateTime, formatSize, parsePrice } from '../labels';
import { Link } from '../router';
import { apiKeyLine, apiKeySavedLine, dayName, firstRouteLine, formatUsd, monthName, ROUTE_ORDERS, spentLine, suggestionLine, turnedOffLine, waitingLine } from '../spend';
import { touch, useModel } from '../queries';
import { queryKeys } from '../queryKeys';
import { phonePoll, routeIds, settingsQuery, settingsSaved, storageQuery, taggingQuery, useSaveSettings, weatherQuery, writePart } from '../settings';
import { useApp } from '../store';
import { applyTheme, loadTheme, saveTheme, THEME_CHOICES, type Theme } from '../theme';
import { styleChanged, styleCount } from '../style';
import { MAX_REWEAR, REWEAR_KINDS, rewearWords } from '../trips';
import type { LaundrySetting, ModelInfo, Profile, RewearKind, RouteOrder, Settings, StyleProfile, TaggingRoute, TaggingSpend } from '../types';

type Toast = (m: string, k?: 'ok' | 'error') => void;

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

/** "Your style": how the owner likes to dress, in their own words. Claude reads it when it chooses the outfits; each
 * closet (the owner's, the demo) keeps its own. Drawn from the settings' answer, which fills its key. */
function StyleSection({ offline, profile, settings, toast }: {
  offline: boolean; profile: Profile; settings: Settings; toast: Toast;
}) {
  const qc = useQueryClient();
  const saveSettings = useSaveSettings();
  const style = useQuery<StyleProfile>({ queryKey: queryKeys.styleProfile(), queryFn: api.styleProfile, enabled: false }).data ?? settings.style_profile;
  const [draft, setDraft] = useState(style.text);
  const [shown, setShown] = useState(style.text);
  const [busy, setBusy] = useState(false);
  const countId = useId();
  if (shown !== style.text) {   // saved here or elsewhere: the box shows what is now in force
    setShown(style.text);
    setDraft(style.text);
  }

  async function save(text: string) {
    setBusy(true);
    try {
      const saved = await api.saveStyleProfile(text);
      writePart(qc, { style_profile: saved });
      void touch(qc, 'styleProfile', ['styleProfile']);
      setDraft(saved.text);
      toast('Saved');
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  const count = styleCount(draft.length, style.max_length);
  return (
    <Section title="Your style" id="s-style"
      hint="How you like to dress, in your own words. Claude reads this every time it chooses your outfits, and it wins over the general menswear guide. Write it the way you would tell a friend who is choosing your clothes.">
      <Toggle label="Let Claude choose my outfits"
        hint={`When this is off, or Claude can't be reached, Closet's own rules choose.${profile === 'demo' ? ' In the demo closet they always do.' : ''}`}
        checked={settings.stylist_on !== false} disabled={offline}
        onChange={async (on) => {
          try {
            await saveSettings({ stylist_on: on });
            toast('Saved');
          } catch (e) {
            toast((e as Error).message, 'error');
          }
        }} />
      <form className="settings-style" onSubmit={(e: FormEvent) => { e.preventDefault(); void save(draft); }}>
        <label className="field">
          <span>About how I dress</span>
          <textarea rows={8} maxLength={style.max_length} value={draft} disabled={offline || busy}
            aria-describedby={countId} onChange={(e) => setDraft(e.target.value)} />
        </label>
        <p className={count.warn ? 'settings-style-count is-warn' : 'settings-style-count'} id={countId}>
          <span className="visually-hidden">Characters used: </span>{count.text}
        </p>
        <p className="hint">For example: “I run warm, so one layer fewer than most people.” “No ties unless it is a wedding.” “I like navy with brown, and I never wear black shoes with jeans.”</p>
        <div className="settings-style-actions">
          <button type="submit" className="btn btn-primary" disabled={offline || busy || !styleChanged(draft, style.text)}>Save</button>
          {!style.is_default && (
            <button type="button" className="btn" disabled={offline || busy} onClick={() => void save('')}>Back to the starting text</button>
          )}
        </div>
      </form>
    </Section>
  );
}

/** Log out and Quit, at the foot of the page. */
function Leave({ offline }: { offline: boolean }) {
  const { logout, quit, toast } = useApp();
  return (
    <div className="settings-leave" role="group" aria-label="Leave">
      {/* offline the server cannot end the login, so the phone would only look logged out until it is back in reach */}
      <button className="btn" disabled={offline} title={offline ? "You're offline: log out once Closet on your computer can be reached" : undefined}
        onClick={() => void logout()}>Log out</button>
      <QuitButton onQuit={quit} disabled={offline} toast={toast} />
    </div>
  );
}

export function SettingsScreen({ version }: { version: string }) {
  const { offline, profile, switchProfile, toast } = useApp();
  const qc = useQueryClient();
  const saveSettings = useSaveSettings();
  const model = useModel();
  const [lifeOpen, setLifeOpen] = useState(false);
  // connecting the phone is done on the computer; the phone itself is only told how to keep Closet on its Home Screen
  const phoneShows = phoneAccessShows(window.location.hostname, fromHomeScreen(window));

  // One quick read draws the page; on the computer it is asked again every few seconds until the phone has an address.
  const read = useQuery({ ...settingsQuery(), enabled: !offline, refetchInterval: (q) => phonePoll(phoneShows, q.state.data, offline) });
  // the slow lookups start at once, beside it, and each fills a row of its own
  useQuery({ ...taggingQuery(), enabled: !offline, refetchOnMount: 'always' });
  useQuery({ ...storageQuery(), enabled: !offline });
  useQuery({ ...weatherQuery(), enabled: !offline });

  const settings = read.data;
  if (!settings) {
    return (
      <div className="settings">
        <PageHeader title="Settings" />
        {offline ? <Notice as="p">You're offline, so settings can't be shown or changed right now.</Notice>
          : read.error ? (
            <>
              <p className="form-error" role="alert">{read.error.message}</p>
              <button className="btn" onClick={() => void read.refetch()}>Try again</button>
            </>
          ) : <p className="hint" aria-busy="true">Opening your settings…</p>}
        {offline && (
          <div className="settings-groups">
            <LookSection />
            <Leave offline={offline} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="settings">
      <PageHeader title="Settings" />
      {offline && <Notice as="p">You're offline, so settings can't be shown or changed right now.</Notice>}
      {!offline && read.error && <p className="form-error" role="alert">{read.error.message}</p>}

      <div className="settings-groups">
        <Section title="Your closet" id="s-closet">
          <Toggle
            label="Show the demo closet"
            hint="About 30 sample clothes to try things out with. Your own closet is kept separately and is not touched."
            checked={profile === 'demo'}
            disabled={offline}
            onChange={(on) => switchProfile(on ? 'demo' : 'main').catch((e) => toast((e as Error).message, 'error'))}
          />
          {settings.autostart !== null && (
            <Toggle label="Start Closet when I log in" hint="Closet opens quietly in the background when you sign in to this computer."
              checked={settings.autostart} disabled={offline}
              onChange={async (on) => {
                try {
                  await saveSettings({ autostart: on });
                  toast('Saved');
                } catch (e) {
                  toast((e as Error).message, 'error');
                }
              }} />
          )}
          {settings.laundry && <LaundrySection settings={settings} toast={toast} disabled={offline} />}
          {settings.rewear && <RewearSection settings={settings} toast={toast} disabled={offline} />}
          <BackupSection settings={settings} toast={toast} disabled={offline} />
          <StorageSection offline={offline} profile={profile} />
        </Section>

        <Section title="Where you are" id="s-place">
          <WhereYouAre place={settings.place} home={settings.home_place} offline={offline} toast={toast} />
          <p className="hint">Going away? <Link to="/trips">Plan a trip</Link> and Closet says what to pack for the weather there.</p>
        </Section>
        <Section title="How you live" id="s-life">
          <p className="hint">Tell What's missing about work, everyday life and time away. Change your answers whenever life changes.</p>
          {lifeOpen ? (
            <LifeQuestions initial={settings.life ?? null} locked={offline} demo={profile === 'demo'}
              onSaved={(saved) => {
                settingsSaved(qc, saved, 'settings', { life: saved.life, life_prompt_dismissed: true });
                toast('Your answers are saved');
              }} onClose={() => setLifeOpen(false)} />
          ) : <button className="btn" disabled={offline} onClick={() => setLifeOpen(true)}>
            {profile === 'demo' ? 'See example answers' : settings.life ? 'Edit my answers' : 'Tell it how you live'}
          </button>}
        </Section>

        <LookSection />

        <StyleSection offline={offline} profile={profile} settings={settings} toast={toast} />

        <TaggingSection offline={offline} settings={settings} toast={toast} />

        <Section title="Updates" id="s-updates" hint="New versions of Closet, from its GitHub releases.">
          <UpdatesSection offline={offline} toast={toast} />
        </Section>

        {phoneShows !== 'nothing' && (
          <Section title="Phone access" id="s-phone">
            {phoneShows === 'connect' ? <PhoneAccess phone={settings.phone} /> : <p>{ADD_TO_HOME_SCREEN}</p>}
          </Section>
        )}

        <details className="card settings-advanced" id="s-advanced">
          <summary>Advanced</summary>
          <div className="settings-advanced-body">
            <ModelAddress model={model ?? settings.model} toast={toast} disabled={offline} />
            <dl className="facts">
              <dt>Your closet is stored in</dt>
              <dd><code className="path">{settings.data_dir}</code></dd>
              <dt>Version</dt>
              <dd>{settings.version ?? version}</dd>
            </dl>
          </div>
        </details>

        <Leave offline={offline} />
      </div>
    </div>
  );
}

/** Where the background-removal model is downloaded from, and where to put it by hand. */
function ModelAddress({ model, toast, disabled }: { model: ModelInfo; toast: Toast; disabled: boolean }) {
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
      {model.second && (
        <>
          <p className="hint">The second model works the same way. Its file is at this address:</p>
          <p><code className="path">{model.second.url}</code></p>
          <p className="hint">and goes here:</p>
          <p><code className="path">{model.second.path}</code></p>
        </>
      )}
    </Sub>
  );
}

export const LAUNDRY_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** Laundry that keeps itself: worn clothes go in after their count ("Before it needs washing"), out on the laundry day. */
function LaundrySection({ settings, toast, disabled }: { settings: Settings; toast: Toast; disabled: boolean }) {
  const saveSettings = useSaveSettings();
  const [busy, setBusy] = useState(false);
  const laundry = settings.laundry!;

  async function save(change: Partial<LaundrySetting>) {
    setBusy(true);
    try {
      await saveSettings({ laundry: { ...laundry, ...change } });
      toast('Saved');
    } catch (err) {
      toast((err as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sub title="Laundry" id="s-laundry">
      <Toggle label="Put worn clothes in the laundry by themselves"
        hint="When you record a wear, a piece goes in the laundry once it has been worn as often as Before it needs washing says. Shoes, coats and accessories never do. Undo the wear and it comes back out."
        checked={laundry.auto} disabled={disabled || busy} onChange={(auto) => void save({ auto })} />
      {laundry.auto && (
        <div className="settings-laundry">
        <label className="field">
          <span>Laundry day</span>
          <select value={laundry.day === null ? '' : String(laundry.day)} disabled={disabled || busy}
            onChange={(e) => void save({ day: e.target.value === '' ? null : Number(e.target.value) })}>
            {LAUNDRY_DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
            <option value="">No set day: I mark things clean myself</option>
          </select>
          <span className="hint">Everything in the laundry is clean again from this day. All clean on the closet works any time.</span>
        </label>
        </div>
      )}
    </Sub>
  );
}

/** "Before it needs washing": how often each kind of clothing is worn before it needs a wash. */
function RewearSection({ settings, toast, disabled }: { settings: Settings; toast: Toast; disabled: boolean }) {
  const saveSettings = useSaveSettings();
  const [busy, setBusy] = useState(false);
  const rewear = settings.rewear!;

  async function save(kind: RewearKind, value: string) {
    setBusy(true);
    try {
      await saveSettings({ rewear: { [kind]: value === '' ? null : Number(value) } });
      toast('Saved');
    } catch (err) {
      toast((err as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sub title="Before it needs washing" id="s-rewear">
      <p className="hint">How many times you wear each kind before it needs washing. The laundry and trip packing count with these; on a hot or humid day on a trip, what is worn next to the skin is worn once.</p>
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

function BackupSection({ settings, toast, disabled }: { settings: Settings; toast: Toast; disabled: boolean }) {
  const qc = useQueryClient();
  const saveSettings = useSaveSettings();
  const [folder, setFolder] = useState(settings.backup_folder ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setFolder(settings.backup_folder ?? ''), [settings.backup_folder]);
  const last = settings.last_backup;

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

/** The space used: a slow walk of the closet's folders, so the rows are drawn at once and filled in when it is done. */
function StorageSection({ offline, profile }: { offline: boolean; profile: Profile }) {
  const { data: storage, error, refetch, isFetching } = useQuery({ ...storageQuery(), enabled: !offline });

  let body: ReactNode;
  if (offline) body = <p className="hint">Storage details aren't available while you're offline.</p>;
  else if (error && !storage) {
    body = (
      <>
        <p className="form-error" role="alert">Couldn't work out how much space Closet uses: {error.message}</p>
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
        <p className="storage-total" aria-busy={!storage}>
          {storage ? (
            <>
              <strong data-testid="storage-total">{formatSize(storage.total_bytes)}</strong> used by{' '}
              {storage.items === 1 ? '1 item' : `${storage.items} items`}
            </>
          ) : <span className="muted">Adding up how much space Closet uses…</span>}
        </p>
        <dl className="storage-list">
          {rows.map(([name, bytes]) => (
            <div key={name}>
              <dt>{name}</dt>
              <dd>{size(bytes)}</dd>
            </div>
          ))}
        </dl>
        {!storage ? <p className="hint">… free on this disk.</p>
          : storage.free_bytes !== null && <p className="hint">{formatSize(storage.free_bytes)} free on this disk.</p>}
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
  settings: Settings;
  toast: Toast;
}

/** How Closet reaches Claude. Whether Claude Code is signed in is a slow lookup of its own, asked once each time the
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
        <p className="form-error" role="alert">Couldn't check how Closet can reach Claude: {error}</p>
        <button className="btn" disabled={tagging.isFetching} onClick={() => void tagging.refetch()}>Try again</button>
      </>
    );
  } else if (!status) {
    // the same shape as the answer (a line, then the button), so nothing below moves when it lands
    routeState = (
      <>
        <p className="hint" aria-busy="true">Checking how Closet can reach Claude…</p>
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
      <p className="hint" data-testid="tags-waiting">
        {waiting === 0 ? 'No items are waiting to be described.'
          : `${waiting} ${waiting === 1 ? 'item is' : 'items are'} waiting to be described.`}
      </p>
      <ApiKeySpend offline={offline} settings={settings} toast={toast} />
    </Section>
  );
}

const ANTHROPIC_KEYS = 'https://console.anthropic.com/settings/keys';

/** Paste an API key: Closet checks it with Anthropic and keeps it in the computer's keychain. The page never
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
