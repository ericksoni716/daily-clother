import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { api } from '../api';
import { PhoneAccess } from '../components/PhoneAccess';
import { ADD_TO_HOME_SCREEN, cameInLine, deviceOf, fromHomeScreen, phoneAccessShows } from '../here';
import { CloudflareDoor } from '../components/CloudflareDoor';
import { WhereYouAre } from '../components/WhereYouAre';
import { LifeQuestions } from '../components/LifeQuestions';
import { LineWords, StyleLines } from '../components/StyleLines';
import { StyleTalk } from '../components/StyleTalk';
import { StatusLine, Toggle } from '../components/Toggle';
import { UpdatesLine } from '../components/Updates';
import { Button, buttonClass, confirmKeys, Notice, PageHeader, Section as UiSection, SegmentedControl, Sheet, useConfirmFocus } from '../components/ui';
import { Link } from '../router';
import { touch } from '../queries';
import { queryKeys } from '../queryKeys';
import { phonePoll, settingsQuery, settingsSaved, taggingQuery, useSaveSettings, writePart } from '../settings';
import { backupLine, claudeLine, computerOnly, mainGroups, type Device, type Group } from '../settingsLines';
import { useApp } from '../store';
import { applyTheme, loadTheme, saveTheme, THEME_CHOICES, type Theme } from '../theme';
import { moreLines, profileLines, shownLines, styleChanged, styleCount } from '../style';
import { MAX_REWEAR, REWEAR_KINDS, rewearWords } from '../trips';
import type { CameIn, LaundrySetting, Profile, RewearKind, Settings, StyleProfile, TaggingSpend } from '../types';

export type Toast = (m: string, k?: 'ok' | 'error') => void;

export const ADVANCED = '/settings/advanced';
export const README_CLAUDE_CODE = 'https://github.com/ericksoni716/daily-clother#installing-claude-code';

/** One group of settings: a card with a heading. */
export function Section({ title, hint, children, id }: { title: string; hint?: string; children: ReactNode; id: string }) {
  return <UiSection id={id} title={title} hint={hint} className="settings-section">{children}</UiSection>;
}

/** "Manage", "Choose a backup folder": a link to the Advanced screen, drawn as a quiet button. */
function ToAdvanced({ children, label }: { children: ReactNode; label?: string }) {
  return <Link to={ADVANCED} className={buttonClass({ variant: 'ghost', small: true })} aria-label={label}>{children}</Link>;
}

/** Light, dark or the device's own setting; kept on this device only, so it works offline too. */
/** This device: its look, and on a device that came in from outside, how it came in (Tailscale or Cloudflare). */
function LookSection({ cameIn }: { cameIn?: CameIn }) {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const line = cameInLine(cameIn);
  return (
    <UiSection id="s-look" title="This device" className="settings-section">
      {line && <p data-testid="came-in">{line}</p>}
      <SegmentedControl label="Look" options={THEME_CHOICES} value={theme} small className="settings-look"
        onChange={(t) => { setTheme(t); saveTheme(t); applyTheme(t); }} />
    </UiSection>
  );
}

/**
 * Your style: what Claude reads about how you dress, as lines with where each came from (the first few here, every one
 * in a sheet to change, remove or add to), the conversation with Claude about it, the whole text to edit in a sheet,
 * and the switch that lets Claude choose. Each closet (the owner's, the demo) keeps its own. Drawn from the settings'
 * answer, which fills its key.
 */
function StyleSection({ offline, profile, settings, toast }: {
  offline: boolean; profile: Profile; settings: Settings; toast: Toast;
}) {
  const saveSettings = useSaveSettings();
  const style = useQuery<StyleProfile>({ queryKey: queryKeys.styleProfile(), queryFn: api.styleProfile, enabled: false }).data ?? settings.style_profile;
  const [open, setOpen] = useState<'talk' | 'lines' | 'text' | null>(null);
  const lines = profileLines(style);
  const { shown, more } = shownLines(lines);
  const toggle = (which: 'talk' | 'lines' | 'text') => setOpen(open === which ? null : which);
  return (
    <Section title="Your style" id="s-style">
      <ol className="style-summary" aria-label="What Claude reads about how you dress" data-testid="style-summary">
        {shown.map((line) => <li key={line.id} className="style-line-words" data-testid="style-summary-line"><LineWords line={line} /></li>)}
      </ol>
      {more > 0 && <p className="muted style-more">{moreLines(more)}</p>}
      <div className="settings-actions style-actions">
        <Button small variant="primary" disabled={offline} aria-expanded={open === 'talk'} onClick={() => toggle('talk')}>Talk to Claude about your style</Button>
        <Button small disabled={offline} aria-expanded={open === 'lines'} onClick={() => toggle('lines')}>{more > 0 ? 'See all lines' : 'Change the lines'}</Button>
        <Button small variant="ghost" disabled={offline} aria-expanded={open === 'text'} onClick={() => toggle('text')}>Edit the text</Button>
      </div>
      {open === 'talk' && (
        <Sheet title="Talk about your style" onClose={() => setOpen(null)} testId="style-talk-sheet">
          <StyleTalk offline={offline} />
        </Sheet>
      )}
      {open === 'lines' && (
        <Sheet title="Your style" onClose={() => setOpen(null)} testId="style-lines-sheet">
          <StyleLines lines={lines} offline={offline} toast={toast} />
        </Sheet>
      )}
      {open === 'text' && <StyleEditor offline={offline} style={style} toast={toast} onClose={() => setOpen(null)} />}
      <Toggle label="Let Claude choose my outfits"
        hint={`When this is off, or Claude can't be reached, Nines' own rules choose.${profile === 'demo' ? ' In the demo closet they always do.' : ''}`}
        checked={settings.stylist_on !== false} disabled={offline}
        onChange={async (on) => {
          try {
            await saveSettings({ stylist_on: on });
            toast('Saved');
          } catch (e) {
            toast((e as Error).message, 'error');
          }
        }} />
    </Section>
  );
}

/** The style text itself, in a sheet: how you like to dress, in your own words. */
function StyleEditor({ offline, style, toast, onClose }: { offline: boolean; style: StyleProfile; toast: Toast; onClose(): void }) {
  const qc = useQueryClient();
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
    <Sheet title="Your style" onClose={onClose} testId="style-sheet">
      <form className="settings-style" onSubmit={(e: FormEvent) => { e.preventDefault(); void save(draft); }}>
        <label className="field">
          <span>About how I dress</span>
          <textarea rows={8} maxLength={style.max_length} value={draft} disabled={offline || busy}
            aria-describedby={countId} onChange={(e) => setDraft(e.target.value)} />
        </label>
        <p className={count.warn ? 'settings-style-count is-warn' : 'settings-style-count'} id={countId}>
          <span className="visually-hidden">Characters used: </span>{count.text}
        </p>
        <p className="hint">Claude reads this every time it chooses your outfits. For example: “No ties unless it is a wedding.”</p>
        <div className="settings-style-actions">
          <button type="submit" className="btn btn-primary" disabled={offline || busy || !styleChanged(draft, style.text)}>Save</button>
          {!style.is_default && (
            <button type="button" className="btn" disabled={offline || busy} onClick={() => void save('')}>Back to the starting text</button>
          )}
        </div>
      </form>
    </Sheet>
  );
}

/** Everyday: the weather's place, how you live, and the laundry. */
function EverydaySection({ offline, profile, settings, toast }: { offline: boolean; profile: Profile; settings: Settings; toast: Toast }) {
  const qc = useQueryClient();
  const [placeOpen, setPlaceOpen] = useState(false);
  const [lifeOpen, setLifeOpen] = useState(false);
  const placeName = settings.place?.name ?? settings.home_place?.name ?? 'New York';
  return (
    <Section title="Everyday" id="s-everyday">
      <div className="settings-row">
        <p>Weather for <strong data-testid="weather-place">{placeName}</strong></p>
        <Button small disabled={offline} aria-expanded={placeOpen} onClick={() => setPlaceOpen(!placeOpen)}>{placeOpen ? 'Done' : 'Change'}</Button>
      </div>
      {placeOpen && (
        <Sheet title="Where you are" onClose={() => setPlaceOpen(false)} testId="place-sheet">
          <WhereYouAre place={settings.place} home={settings.home_place} offline={offline} toast={toast} />
        </Sheet>
      )}
      <div className="settings-row">
        <p>{profile === 'demo' ? 'How you live: example answers.' : settings.life ? 'How you live: your answers are saved.' : 'Wardrobe does not know how you live yet.'}</p>
        {!lifeOpen && (
          <Button small disabled={offline} onClick={() => setLifeOpen(true)}>
            {profile === 'demo' ? 'See example answers' : settings.life ? 'Edit my answers' : 'Tell it how you live'}
          </Button>
        )}
      </div>
      {lifeOpen && (
        <LifeQuestions initial={settings.life ?? null} locked={offline} demo={profile === 'demo'}
          onSaved={(saved) => {
            settingsSaved(qc, saved, 'settings', { life: saved.life, life_prompt_dismissed: true });
            toast('Your answers are saved');
          }} onClose={() => setLifeOpen(false)} />
      )}
      {settings.laundry && <LaundrySection settings={settings} toast={toast} disabled={offline} />}
      {settings.rewear && <RewearSection settings={settings} toast={toast} disabled={offline} />}
    </Section>
  );
}

export const LAUNDRY_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** Laundry that keeps itself: worn clothes go in after their count (Wears between washes), out on the laundry day. */
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
    <>
      <Toggle label="Put worn clothes in the laundry by themselves"
        hint="After the wears set below; shoes, coats and accessories never go."
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
          </label>
        </div>
      )}
    </>
  );
}

/** Wears between washes: how often each kind of clothing is worn before it needs a wash. Folded: the starting
 * numbers suit most people. */
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
    <details className="more settings-rewear-fold" data-testid="rewear">
      <summary>Wears between washes</summary>
      <p className="hint">The laundry and trip packing count with these.</p>
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
    </details>
  );
}

/** Claude: one line saying how Closet reaches it, the one thing to do when it can't, and Manage. */
function ClaudeSection({ offline, settings }: { offline: boolean; settings: Settings }) {
  const qc = useQueryClient();
  const tagging = useQuery({ ...taggingQuery(), enabled: !offline });
  const spend = useQuery<TaggingSpend>({ queryKey: queryKeys.spend(), queryFn: api.tagSpend, enabled: false }).data ?? settings.tagging_spend;
  const line = claudeLine(settings, spend, tagging.data ?? null, tagging.error?.message ?? null, offline);
  const checkAgain = (
    <Button small disabled={tagging.isFetching} onClick={() => {
      void tagging.refetch();
      void qc.invalidateQueries({ queryKey: queryKeys.settings(), exact: true });
    }}>Check again</Button>
  );
  return (
    <Section title="Claude" id="s-claude">
      <StatusLine line={line} testId="claude-line">
        {line.action === 'install' && <> <a href={README_CLAUDE_CODE} target="_blank" rel="noreferrer">Install Claude Code and sign in</a>, then check again.</>}
      </StatusLine>
      <div className="settings-actions">
        {line.action && checkAgain}
        <ToAdvanced label="Manage how Nines reaches Claude">Manage</ToAdvanced>
      </div>
    </Section>
  );
}

/** Your data: the backups in one line; choosing the folder is on the Advanced screen, on the computer. */
function DataSection({ settings, profile, device }: { settings: Settings; profile: Profile; device: Device }) {
  const line = backupLine(settings, profile, device);
  return (
    <Section title="Your data" id="s-data">
      <StatusLine line={line} testId="backup-line" />
      {line.action === 'choose' && <div className="settings-actions"><ToAdvanced>Choose a backup folder</ToAdvanced></div>}
    </Section>
  );
}

/** Log out, and Quit on the computer only: from the phone, Closet could not be started again. */
export function Leave({ offline, device }: { offline: boolean; device: Device }) {
  const { logout, quit, toast } = useApp();
  return (
    <div className="settings-leave" role="group" aria-label="Leave">
      {/* offline the server cannot end the login, so the phone would only look logged out until it is back in reach */}
      <button className="btn" disabled={offline} title={offline ? "You're offline: log out once Nines on your computer can be reached" : undefined}
        onClick={() => void logout()}>Log out</button>
      {computerOnly(device).quit && <QuitButton onQuit={quit} disabled={offline} toast={toast} />}
    </div>
  );
}

export function SettingsScreen({ version }: { version: string }) {
  const { offline, profile, toast } = useApp();
  // connecting the phone is done on the computer; the phone itself is only told how to keep Closet on its Home Screen
  const phoneShows = phoneAccessShows(window.location.hostname, fromHomeScreen(window));
  const device = deviceOf(window.location.hostname);

  // One quick read draws the page; on the computer it is asked again every few seconds until the phone has an address.
  const read = useQuery({ ...settingsQuery(), enabled: !offline, refetchInterval: (q) => phonePoll(phoneShows, q.state.data, offline) });
  // how Claude is reached is a slow lookup of its own, started at once beside it; asked each time the page opens
  useQuery({ ...taggingQuery(), enabled: !offline, refetchOnMount: 'always' });

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
            <Leave offline={offline} device={device} />
          </div>
        )}
      </div>
    );
  }

  const group: Record<Group, ReactNode> = {
    style: <StyleSection key="style" offline={offline} profile={profile} settings={settings} toast={toast} />,
    everyday: <EverydaySection key="everyday" offline={offline} profile={profile} settings={settings} toast={toast} />,
    claude: <ClaudeSection key="claude" offline={offline} settings={settings} />,
    updates: (
      <Section key="updates" title="Updates" id="s-updates">
        <UpdatesLine offline={offline} toast={toast} version={settings.version ?? version} />
      </Section>
    ),
    phone: (
      <Section key="phone" title="Phone" id="s-phone">
        {phoneShows === 'connect' ? <PhoneAccess phone={settings.phone} /> : <p>{ADD_TO_HOME_SCREEN}</p>}
        {computerOnly(device).cloudflare && settings.cloudflare && <CloudflareDoor door={settings.cloudflare} offline={offline} toast={toast} />}
      </Section>
    ),
    device: <LookSection key="device" cameIn={settings.came_in} />,
    data: <DataSection key="data" settings={settings} profile={profile} device={device} />,
    leave: (
      <div key="leave" className="settings-foot">
        <Link to={ADVANCED} className="settings-advanced-link" data-testid="advanced-link">Advanced settings</Link>
        <Leave offline={offline} device={device} />
      </div>
    ),
  };

  return (
    <div className="settings">
      <PageHeader title="Settings" />
      {offline && <Notice as="p">You're offline, so settings can't be shown or changed right now.</Notice>}
      {!offline && read.error && <p className="form-error" role="alert">{read.error.message}</p>}
      <div className="settings-groups">
        {mainGroups(phoneShows).map((g) => group[g])}
      </div>
    </div>
  );
}

function QuitButton({ onQuit, disabled, toast }: { onQuit(): Promise<void>; disabled: boolean; toast: Toast }) {
  const [confirming, setConfirming] = useState(false);
  const back = useConfirmFocus(confirming);
  if (!confirming) return <button ref={back} className="btn btn-block btn-danger-quiet" disabled={disabled} onClick={() => setConfirming(true)}>Quit Nines</button>;
  return (
    <div className="confirm" role="alertdialog" aria-labelledby="quit-q" onKeyDown={confirmKeys(() => setConfirming(false))}>
      <p id="quit-q"><strong>Quit Nines?</strong> Your phone won't be able to reach it until you start it again on this computer.</p>
      <div className="row">
        <button className="btn btn-danger" autoFocus onClick={() => onQuit().catch((e) => toast((e as Error).message, 'error'))}>Quit</button>
        <button className="btn" onClick={() => setConfirming(false)}>Cancel</button>
      </div>
    </div>
  );
}
