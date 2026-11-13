import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../api';
import { BackIcon, CheckIcon, HangerIcon, PlusIcon, SearchIcon, WarnIcon } from '../components/Icons';
import { formatDateTime, label, SWATCH } from '../labels';
import { Link, navigate } from '../router';
import { HIDE_REASONS, helpLevel, lookForWords, readShopping, saveShopping, type Gap, type HideReason, type LookFor, type SavedShopping, type Wish } from '../shopping';
import { shoppingApi } from '../shopping-api';
import { useCloset } from '../store';
import type { ItemSummary } from '../types';
import { ItemDetail } from './ItemDetail';
import './Missing.css';

const OFFLINE = 'Needs Closet on your computer to be reachable';

export function MissingScreen({ itemId }: { itemId: string | null }) {
  const { profile, offline, items, toast } = useCloset();
  const [data, setData] = useState<SavedShopping | null>(null);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [adding, setAdding] = useState(false);
  const wasOffline = useRef(offline);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError('');
    Promise.all([shoppingApi.gaps(ctrl.signal), shoppingApi.hidden(ctrl.signal), shoppingApi.wishes(ctrl.signal)]).then(
      ([answer, hidden, wishes]) => {
        if (ctrl.signal.aborted) return;
        const next = { answer, hidden, wishes, saved_at: new Date().toISOString() };
        saveShopping(profile, next);
        setData(next);
        setSaved(false);
        setLoading(false);
      },
      (e: ApiError) => {
        if (ctrl.signal.aborted) return;
        if (e.status === 0) {
          setData(readShopping(profile));
          setSaved(true);
        }
        setError(e.status === 0 ? "Closet on your computer can't be reached. Changes have to wait until it's back." : e.message);
        setLoading(false);
      },
    );
    return () => ctrl.abort();
  }, [profile, attempt]);

  useEffect(() => {
    if (wasOffline.current && !offline) setAttempt((n) => n + 1);
    wasOffline.current = offline;
  }, [offline]);

  const locked = offline || saved;
  const disabled = locked || busy || loading;
  const title = locked ? OFFLINE : undefined;
  const byId = new Map((items.active ?? []).map((item) => [item.id, item]));

  function remember(next: SavedShopping) {
    setData(next);
    saveShopping(profile, next);
  }

  async function change<T>(work: () => Promise<T>, update: (result: T, previous: SavedShopping) => SavedShopping, message: string): Promise<boolean> {
    if (!data || disabled) return false;
    setBusy(true);
    setError('');
    try {
      const result = await work();
      if (!mounted.current) return false;
      remember(update(result, data));
      toast(message);
      return true;
    } catch (e) {
      if (!mounted.current) return false;
      setError((e as Error).message);
      if ((e as ApiError).status === 0) setSaved(true);
      return false;
    } finally { if (mounted.current) setBusy(false); }
  }

  const addWish = (gap: Gap) => change(() => shoppingApi.add({ gap_id: gap.id }), (wish, d) => ({
    ...d, wishes: [wish, ...d.wishes.filter((w) => w.id !== wish.id)],
    hidden: d.hidden.filter((g) => g.id !== gap.id),
    answer: { ...d.answer, gaps: d.answer.gaps.map((g) => g.id === gap.id ? { ...g, wished: true, hidden: false, hidden_reason: null } : g) },
  }), 'Added to your wishlist.');

  const hide = (gap: Gap, reason: HideReason | null) => change(() => shoppingApi.hide(gap.id, reason), (_, d) => ({
    ...d, hidden: [...d.hidden.filter((g) => g.id !== gap.id), { ...gap, hidden: true, hidden_reason: reason }],
    answer: { ...d.answer, gaps: d.answer.gaps.map((g) => g.id === gap.id ? { ...g, hidden: true, hidden_reason: reason } : g) },
  }), 'Hidden. You can bring it back below.');

  const unhide = (gap: Gap) => change(() => shoppingApi.unhide(gap.id), (_, d) => ({
    ...d, hidden: d.hidden.filter((g) => g.id !== gap.id),
    answer: { ...d.answer, gaps: d.answer.gaps.map((g) => g.id === gap.id ? { ...g, hidden: false, hidden_reason: null } : g) },
  }), 'No longer hidden. It will show whenever the analysis suggests it.');

  const removeWish = async (wish: Wish, bought: boolean) => {
    const ok = await change(() => bought ? shoppingApi.bought(wish.id) : shoppingApi.remove(wish.id), (_, d) => ({
      ...d, wishes: d.wishes.filter((w) => w.id !== wish.id),
      answer: { ...d.answer, gaps: d.answer.gaps.map((g) => g.id === wish.gap_id ? { ...g, wished: false } : g) },
    }), bought ? 'Off your wishlist. Add a photo of your new piece.' : 'Removed from your wishlist.');
    if (ok && bought) navigate('/add');
  };

  if (itemId) return (
    <div className="missing-item">
      <Link to="/missing" className="btn btn-ghost"><BackIcon /> What's missing</Link>
      <ItemDetail key={itemId} id={itemId} status="active" inPanel />
    </div>
  );

  const visible = data?.answer.gaps.filter((g) => !g.hidden) ?? [];
  const observations = data ? [
    ...data.answer.notes,
    ...data.answer.gaps.filter((g) => g.found_by.includes('worn_most'))
      .flatMap((g) => g.why.filter((why) => why.startsWith('You wore ')).map((text) => ({ kind: 'worn_most', text, items: g.evidence.items }))),
  ] : [];
  return (
    <div className="missing">
      <header className="missing-header">
        <div>
          <p className="missing-eyebrow">Make more of what you own</p>
          <h1 id="missing-title">What's missing</h1>
          <p className="missing-intro">A few thoughtful additions. More ways to wear your closet.</p>
        </div>
        <a className="btn missing-wishlist-jump" href="#wishlist">Your wishlist <span className="missing-count">{data?.wishes.length ?? 0}</span></a>
      </header>

      {locked && data && <div className="notice notice-warn" role="status">
        <WarnIcon /><div><strong>Saved earlier · {formatDateTime(data.saved_at)}</strong><br />
          Changes need Closet on your computer to be reachable. This updates when it is back.</div>
      </div>}
      {error && (!locked || !data) && <div className="notice notice-warn" role="alert">
        <WarnIcon /><div><p>{error}</p>{!data && saved && <p>No answer has been saved on this device for this closet yet.</p>}
          <button className="btn" onClick={() => setAttempt((n) => n + 1)} disabled={loading}>Try again</button></div>
      </div>}

      {loading && !data && <div className="missing-loading" role="status">
        <span className="spinner" aria-hidden="true" /><h2>Looking at your closet…</h2>
        <p className="muted">Checking what would work with the pieces you own.</p>
      </div>}

      {data && <div className="missing-layout" aria-busy={busy || loading}>
        <div className="missing-suggestions">
          <div className="missing-section-head">
            <div><h2>Worth looking for</h2><p className="hint">Best first · based on your {data.answer.checked.items} pieces</p></div>
            <button className="btn btn-ghost" disabled={disabled} title={title} onClick={() => setAttempt((n) => n + 1)}>
              {loading ? 'Checking…' : 'Check again'}
            </button>
          </div>
          {!data.answer.enough ? <div className="missing-empty">
            <HangerIcon /><h3>A little more to go on</h3><p>{data.answer.message}</p>
            {locked ? <button className="btn btn-primary" disabled title={OFFLINE}>Add clothes</button>
              : <Link to="/add" className="btn btn-primary">Add clothes</Link>}
          </div> : visible.length === 0 ? <div className="missing-empty">
            <CheckIcon /><h3>Nothing else to look for right now</h3>
            <p>Your wishlist and anything you have hidden are still here.</p>
          </div> : <div className="missing-cards">
            {visible.map((gap, index) => <GapCard key={gap.id} gap={gap} first={index === 0} byId={byId}
              disabled={disabled} title={title} onWish={() => addWish(gap)} onHide={(reason) => hide(gap, reason)} />)}
          </div>}

          <section className="missing-observations" aria-labelledby="observations-title">
            <p className="missing-eyebrow">Already in your closet</p>
            <h2 id="observations-title">A few things to notice</h2>
            <p className="hint">Not a shopping list. Sometimes the answer is wearing what you have.</p>
            {observations.length ? observations.map((note, i) => <div className="missing-observation" key={`${note.kind}-${i}`}>
              <p>{note.text}</p><Evidence ids={note.items} byId={byId} />
            </div>) : <p className="muted small">Keep recording what you wear. Patterns will show up here.</p>}
          </section>

          <details className="missing-hidden">
            <summary>Hidden suggestions <span className="missing-count">{data.hidden.length}</span></summary>
            <p className="hint">These stay hidden when your closet changes. Bringing one back lets the analysis suggest it again.</p>
            {data.hidden.length === 0 && <p className="small muted">Nothing hidden.</p>}
            {data.hidden.map((gap) => <article key={gap.id} className="missing-hidden-card">
              <h3>{gap.name}</h3>
              <p className="small muted">{gap.hidden_reason ? HIDE_REASONS[gap.hidden_reason] : 'No reason given'}</p>
              <LookForDetails look={gap.look_for} />
              <button className="btn" disabled={disabled} title={title} onClick={() => void unhide(gap)}>Bring back</button>
            </article>)}
          </details>
        </div>

        <aside id="wishlist" className="missing-wishlist" aria-labelledby="wishlist-title">
          <div className="missing-wishlist-head">
            <div className="missing-section-head"><h2 id="wishlist-title">Your wishlist</h2><span className="missing-count">{data.wishes.length}</span></div>
            <p>Good things to keep an eye out for.<br />No need to buy them all at once.</p>
          </div>
          <div className="missing-wishlist-body">
            {data.wishes.length === 0 && <div className="missing-wishlist-empty">
              <SearchIcon /><h3>Room for the right piece</h3>
              <p>Choose “I'll look for this” on an idea you like, or add something of your own.</p>
            </div>}
            {data.wishes.map((wish) => <WishCard key={wish.id} wish={wish} disabled={disabled} title={title}
              onNote={(note) => change(() => shoppingApi.note(wish.id, note), (updated, d) => ({
                ...d, wishes: d.wishes.map((w) => w.id === wish.id ? updated : w),
              }), 'Note saved.')}
              onRemove={() => void removeWish(wish, false)} onBought={() => void removeWish(wish, true)} />)}
            {adding ? <ManualWish disabled={disabled} title={title} onCancel={() => setAdding(false)}
              onAdd={async (body) => {
                if (await change(() => shoppingApi.add(body), (wish, d) => ({ ...d, wishes: [wish, ...d.wishes] }), 'Added to your wishlist.')) setAdding(false);
              }} />
              : <button className="btn btn-block" disabled={disabled} title={title} onClick={() => setAdding(true)}><PlusIcon /> Add your own wish</button>}
            <p className="missing-wishlist-foot">Just your list for now. Shop searches and prices come later.</p>
          </div>
        </aside>
      </div>}
    </div>
  );
}

function Help({ score }: { score: number }) {
  const help = helpLevel(score);
  return <div className="missing-help" aria-label={`How much it would help: ${help.words}`}>
    <span className="missing-help-bars" aria-hidden="true">{[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= help.bars ? 'is-filled' : ''} />)}</span>
    <span>{help.words}</span>
  </div>;
}

function LookForDetails({ look, details }: { look: LookFor | null; details?: string }) {
  return <div className="missing-look">
    <p className="missing-label">What to look for</p>
    <p>{lookForWords(look).join(' · ')}{details}</p>
    {!!look?.colors.length && <span className="missing-swatches" aria-hidden="true">
      {look.colors.map((c) => <span key={c} style={{ background: SWATCH[c] ?? 'var(--surface-2)' }} />)}
    </span>}
  </div>;
}

function Evidence({ ids, byId }: { ids: string[]; byId: Map<string, ItemSummary> }) {
  const pieces = ids.map((id) => byId.get(id)).filter((i): i is ItemSummary => !!i);
  if (!pieces.length) return null;
  return <ul className="missing-pieces" aria-label="Your own pieces">
    {pieces.map((item) => {
      const name = item.name || label('category', item.category) || 'Unnamed item';
      const src = item.thumb_url || item.illustration_url;
      return <li key={item.id}><Link to={`/missing/item/${encodeURIComponent(item.id)}`} title={name} aria-label={`Open ${name}`}>
        <span className="missing-piece-picture">{src ? <img src={src} alt="" className={item.thumb_url && item.cutout_state !== 'ready' ? 'pic-photo' : 'pic-cutout'} /> : <HangerIcon />}</span>
        <span className="missing-piece-name">{name}</span>
      </Link></li>;
    })}
  </ul>;
}

function GapCard({ gap, first, byId, disabled, title, onWish, onHide }: {
  gap: Gap; first: boolean; byId: Map<string, ItemSummary>; disabled: boolean; title?: string;
  onWish(): Promise<boolean>; onHide(reason: HideReason | null): Promise<boolean>;
}) {
  const [hiding, setHiding] = useState(false);
  const [reason, setReason] = useState<HideReason | ''>('');
  return <article className={`missing-card${first ? ' missing-card-first' : ''}`} aria-label={gap.name} data-testid="gap">
    <div className="missing-card-top">
      <span className="missing-label">{gap.wished ? 'On your wishlist' : first ? 'Start here' : 'Another possibility'}</span>
      <Help score={gap.score} />
    </div>
    <h3>{gap.name}</h3>
    <ul className="missing-reasons" aria-label="Why this would help">{gap.why.map((why) => <li key={why}>{why}</li>)}</ul>
    <LookForDetails look={gap.look_for} />
    <div className="missing-card-actions">
      {gap.wished ? <a href="#wishlist" className="missing-wished"><CheckIcon /> On your wishlist</a>
        : <><button className="btn btn-primary" disabled={disabled} title={title} onClick={() => void onWish()}><PlusIcon /> I'll look for this</button>
          <button className="btn btn-ghost" disabled={disabled} title={title} aria-expanded={hiding} onClick={() => setHiding(!hiding)}>Not for me</button></>}
    </div>
    {hiding && !gap.wished && <form className="missing-hide-form" onSubmit={async (e) => { e.preventDefault(); if (await onHide(reason || null)) setHiding(false); }}>
      <label className="field"><span>Why not? (optional)</span><select value={reason} disabled={disabled} onChange={(e) => setReason(e.target.value as HideReason | '')}>
        <option value="">I'd rather not say</option>
        {Object.entries(HIDE_REASONS).map(([key, text]) => <option value={key} key={key}>{text}</option>)}
      </select></label>
      <div className="row"><button className="btn" disabled={disabled} title={title}>Hide suggestion</button>
        <button className="btn btn-ghost" type="button" onClick={() => setHiding(false)}>Cancel</button></div>
    </form>}
    {!!gap.evidence.items.length && <div className="missing-evidence">
      <p className="missing-label">Based on your pieces</p><Evidence ids={gap.evidence.items} byId={byId} />
    </div>}
  </article>;
}

function WishCard({ wish, disabled, title, onNote, onBought, onRemove }: {
  wish: Wish; disabled: boolean; title?: string; onNote(note: string): Promise<boolean>; onBought(): void; onRemove(): void;
}) {
  const [draft, setDraft] = useState({ base: wish.note, text: wish.note });
  const dirty = draft.text !== draft.base;
  const note = dirty ? draft.text : wish.note;
  const conflict = dirty && draft.base !== wish.note;
  return <article className="missing-wish" aria-label={wish.name} data-testid="wish">
    <p className="missing-label">{wish.gap_id ? 'From your closet’s suggestions' : 'Your own idea'}</p>
    <h3>{wish.name}</h3>
    {(wish.look_for || wish.details) && <LookForDetails look={wish.look_for} details={wish.details} />}
    <form onSubmit={async (e) => {
      e.preventDefault();
      if (await onNote(note)) setDraft({ base: note, text: note });
    }}>
      {conflict && <div className="missing-note-conflict" role="status">
        <p>This note changed elsewhere. Your draft is kept below.</p>
        <p><strong>Saved note:</strong> {wish.note || '(empty)'}</p>
        <button type="button" className="btn btn-ghost" onClick={() => setDraft({ base: wish.note, text: wish.note })}>Use saved note</button>
      </div>}
      <label className="field"><span>Your note</span><textarea rows={2} maxLength={2000} value={note} disabled={disabled} title={title}
        placeholder="A fit, a fabric, somewhere to look…" onChange={(e) => setDraft({ base: dirty ? draft.base : wish.note, text: e.target.value })} /></label>
      {note !== wish.note && <button className="btn" disabled={disabled} title={title}>{conflict ? 'Save my note instead' : 'Save note'}</button>}
    </form>
    <div className="row missing-wish-actions">
      <button className="btn" disabled={disabled} title={title ?? 'Take this off the list and add a photo'} onClick={onBought}><CheckIcon /> I bought it</button>
      <button className="btn btn-ghost" disabled={disabled} title={title} onClick={onRemove}>Remove</button>
    </div>
  </article>;
}

function ManualWish({ disabled, title, onCancel, onAdd }: {
  disabled: boolean; title?: string; onCancel(): void; onAdd(body: { name: string; details: string; note: string }): Promise<void>;
}) {
  const [name, setName] = useState('');
  const [details, setDetails] = useState('');
  const [note, setNote] = useState('');
  const submit = (e: FormEvent) => { e.preventDefault(); if (name.trim()) void onAdd({ name: name.trim(), details: details.trim(), note: note.trim() }); };
  return <form className="missing-manual" onSubmit={submit} aria-label="Add your own wish">
    <h3>Something you have in mind</h3>
    <label className="field"><span>What are you looking for?</span><input autoFocus required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} disabled={disabled} /></label>
    <label className="field"><span>What to look for (optional)</span><textarea maxLength={4000} rows={2} value={details} onChange={(e) => setDetails(e.target.value)} disabled={disabled} placeholder="Colour, fabric, the kind of day…" /></label>
    <label className="field"><span>A note (optional)</span><textarea maxLength={2000} rows={2} value={note} onChange={(e) => setNote(e.target.value)} disabled={disabled} /></label>
    <div className="row"><button className="btn btn-primary" disabled={disabled || !name.trim()} title={title}>Add wish</button>
      <button className="btn btn-ghost" type="button" onClick={onCancel}>Cancel</button></div>
  </form>;
}
