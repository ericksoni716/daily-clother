import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { ChevronIcon, ChevronLeftIcon, HangerIcon, MoreIcon, PlusIcon } from '../components/Icons';
import { Button, Card, EmptyState, ItemThumb, PageHeader, trapTab } from '../components/ui';
import { label } from '../labels';
import { Link, navigate } from '../router';
import { useCloset } from '../store';
import { occasionLabel } from '../today';
import type { ItemSummary } from '../types';
import { localDay } from '../wears';
import {
  contextWords, RATINGS, ratingLabel, ratingSummary, reasonLabel, reasonsFor, loadSavedWorn, pieceName, saveWorn, wornDay, wornIds, type Rating, type Reason,
  type WornOutfit, type WornPage,
} from '../worn';
import './Worn.css';

const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';
export const RATE_OFFLINE = "You're offline, so rating has to wait until Closet on your computer can be reached.";

/** The three answers, then the reasons; each tap is saved straight away. Used by the Worn list and by Today's question. */
export function RateOutfit({ outfit, offline, onRated, compact }: {
  outfit: WornOutfit; offline: boolean; onRated(o: WornOutfit): void; compact?: boolean;
}) {
  const { toast } = useCloset();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(outfit.rating_note ?? '');
  const locked = offline || busy;
  const title = offline ? OFFLINE_TITLE : undefined;

  async function save(rating: Rating | null, reasons: Reason[], noteText: string | null) {
    setBusy(true);
    try {
      onRated(await api.rateOutfit(outfit.id, rating, reasons, reasons.includes('other') ? noteText : null));
    } catch (e) {
      toast((e as ApiError).message, 'error');
    } finally {
      setBusy(false);
    }
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
            disabled={locked} title={title}
            onClick={() => void save(outfit.rating === r ? null : r, outfit.rating === r ? [] : reasons, note.trim() || null)}>
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
                disabled={locked} title={title} onClick={() => toggle(r)}>
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
              <button className="btn btn-small" disabled={locked || note.trim() === (outfit.rating_note ?? '')} title={title}>Save note</button>
            </form>
          )}
        </>
      )}
      {offline && <p className="hint rate-offline">{RATE_OFFLINE}</p>}
    </div>
  );
}

/** The pieces of a worn outfit, each opening its item unless `linked` is false (a small preview, as on Today's question). */
export function OutfitPics({ outfit, byId, linked = true }: { outfit: WornOutfit; byId: Map<string, ItemSummary>; linked?: boolean }) {
  const ids = wornIds(outfit.pieces);
  return (
    <ul className="worn-pics" aria-label="Pieces">
      {ids.map((id) => {
        const deleted = (outfit.gone ?? []).includes(id);
        const item = byId.get(id);
        const name = nameOf(item, deleted);
        return (
          <li key={id}>
            {deleted || !linked ? (
              <ItemThumb className={`worn-pic${deleted ? ' is-gone' : item?.status === 'archived' ? ' is-archived' : ''}`} title={name}
                picture={<Pic item={deleted ? undefined : item} alt={name} />} />
            ) : (
              <ItemThumb to={item?.status === 'archived' ? `/archived/item/${encodeURIComponent(id)}` : `/today/item/${encodeURIComponent(id)}`}
                className={`worn-pic${item?.status === 'archived' ? ' is-archived' : ''}`} title={name} picture={<Pic item={item} alt={name} />} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Every item in the closet by id, archived ones too: a worn outfit may hold a piece archived since. */
export function useAllItems(): Map<string, ItemSummary> {
  const { items, loadItems } = useCloset();
  useEffect(() => {
    if (items.archived === null) void loadItems('archived');
  }, [items.archived, loadItems]);
  return useMemo(() => new Map([...(items.archived ?? []), ...(items.active ?? [])].map((i) => [i.id, i])), [items.active, items.archived]);
}

/**
 * Fetch the first page of worn outfits again and keep it for this closet, so the copy saved for offline matches
 * what changed. When Closet on the computer cannot be reached, this closet's saved copy (or null).
 */
export async function refreshSaved(profile: string): Promise<WornPage | null> {
  try {
    const page = await api.wornOutfits();
    saveWorn(profile, page);
    return page;
  } catch (e) {
    return (e as ApiError).status === 0 ? loadSavedWorn(profile)?.page ?? null : null;
  }
}

export function WornScreen() {
  const { profile, items, loadItems, offline, toast } = useCloset();
  const [list, setList] = useState<WornOutfit[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    if (items.active === null) void loadItems('active');
  }, [items.active, loadItems]);

  const load = useCallback(async () => {
    try {
      const page = await api.wornOutfits();
      saveWorn(profile, page);
      setList(page.outfits);
      setNext(page.next);
      setError(null);
    } catch (e) {
      const err = e as ApiError;
      const saved = err.status === 0 ? loadSavedWorn(profile) : null;
      if (saved) {
        setList(saved.page.outfits);
        setNext(saved.page.next);
        setError(null);
        return;
      }
      setError(err.status === 0 ? "You're offline, and the worn outfits were not saved on this device yet." : err.message);
    }
  }, [profile]);

  useEffect(() => {
    setList(null);
    void load();
  }, [load, profile]);

  async function more() {
    if (!next) return;
    setLoadingMore(true);
    try {
      const page = await api.wornOutfits(next);
      setList((l) => [...(l ?? []), ...page.outfits.filter((o) => !(l ?? []).some((x) => x.id === o.id))]);
      setNext(page.next);
    } catch (e) {
      toast((e as ApiError).message, 'error');
    } finally {
      setLoadingMore(false);
    }
  }

  const byId = useAllItems();
  const replace = (o: WornOutfit) => {
    setList((l) => (l ?? []).map((x) => (x.id === o.id ? o : x)));
    void refreshSaved(profile);
  };

  return (
    <div className="worn">
      <div className="detail-top">
        <Link to="/today" className="btn btn-ghost back-link"><ChevronLeftIcon /> Today</Link>
      </div>
      <PageHeader title="Worn" count={list && <>{list.length}{next ? '+' : ''} {list.length === 1 ? 'outfit' : 'outfits'}</>}
        secondary={!adding && (
          <Button disabled={offline} title={offline ? OFFLINE_TITLE : undefined} onClick={() => setAdding(true)}>
            <PlusIcon /> Record an outfit
          </Button>
        )} />
      <p className="hint worn-intro">Outfits you wore, newest first. Say how each one went and the outfits Today offers learn from it.</p>

      {adding && (
        <RecordByHand items={items.active ?? []} onCancel={() => setAdding(false)}
          onDone={(o) => {
            setAdding(false);
            setList((l) => [o, ...(l ?? [])].sort((a, b) => (a.worn_on === b.worn_on ? 0 : a.worn_on < b.worn_on ? 1 : -1)));
            void loadItems('active');
            void refreshSaved(profile);
            toast('Outfit recorded');
          }} />
      )}

      {error && !list && <p className={offline ? 'notice' : 'form-error'} role="alert">{error}</p>}
      {list === null && !error && <p className="muted"><span className="spinner" aria-hidden="true" /> Loading…</p>}
      {list && list.length === 0 && (
        <EmptyState icon={<HangerIcon />} title="No outfits worn yet" body={'Tap "I\'m wearing this" on Today, or record one here.'} />
      )}
      {list && list.length > 0 && (
        <ol className="worn-list" aria-label="Worn outfits">
          {list.map((o) => (
            <li key={o.id}>
              <WornCard outfit={o} byId={byId} offline={offline} onRated={replace}
                onRemoved={() => {
                  setList((l) => (l ?? []).filter((x) => x.id !== o.id));
                  void loadItems('active');
                  void refreshSaved(profile);
                }} />
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
  const { toast } = useCloset();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rating, setRating] = useState(false);
  const title = offline ? OFFLINE_TITLE : undefined;
  const names = wornIds(outfit.pieces).map((id) => nameOf(byId.get(id), (outfit.gone ?? []).includes(id)));
  const day = contextWords(outfit.context, occasionLabel);

  async function remove() {
    setBusy(true);
    try {
      await api.removeOutfit(outfit.id);
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
          onRemove={() => setConfirm(true)} />
      </div>
      <OutfitPics outfit={outfit} byId={byId} />
      <p className="worn-names">{names.join(', ')}</p>
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

/** The less used actions on a worn outfit, behind a ⋯ button. Escape closes the menu and puts focus back on the button. */
function OutfitMenu({ offline, onAgain, onRemove }: { offline: boolean; onAgain(): void; onRemove(): void }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const title = offline ? OFFLINE_TITLE : undefined;

  useEffect(() => {
    if (!open) return;
    // the first thing that can be chosen; the menu itself when nothing can (offline), so Escape still closes it
    (menu.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? menu.current)?.focus();
    const outside = (e: PointerEvent) => {
      if (!menu.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };
  const choose = (act: () => void) => () => {
    close();
    act();
  };

  function onKey(e: ReactKeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      return;
    }
    // Tab stays in the menu, as in a dialog
    trapTab(e, menu.current);
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    const all = [...(menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [])];
    if (!all.length) return;
    if (e.key === 'Home') return all[0].focus();
    if (e.key === 'End') return all[all.length - 1].focus();
    const at = all.indexOf(document.activeElement as HTMLButtonElement);
    all[(at + (e.key === 'ArrowDown' ? 1 : all.length - 1)) % all.length]?.focus();
  }

  return (
    <div className="worn-menu">
      <button ref={button} type="button" className="btn btn-icon btn-ghost worn-menu-button" aria-label="More for this outfit"
        aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <MoreIcon />
      </button>
      {open && (
        <div ref={menu} className="worn-menu-list" role="menu" aria-label="This outfit" tabIndex={-1} onKeyDown={onKey}>
          <button type="button" role="menuitem" className="worn-menu-item" disabled={offline} title={title} onClick={choose(onAgain)}>
            Wear this again
          </button>
          <button type="button" role="menuitem" className="worn-menu-item is-danger" disabled={offline} title={title} onClick={choose(onRemove)}>
            Remove
          </button>
        </div>
      )}
    </div>
  );
}

function RecordByHand({ items, onCancel, onDone }: { items: ItemSummary[]; onCancel(): void; onDone(o: WornOutfit): void }) {
  const { offline } = useCloset();
  const today = localDay();
  const [day, setDay] = useState(today);
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const usable = items.filter((i) => i.status !== 'archived' && i.category);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await api.recordOutfit(chosen, day));
    } catch (err) {
      setError((err as ApiError).message);
      setBusy(false);
    }
  }

  return (
    <Card as="form" className="worn-record" onSubmit={submit} aria-label="Record an outfit">
      <h2>Record an outfit</h2>
      <p className="hint">For a day you got dressed without Closet. Choose what you wore; the wears are recorded too.</p>
      <label className="field worn-record-day">
        <span>Day</span>
        <input type="date" value={day} max={today} required onChange={(e) => setDay(e.target.value)} />
      </label>
      <div className="worn-record-items" role="group" aria-label="What you wore">
        {usable.map((i) => {
          const on = chosen.includes(i.id);
          return (
            <button key={i.id} type="button" className={`worn-record-item${on ? ' is-on' : ''}`} aria-pressed={on}
              onClick={() => setChosen((c) => (on ? c.filter((x) => x !== i.id) : [...c, i.id]))}>
              <Pic item={i} />
              <span>{nameOf(i, false)}</span>
            </button>
          );
        })}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="row">
        <button className="btn btn-primary" disabled={busy || offline || chosen.length < 2} title={offline ? OFFLINE_TITLE : undefined}>
          Record {chosen.length > 0 ? `${chosen.length} pieces` : 'outfit'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
      </div>
    </Card>
  );
}

function Pic({ item, alt = nameOf(item, false) }: { item: ItemSummary | undefined; alt?: string }): ReactNode {
  if (!item) return <span className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></span>;
  if (item.cutout_state === 'ready' && item.thumb_url) return <img className="pic-cutout" src={item.thumb_url} alt={alt} />;
  if (item.illustration_url) return <img className="pic-illustration" src={item.illustration_url} alt={alt} />;
  if (item.thumb_url) return <img className="pic-photo" src={item.thumb_url} alt={alt} />;
  return <span className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></span>;
}

function nameOf(item: ItemSummary | undefined, deleted: boolean): string {
  return pieceName(item, deleted, (c) => label('category', c));
}
