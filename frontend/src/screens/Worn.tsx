import { backByWearing, recordedSentence } from '../away';
import { queryOptions, useQueries, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent, type ReactNode, type RefObject } from 'react';
import { api, ApiError, connection } from '../api';
import { ChevronIcon, ChevronLeftIcon, HangerIcon, MoreIcon, PlusIcon } from '../components/Icons';
import { Pic } from '../components/ItemPic';
import { nameOf, OutfitPics } from '../components/OutfitPics';
import { DaySheet } from '../components/DaySheet';
import { BackLink, Button, buttonClass, Card, EmptyState, Failed, PageHeader, SaveStatus, SegmentedControl, Sheet, ShowMore, useSaveStatus } from '../components/ui';
import { goneLine, KEPT_EMPTY, KEPT_NAME_MAX, keptToast, keptWhen, type KeptOutfit } from '../kept';
import { label } from '../labels';
import { setLaundryMany } from '../laundry';
import { newActionId, outboxFor, withKeptRatings, type RateAction } from '../outbox';
import { keptQuery, plansQuery, touch, useAllItems, useEdit, useItems, writeItem } from '../queries';
import { queryKeys } from '../queryKeys';
import { Link, navigate } from '../router';
import { ItemDetail } from './ItemDetail';
import { useApp } from '../store';
import { occasionLabel } from '../today';
import { tripsQuery } from './Trips';
import type { ItemSummary } from '../types';
import { localDay } from '../wears';
import {
  contextWords, joinPages, RATINGS, ratingLabel, ratingSummary, reasonLabel, reasonsFor, loadSavedWorn, recordGroups, saveWorn, withOutfit,
  withoutOutfit, withRecorded, wornDay, wornIds, type Rating, type Reason, type WornOutfit, type WornPage,
} from '../worn';

/** The kinds of piece that go in the wash after a day's wear (not shoes, coats, jackets or accessories). */
const WASHED = new Set(['tee', 'shirt', 'polo', 'sweater', 'hoodie', 'jeans', 'trousers', 'shorts']);
import './Worn.css';

const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';

/** The three answers, then the reasons that fit the answer; each tap is saved straight away. Used by the Worn list and by
 * Today's question. While Nines cannot be reached, a tap is kept on this phone and sent when it answers (`outbox.ts`):
 * it shows at once as if it had been sent, and the banner over the page says it is kept. */
export function RateOutfit({ outfit, offline, onRated, compact }: {
  outfit: WornOutfit; offline: boolean; onRated(o: WornOutfit): void; compact?: boolean;
}) {
  const qc = useQueryClient();
  const { profile } = useApp();
  const status = useSaveStatus();
  const [note, setNote] = useState(outfit.rating_note ?? '');
  const locked = status.state === 'saving';

  // each tap saves at once and says so beside the answers: "Saving…", "Saved", or "Didn't save" with Try again
  function save(rating: Rating | null, reasons: Reason[], noteText: string | null) {
    return status.run(async () => {
      const kept: RateAction = {
        kind: 'rate', id: newActionId(), at: new Date().toISOString(), outfit_id: outfit.id, worn_on: outfit.worn_on,
        rating, reasons, note: reasons.includes('other') ? noteText : null,
        before: { rating: outfit.rating, reasons: outfit.rating_reasons, note: outfit.rating_note },
      };
      const sent = await outboxFor(profile).send<WornOutfit>(kept);
      const o = sent.kept
        ? { ...outfit, rating: kept.rating, rating_reasons: kept.reasons, rating_note: kept.note, rated_at: kept.rating ? kept.at : null }
        : sent.answer;
      changePages(qc, (page) => withOutfit(page, o));
      if (!sent.kept) void touch(qc, 'outfit');
      onRated(o);
    });
  }

  const reasons = outfit.rating_reasons;
  const toggle = (r: Reason) => {
    const next = reasons.includes(r) ? reasons.filter((x) => x !== r) : [...reasons, r];
    void save(outfit.rating, next, r === 'other' ? null : note.trim() || null);
  };

  return (
    <div className={`rate${compact ? ' rate-compact' : ''}`}>
      <div className="chips rate-answers" role="group" aria-label="How it went">
        {RATINGS.map((r) => (
          <button key={r} type="button" className={`chip${outfit.rating === r ? ' is-on' : ''}`} aria-pressed={outfit.rating === r}
            disabled={locked}
            onClick={() => void save(outfit.rating === r ? null : r, outfit.rating === r ? [] : reasons.filter((x) => reasonsFor(r).includes(x)), note.trim() || null)}>
            {ratingLabel(r)}
          </button>
        ))}
      </div>
      {outfit.rating && (
        <>
          <p className="chip-group-title rate-why">Why? (if you like)</p>
          <div className="chips" role="group" aria-label="Why">
            {reasonsFor(outfit.rating).map((r) => (
              <button key={r} type="button" className={`chip${reasons.includes(r) ? ' is-on' : ''}`} aria-pressed={reasons.includes(r)}
                disabled={locked} onClick={() => toggle(r)}>
                {reasonLabel(r)}
              </button>
            ))}
          </div>
          {reasons.includes('other') && (
            <form className="rate-note" onSubmit={(e: FormEvent) => { e.preventDefault(); void save(outfit.rating, reasons, note.trim() || null); }}>
              <label className="field">
                <span>What else?</span>
                <input value={note} maxLength={300} disabled={locked} onChange={(e) => setNote(e.target.value)} />
              </label>
              <button className="btn btn-small" disabled={locked || note.trim() === (outfit.rating_note ?? '')}>Save note</button>
            </form>
          )}
        </>
      )}
      {!offline && <SaveStatus state={status.state} onRetry={status.retry} className="rate-status" />}
    </div>
  );
}

/** How many outfits Recent outfits shows on Today: three on a phone, a week's worth on a wider screen. */
const RECENT = { first: 3, wide: 7 };

/**
 * The last outfits worn, on Today (DESIGN: Today takes in Worn): each with its pieces and how it went, rated in place,
 * then "See all" for the whole history, where an outfit is recorded by hand, worn again or removed. `children` is the
 * question about yesterday's outfit, asked first.
 */
export function RecentOutfits({ outfits, byId, offline, children }: {
  outfits: WornOutfit[]; byId: Map<string, ItemSummary>; offline: boolean; children?: ReactNode;
}) {
  return (
    <section className="recent" aria-labelledby="recent-title" data-testid="recent-outfits">
      <h2 id="recent-title" className="recent-title">Recent outfits</h2>
      {children}
      {outfits.length === 0 ? (
        <p className="muted recent-none">The outfits you wear show here, to say how each one went.{' '}
          <Link to="/today/worn">Record one by hand</Link></p>
      ) : (
        <ShowMore items={outfits.slice(0, RECENT.wide)} first={RECENT.first} wide={RECENT.wide} to="/today/worn" total={null}
          as="ol" className="recent-list" label="Recent outfits" keyOf={(o) => o.id}
          render={(o) => <RecentCard outfit={o} byId={byId} offline={offline} />} />
      )}
    </section>
  );
}

/** One recent outfit: the day, its pieces, and how it went (the three answers when it has none yet). */
function RecentCard({ outfit, byId, offline }: { outfit: WornOutfit; byId: Map<string, ItemSummary>; offline: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Card as="article" className="recent-card" aria-label={`Worn ${wornDay(outfit)}`} data-testid="recent-outfit">
      <h3 className="recent-day">{wornDay(outfit)}</h3>
      <OutfitPics outfit={outfit} byId={byId} />
      {outfit.rating && !open ? (
        <button type="button" className={`chip worn-rating is-${outfit.rating}`} data-testid="worn-rating" aria-expanded={false}
          aria-label={`${ratingSummary(outfit)}. Change rating`} onClick={() => setOpen(true)}>
          <span>{ratingSummary(outfit)}</span>
          <ChevronIcon aria-hidden="true" className="worn-rating-chevron" />
        </button>
      ) : (
        <RateOutfit outfit={outfit} offline={offline} compact onRated={() => setOpen(true)} />
      )}
    </Card>
  );
}

/** A page of worn outfits as read, and when it was asked for (null: the copy kept on this device, shown offline). */
export interface WornRead {
  page: WornPage;
  at: number | null;
}

/**
 * A page of worn outfits, newest first (`before`: the cursor the page before gave; null for the first page). The
 * first page is the one Today reads too, and it is kept on this device for offline: when Nines on the computer
 * cannot be reached, this closet's saved copy is given instead. Made stale by the edits that touch `worn`.
 */
export const wornQuery = (profile: string, before: string | null = null) => queryOptions({
  queryKey: queryKeys.worn(before),
  queryFn: async (): Promise<WornRead> => {
    // what this phone kept goes to Nines first, so a fresh page never shows a rating from before it (then it shows on
    // whichever page comes back, the saved copy too, while it is still kept)
    const box = outboxFor(profile);
    if (!connection.offline) await box.flush();
    const started = Date.now();
    try {
      const page = await api.wornOutfits(before);
      if (before === null) saveWorn(profile, page);
      return { page: withKeptRatings(page, box.list), at: navigator.onLine !== false ? started : null };
    } catch (e) {
      const saved = before === null && (e as ApiError).status === 0 ? loadSavedWorn(profile) : null;
      if (saved) return { page: withKeptRatings(saved.page, box.list), at: null };
      throw e;
    }
  },
});

/** Changes every page of worn outfits read so far (a save answered with the outfit), before they are read again. */
export function changePages(qc: QueryClient, change: (page: WornPage) => WornPage): void {
  qc.setQueriesData<WornRead>({ queryKey: [queryKeys.worn()[0]] }, (d) => {
    if (!d) return d;
    const page = change(d.page);
    return page === d.page ? d : { ...d, page };
  });
}

/** The switch at the top of Worn: what you wore, or the outfits you keep (each half its own address). */
function WornSwitch({ kept }: { kept: boolean }) {
  return (
    <SegmentedControl label="Show" small className="worn-switch" value={kept ? 'kept' : 'worn'}
      options={[{ value: 'worn', label: 'What you wore', to: '/today/worn' }, { value: 'kept', label: 'Outfits you keep', to: '/today/worn/kept' }]} />
  );
}

export function WornScreen({ itemId, kept = false }: { itemId: string | null; kept?: boolean }) {
  if (itemId) {
    return (
      <div className="today-item">
        <div className="detail-top">
          <BackLink to="/today/worn" className="btn btn-ghost back-link"><ChevronLeftIcon /> Worn</BackLink>
        </div>
        <ItemDetail key={itemId} id={itemId} status="active" inPanel />
      </div>
    );
  }
  return kept ? <KeptList /> : <WornList />;
}

function WornList() {
  const { profile, offline, toast } = useApp();
  const qc = useQueryClient();
  const items = useItems('active').data ?? null;
  const [adding, setAdding] = useState(false);
  const recordButton = useRef<HTMLButtonElement>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // The pages shown: the first, then each asked for with the cursor of the page before it as it now stands, so a
  // first page read again after an edit (an outfit recorded) leaves no outfit out between it and the next.
  const [count, setCount] = useState(1);
  const cursors: (string | null)[] = [null];
  for (let i = 1; i < count; i++) {
    const next = qc.getQueryData<WornRead>(queryKeys.worn(cursors[i - 1]))?.page.next;
    if (!next) break;
    cursors.push(next);
  }
  const pages = useQueries({ queries: cursors.map((c) => wornQuery(profile, c)) });
  const first = pages[0];
  const list = first.data ? joinPages(pages.map((p) => p.data?.page)) : null;
  const next = pages[pages.length - 1].data?.page.next ?? null;
  const error = first.error && !first.data
    ? ((first.error as ApiError).status === 0 ? "You're offline, and the worn outfits were not saved on this device yet." : 'failed')
    : null;

  async function more() {
    if (!next) return;
    setLoadingMore(true);
    try {
      await qc.fetchQuery(wornQuery(profile, next));
      setCount(cursors.length + 1);
    } catch (e) {
      toast((e as ApiError).message, 'error');
    } finally {
      setLoadingMore(false);
    }
  }

  const byId = useAllItems();

  return (
    <div className="worn">
      <PageHeader title="Worn" back={{ to: '/today', label: 'Today' }} count={list && <>{list.length}{next ? '+' : ''} {list.length === 1 ? 'outfit' : 'outfits'}</>}
        secondary={(
          <button ref={recordButton} type="button" className={buttonClass({})} disabled={offline} title={offline ? OFFLINE_TITLE : undefined}
            aria-haspopup="dialog" aria-expanded={adding} onClick={() => setAdding(true)}>
            <PlusIcon /> Record an outfit
          </button>
        )} />
      <WornSwitch kept={false} />
      <p className="hint worn-intro">Outfits you wore, newest first. Say how each one went and the outfits Today offers learn from it.</p>

      {adding && (
        <RecordByHand items={items ?? []} anchor={recordButton} onCancel={() => setAdding(false)}
          onDone={(o, back) => {
            setAdding(false);
            qc.setQueryData<WornRead>(queryKeys.worn(), (d) => d && { ...d, page: withRecorded(d.page, o) });
            toast(recordedSentence(back));
          }} />
      )}

      {error === 'failed' ? <Failed query={first} what="your worn outfits" />
        : error ? <p className="notice" role="alert">{error}</p> : first.data && <Failed query={first} what="your worn outfits" />}
      {list === null && !error && <p className="muted"><span className="spinner" aria-hidden="true" /> Loading…</p>}
      {list && list.length === 0 && (
        <EmptyState icon={<HangerIcon />} title="No outfits worn yet" body={'Tap "I\'m wearing this" on Today, or record one here.'} />
      )}
      {list && list.length > 0 && (
        <ol className="worn-list" aria-label="Worn outfits">
          {list.map((o) => (
            <li key={o.id}>
              <WornCard outfit={o} byId={byId} offline={offline} onRated={() => undefined}
                onRemoved={() => changePages(qc, (page) => withoutOutfit(page, o.id))} />
            </li>
          ))}
        </ol>
      )}
      {next && (
        <button className="btn worn-more" disabled={loadingMore || offline} title={offline ? OFFLINE_TITLE : undefined} onClick={() => void more()}>
          {loadingMore ? 'Loading…' : 'Show more'}
        </button>
      )}
    </div>
  );
}

function WornCard({ outfit, byId, offline, onRated, onRemoved }: {
  outfit: WornOutfit; byId: Map<string, ItemSummary>; offline: boolean; onRated(o: WornOutfit): void; onRemoved(): void;
}) {
  const { toast } = useApp();
  const qc = useQueryClient();
  const removed = useEdit('outfit');
  const [confirm, setConfirm] = useState(false);
  // the clothes of the outfit that go in the wash, still in the closet and not in the laundry already
  const washable = wornIds(outfit.pieces).filter((id) => {
    const item = byId.get(id);
    return item && item.status !== 'archived' && item.laundry !== 'laundry' && WASHED.has(item.category ?? '');
  });
  async function toLaundry() {
    const failed = await setLaundryMany(washable, 'laundry', (item) => writeItem(qc, item));
    if (failed < washable.length) void touch(qc, 'laundry', ['items', 'item']);
    toast(failed ? `${failed} could not be put in the laundry. Try again.` : `${washable.length === 1 ? 'It is' : `${washable.length} pieces are`} in the laundry`,
      failed ? 'error' : 'ok');
  }
  const [busy, setBusy] = useState(false);
  const [rating, setRating] = useState(false);
  const title = offline ? OFFLINE_TITLE : undefined;
  const day = contextWords(outfit.context, occasionLabel);

  async function keep() {
    try {
      const answer = await api.keepOutfit({ ...outfit.pieces, accessories: outfit.pieces.accessories ?? [] });
      void touch(qc, 'kept');
      toast(keptToast(answer));
    } catch (e) {
      toast((e as ApiError).message, 'error');
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await removed(() => api.removeOutfit(outfit.id));
      onRemoved();
      toast('Outfit removed');
    } catch (e) {
      toast((e as ApiError).message, 'error');
      setBusy(false);
    }
  }

  return (
    <Card as="article" className="worn-card" aria-label={`Worn ${wornDay(outfit)}`} data-testid="worn-outfit">
      <div className="worn-card-head">
        <div className="worn-card-when">
          <h2>{wornDay(outfit)}</h2>
          {day && <p className="muted worn-day">{day}{outfit.recorded_by === 'hand' ? ' · recorded by hand' : ''}</p>}
          {!day && outfit.recorded_by === 'hand' && <p className="muted worn-day">Recorded by hand</p>}
        </div>
        <OutfitMenu offline={offline}
          onAgain={() => navigate(`/today?again=${encodeURIComponent(outfit.id)}`)}
          onLaundry={washable.length ? () => void toLaundry() : undefined}
          onKeep={() => void keep()}
          onRemove={() => setConfirm(true)} />
      </div>
      <OutfitPics outfit={outfit} byId={byId} from="/today/worn" />
      {outfit.rating ? (
        <button type="button" className={`chip worn-rating is-${outfit.rating}`} data-testid="worn-rating" aria-expanded={rating}
          aria-label={`${ratingSummary(outfit)}. Change rating`} onClick={() => setRating(!rating)}>
          <span>{ratingSummary(outfit)}</span>
          <ChevronIcon aria-hidden="true" className="worn-rating-chevron" />
        </button>
      ) : (
        <p className="worn-rating" data-testid="worn-rating">{ratingSummary(outfit)}</p>
      )}
      {rating || !outfit.rating ? (
        <RateOutfit outfit={outfit} offline={offline} onRated={(o) => {
          if (!outfit.rating) setRating(true);   // the reasons stay open after the first answer
          onRated(o);
        }} />
      ) : null}
      {confirm && (
        <div className="worn-confirm" role="group" aria-label="Remove this outfit?">
          <span>Remove it? The wears it recorded go too.</span>
          <button className="btn btn-small btn-danger" disabled={busy || offline} title={title} onClick={() => void remove()}>Remove</button>
          <button className="btn btn-small btn-ghost" onClick={() => setConfirm(false)}>Keep</button>
        </div>
      )}
    </Card>
  );
}

/** The less used actions on a worn outfit, behind a ⋯ button, in a sheet. Escape closes it and puts focus back on the button. */
function OutfitMenu({ offline, onAgain, onLaundry, onKeep, onRemove }: { offline: boolean; onAgain(): void; onLaundry?(): void; onKeep(): void; onRemove(): void }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const title = offline ? OFFLINE_TITLE : undefined;
  const choose = (act: () => void) => () => {
    setOpen(false);
    act();
  };

  return (
    <div className="worn-menu">
      <button ref={button} type="button" className="btn btn-icon btn-ghost worn-menu-button" aria-label="More for this outfit"
        aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(!open)}>
        <MoreIcon />
      </button>
      {open && (
        <Sheet title="This outfit" anchor={button} onClose={() => setOpen(false)} className="worn-menu-sheet" testId="worn-menu">
          <div className="worn-menu-list">
            <Button block disabled={offline} title={title} onClick={choose(onAgain)}>Wear this again</Button>
            <Button block disabled={offline} title={title} onClick={choose(onKeep)}>Keep this outfit</Button>
            {onLaundry && <Button block disabled={offline} title={title} onClick={choose(onLaundry)}>Put these in the laundry</Button>}
            <Button block variant="danger-quiet" disabled={offline} title={title} onClick={choose(onRemove)}>Remove</Button>
          </div>
        </Sheet>
      )}
    </div>
  );
}

/** "Record an outfit", in a sheet: the day, then the pieces in four groups (most recently worn first) with a search. */
function RecordByHand({ items, anchor, onCancel, onDone }: {
  items: ItemSummary[]; anchor: RefObject<HTMLElement | null>; onCancel(): void;
  /** `back`: the pieces away that wearing them today brought back, by name and category */
  onDone(o: WornOutfit, back: { name: string; category: string | null }[]): void;
}) {
  const { offline } = useApp();
  const recorded = useEdit('outfit');
  const today = localDay();
  const [day, setDay] = useState(today);
  const [chosen, setChosen] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const words = (i: ItemSummary) => [nameOf(i, false), label('category', i.category), label('color', i.color)].join(' ');
  const groups = recordGroups(items, query, words);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const back = backByWearing(items.filter((i) => chosen.includes(i.id)), day, today).map((i) => ({ name: nameOf(i, false), category: i.category }));
      onDone(await recorded(() => api.recordOutfit(chosen, day)), back);
    } catch (err) {
      setError((err as ApiError).message);
      setBusy(false);
    }
  }

  const tile = (i: ItemSummary) => {
    const on = chosen.includes(i.id);
    return (
      <button type="button" className={`worn-record-item${on ? ' is-on' : ''}`} aria-pressed={on}
        onClick={() => setChosen((c) => (on ? c.filter((x) => x !== i.id) : [...c, i.id]))}>
        <Pic item={i} alt="" />
        <span>{nameOf(i, false)}</span>
      </button>
    );
  };

  return (
    <Sheet title="Record an outfit" anchor={anchor} closeLabel="Cancel" onClose={onCancel} className="worn-record-sheet" testId="record-sheet">
      <form className="worn-record" onSubmit={submit} aria-label="Record an outfit">
        <p className="hint">For a day you got dressed without Nines. The wears are recorded too.</p>
        <div className="worn-record-find">
          <label className="field worn-record-day">
            <span>Day</span>
            <input type="date" value={day} max={today} required onChange={(e) => setDay(e.target.value)} />
          </label>
          <label className="field worn-record-search">
            <span>Find a piece</span>
            <input type="search" value={query} placeholder="Name or colour" autoComplete="off" onChange={(e) => setQuery(e.target.value)} />
          </label>
        </div>
        <div role="group" aria-label="What you wore">
          {groups.length === 0 && <p className="muted">Nothing in your closet matches “{query.trim()}”.</p>}
          {groups.map((g) => (
            <section key={g.group} className="worn-record-group" aria-label={g.label}>
              <h3 className="chip-group-title">{g.label}</h3>
              <ShowMore items={g.pieces} first={query.trim() ? g.pieces.length : 8} keyOf={(i) => i.id} render={tile} className="worn-record-items" />
            </section>
          ))}
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="worn-record-bar">
          <Button variant="primary" block type="submit" disabled={busy || offline || chosen.length < 2} title={offline ? OFFLINE_TITLE : undefined}>
            {chosen.length < 2 ? 'Choose at least two pieces' : `Record ${chosen.length} pieces`}
          </Button>
        </div>
      </form>
    </Sheet>
  );
}

// ------------------------------------------------------------------ the outfits you keep

/** Worn's other half: the outfits kept without wearing them, newest first, each to wear in a tap. */
function KeptList() {
  const { profile, offline } = useApp();
  const read = useQuery(keptQuery());
  const list = read.data ?? null;
  const byId = useAllItems();
  const plans = useQuery(plansQuery(profile)).data;
  const trips = useQuery(tripsQuery(profile)).data;
  // as What you wore: offline with nothing kept on this device, one sentence; any other failed read, the shared one
  const error = read.error && !list
    ? ((read.error as ApiError).status === 0 ? "You're offline. The outfits you keep show here once Nines on your computer can be reached." : 'failed')
    : null;
  return (
    <div className="worn">
      <PageHeader title="Worn" back={{ to: '/today', label: 'Today' }}
        count={list && <>{list.length} kept</>} />
      <WornSwitch kept />
      {error === 'failed' ? <Failed query={read} what="the outfits you keep" />
        : error ? <p className="notice" role="alert">{error}</p> : list && <Failed query={read} what="the outfits you keep" />}
      {list === null && !error && <p className="muted"><span className="spinner" aria-hidden="true" /> Loading…</p>}
      {list && list.length === 0 && (
        <EmptyState icon={<HangerIcon />} title="No outfits kept yet" body={KEPT_EMPTY} testId="kept-empty" />
      )}
      {list && list.length > 0 && (
        <ol className="worn-list" aria-label="Outfits you keep">
          {list.map((o) => <li key={o.id}><KeptCard outfit={o} byId={byId} offline={offline} plans={plans} trips={trips} /></li>)}
        </ol>
      )}
    </div>
  );
}

/** One kept outfit: its name (given in place), when it was kept, its pieces, and Wear this; behind ⋯, Wear this on
 * another day and Remove. Removed, it leaves a line with Undo in its place. */
function KeptCard({ outfit, byId, offline, plans, trips }: {
  outfit: KeptOutfit; byId: Map<string, ItemSummary>; offline: boolean;
  plans: Parameters<typeof DaySheet>[0]['plans']; trips: Parameters<typeof DaySheet>[0]['trips'];
}) {
  const { toast } = useApp();
  const qc = useQueryClient();
  const status = useSaveStatus();
  const [name, setName] = useState(outfit.name ?? '');
  const [removed, setRemoved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [menu, setMenu] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const title = offline ? OFFLINE_TITLE : undefined;
  const gone = goneLine(outfit);

  function saveName() {
    const next = name.trim();
    if (next === (outfit.name ?? '')) return;
    void status.run(async () => {
      const o = await api.nameKept(outfit.id, next || null);
      qc.setQueryData<KeptOutfit[]>(queryKeys.kept(), (l) => l?.map((x) => (x.id === o.id ? o : x)));
    });
  }

  async function change(act: () => Promise<unknown>, gone: boolean) {
    setBusy(true);
    try {
      await act();
      setRemoved(gone);
      if (!gone) void touch(qc, 'kept');
    } catch (e) {
      toast((e as ApiError).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  if (removed) {
    return (
      <p className="worn-confirm kept-removed" role="status" data-testid="kept-removed">
        <span>You removed {outfit.name ? `“${outfit.name}”` : 'an outfit you kept'}.</span>
        <button className="btn btn-small" disabled={busy || offline} title={title}
          onClick={() => void change(() => api.restoreKept(outfit.id), false)}>Undo</button>
      </p>
    );
  }
  return (
    <Card as="article" className="worn-card kept-card" aria-label={outfit.name || 'An outfit you keep'} data-testid="kept-outfit">
      <div className="worn-card-head">
        <div className="worn-card-when kept-name">
          <label className="visually-hidden" htmlFor={`kept-name-${outfit.id}`}>Name of this outfit</label>
          <input id={`kept-name-${outfit.id}`} className="kept-name-input" value={name} maxLength={KEPT_NAME_MAX} placeholder="Give it a name"
            disabled={offline} onChange={(e) => setName(e.target.value)} onBlur={saveName}
            onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
          <p className="muted worn-day">{keptWhen(outfit)}</p>
        </div>
        <div className="worn-menu">
          <button ref={menuButton} type="button" className="btn btn-icon btn-ghost worn-menu-button" aria-label="More for this outfit"
            aria-haspopup="dialog" aria-expanded={menu} onClick={() => setMenu(!menu)}>
            <MoreIcon />
          </button>
          {menu && (
            <Sheet title="This outfit" anchor={menuButton} onClose={() => setMenu(false)} className="worn-menu-sheet" testId="kept-menu">
              <div className="worn-menu-list">
                <Button block disabled={offline} title={title} onClick={() => { setMenu(false); setChoosing(true); }}>Wear this on another day</Button>
                <Button block variant="danger-quiet" disabled={offline || busy} title={title}
                  onClick={() => { setMenu(false); void change(() => api.removeKept(outfit.id), true); }}>Remove</Button>
              </div>
            </Sheet>
          )}
        </div>
      </div>
      <OutfitPics outfit={outfit} byId={byId} from="/today/worn" />
      {gone && <p className="hint kept-gone">{gone}</p>}
      <div className="kept-actions">
        <Button variant="primary" small disabled={offline} title={title}
          onClick={() => navigate(`/today?again=${encodeURIComponent(outfit.id)}`)}>Wear this</Button>
        {!offline && <SaveStatus state={status.state} onRetry={status.retry} className="kept-status" />}
      </div>
      {choosing && (
        <DaySheet today={localDay()} plans={plans} trips={trips} anchor={menuButton} title="Wear it on another day"
          onClose={() => setChoosing(false)}
          onChoose={(d) => { setChoosing(false); navigate(`/today/day/${d}?again=${encodeURIComponent(outfit.id)}`); }} />
      )}
    </Card>
  );
}
