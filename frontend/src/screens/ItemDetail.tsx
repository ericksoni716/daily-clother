import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { ChipGroup } from '../components/Chips';
import { BackIcon, HangerIcon, WarnIcon } from '../components/Icons';
import { formatPrice, label, parsePrice, ratingLabel, SWATCH } from '../labels';
import { Link, navigate } from '../router';
import { silhouetteGroups } from '../silhouette';
import { useCloset } from '../store';
import type { Item, ItemPatch } from '../types';
import { busyLabel } from './Closet';

type View = 'illustration' | 'cutout' | 'photo';

interface Props {
  id: string;
  status: 'active' | 'archived';
  inPanel?: boolean;
}

function applyPatch(item: Item, changes: ItemPatch): Item {
  const { silhouette, ...rest } = changes;
  const next: Item = { ...item, ...(rest as Partial<Item>) };
  if (silhouette) {
    const merged = { ...item.silhouette };
    for (const [k, v] of Object.entries(silhouette)) {
      if (v === null) delete merged[k];
      else merged[k] = v;
    }
    next.silhouette = merged;
  }
  return next;
}

export function ItemDetail({ id, status, inPanel }: Props) {
  const { vocab, upsert, drop, toast, offline, model, items } = useCloset();
  const [item, setItem] = useState<Item | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef(0);
  const backTo = status === 'archived' ? '/archived' : '/';

  const load = useCallback(async () => {
    try {
      const it = await api.item(id);
      setItem(it);
      setError(null);
    } catch (e) {
      setError((e as ApiError).message);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Follow the cutout while it is being made.
  const busy = item?.cutout_state === 'pending' || item?.cutout_state === 'processing';
  useEffect(() => {
    if (!busy || offline) return;
    const t = window.setInterval(async () => {
      if (inflight.current) return;
      try {
        const fresh = await api.item(id);
        if (!inflight.current) setItem(fresh);
      } catch {
        /* the next tick tries again */
      }
    }, 2000);
    return () => window.clearInterval(t);
  }, [busy, offline, id]);

  const save = useCallback(async (changes: ItemPatch, saidAs = 'Saved') => {
    if (!item) return;
    const before = item;
    setItem((cur) => (cur ? applyPatch(cur, changes) : cur));
    inflight.current++;
    try {
      const saved = await api.patch(id, changes);
      inflight.current--;
      if (!inflight.current) setItem(saved);
      upsert(saved);
      toast(saidAs);
    } catch (e) {
      inflight.current--;
      setItem(before);
      toast((e as ApiError).message, 'error');
      if (!inflight.current) void load();
    }
  }, [item, id, upsert, toast, load]);

  if (error && !item) {
    const summary = items.active?.find((x) => x.id === id) ?? items.archived?.find((x) => x.id === id);
    if (offline && summary) {
      // Not saved for offline use yet: show what the closet list knows.
      const asItem = { ...summary, photos: [], silhouette: {}, illustration_svg: null } as unknown as Item;
      return (
        <article className="detail" aria-label={summary.name || 'Item'}>
          <DetailTop inPanel={inPanel} backTo={backTo} />
          <Picture item={asItem} busyText={busyLabel(model)} fallbackThumb={summary.thumb_url} />
          <p className="notice">You're offline, so this item can't be changed right now. Its full details show once Closet can be reached again.</p>
          <h2 className="detail-name">{summary.name || label('category', summary.category) || 'Item'}</h2>
          <p className="muted">{[label('category', summary.category), label('color', summary.color), label('pattern', summary.pattern), label('location', summary.location)].filter(Boolean).join(' · ')}</p>
        </article>
      );
    }
    return (
      <div className="detail">
        <DetailTop inPanel={inPanel} backTo={backTo} />
        <div className="empty"><p className="form-error" role="alert">{error}</p></div>
      </div>
    );
  }
  if (!item || !vocab) {
    return (
      <div className="detail" aria-busy="true">
        <DetailTop inPanel={inPanel} backTo={backTo} />
        <div className="detail-picture tile-skeleton" />
      </div>
    );
  }

  const locked = offline;
  const groups = silhouetteGroups(item.category);

  return (
    <article className="detail" aria-label={item.name || 'Item'}>
      <DetailTop inPanel={inPanel} backTo={backTo} />
      <Picture item={item} busyText={busyLabel(model)} />

      {locked && <p className="notice">You're offline, so this item can't be changed right now.</p>}

      <NameField value={item.name} placeholder={label('category', item.category) || 'Name this item'} disabled={locked}
        onSave={(name) => save({ name })} />

      {item.cutout_state === 'failed' && (
        <div className="notice notice-warn">
          <WarnIcon />
          <div>
            <p><strong>The background couldn't be removed.</strong>{item.cutout_error ? ` ${item.cutout_error}` : ''}</p>
            <button className="btn btn-small" disabled={locked} onClick={async () => {
              try {
                setItem(await api.retryCutout(id));
                toast('Trying the cutout again');
              } catch (e) {
                toast((e as Error).message, 'error');
              }
            }}>Try the cutout again</button>
          </div>
        </div>
      )}

      <div className="attr-groups">
        <ChipGroup field="category" options={vocab.category} value={item.category} disabled={locked}
          onChange={(v) => save({ category: v })} />
        <ChipGroup field="color" options={vocab.color} value={item.color} disabled={locked} swatches
          onChange={(v) => save({ color: v, color_hex: v ? (SWATCH[v]?.startsWith('#') ? SWATCH[v] : null) : null })} />
        <ChipGroup field="pattern" options={vocab.pattern} value={item.pattern} disabled={locked} onChange={(v) => save({ pattern: v })} />
        <ChipGroup field="formality" options={vocab.formality} value={item.formality} disabled={locked} onChange={(v) => save({ formality: v })} />
        <ChipGroup field="season" options={vocab.season} value={item.season} disabled={locked} onChange={(v) => save({ season: v })} />
        <ChipGroup field="location" options={vocab.location} value={item.location} disabled={locked} onChange={(v) => save({ location: v })} />
        {groups.map((g) => (
          <ChipGroup key={g} field={g} options={vocab.silhouette[g] ?? []} value={item.silhouette?.[g]} disabled={locked}
            onChange={(v) => save({ silhouette: { [g]: v } })} />
        ))}
        <ChipGroup field="rating" options={vocab.rating} value={item.rating} disabled={locked} labelOf={ratingLabel}
          onChange={(v) => save(v ? { rating: v } : { rating: null, rating_reason: null })} />
        {item.rating && (
          <TextField label="Why? (optional)" value={item.rating_reason} disabled={locked} placeholder="e.g. great fit, itchy collar"
            onSave={(v) => save({ rating_reason: v })} />
        )}
      </div>

      <details className="more">
        <summary>More details</summary>
        <div className="more-body">
          <TextField label="Brand" value={item.brand} disabled={locked} onSave={(v) => save({ brand: v })} />
          <TextField label="Size" value={item.size} disabled={locked} onSave={(v) => save({ size: v })} />
          <TextField label="Material" value={item.material} disabled={locked} placeholder="e.g. cotton, wool blend" onSave={(v) => save({ material: v })} />
          <TextField label="Fit notes" value={item.fit_notes} disabled={locked} placeholder="e.g. runs small in the shoulders" onSave={(v) => save({ fit_notes: v })} />
          <ChipGroup field="condition" options={vocab.condition} value={item.condition} disabled={locked} onChange={(v) => save({ condition: v })} />
          <PriceField cents={item.price_cents} disabled={locked} onSave={(c) => save({ price_cents: c })} toastError={(m) => toast(m, 'error')} />
          <TextField label="Date acquired" type="date" value={item.acquired_on} disabled={locked} onSave={(v) => save({ acquired_on: v })} />
          <TextField label="Notes" multiline value={item.notes} disabled={locked} onSave={(v) => save({ notes: v })} />
        </div>
      </details>

      <Actions item={item} disabled={locked} onArchive={async (archived) => {
        await save({ status: archived ? 'archived' : 'active' }, archived ? 'Archived' : 'Back in your closet');
      }} onDelete={async () => {
        try {
          await api.remove(id);
          drop(id);
          toast('Deleted');
          navigate(backTo);
        } catch (e) {
          toast((e as Error).message, 'error');
        }
      }} />
    </article>
  );
}

function DetailTop({ inPanel, backTo }: { inPanel?: boolean; backTo: string }) {
  if (inPanel) return null;
  return (
    <div className="detail-top">
      <Link to={backTo} className="btn btn-ghost back-link"><BackIcon /> Closet</Link>
    </div>
  );
}

function Picture({ item, busyText, fallbackThumb }: { item: Item; busyText: string; fallbackThumb?: string | null }) {
  const photo = item.photos[0];
  const views: { key: View; label: string }[] = [];
  if (item.illustration_url || item.has_illustration) views.push({ key: 'illustration', label: 'Illustration' });
  if (photo?.cutout_url) views.push({ key: 'cutout', label: 'Cutout' });
  if (photo?.url) views.push({ key: 'photo', label: 'Photo' });
  const preferred: View | undefined = photo?.cutout_url ? 'cutout' : views[0]?.key;
  const [chosen, setChosen] = useState<View | undefined>(undefined);
  const view = chosen && views.some((v) => v.key === chosen) ? chosen : preferred;
  const alt = item.name || label('category', item.category) || 'Item';
  const busy = item.cutout_state === 'pending' || item.cutout_state === 'processing';

  let pic: ReactNode;
  if (view === 'cutout') pic = <img className="pic-cutout" src={photo!.cutout_url!} alt={`${alt}, background removed`} />;
  else if (view === 'photo') pic = <img className="pic-photo-full" src={photo!.url!} alt={`${alt}, original photo`} />;
  else if (view === 'illustration') {
    pic = item.illustration_url
      ? <img className="pic-illustration" src={item.illustration_url} alt={`${alt}, illustration`} />
      : <div className="pic-illustration" role="img" aria-label={`${alt}, illustration`} dangerouslySetInnerHTML={{ __html: item.illustration_svg ?? '' }} />;
  } else if (fallbackThumb) pic = <img className={item.cutout_state === 'ready' ? 'pic-cutout' : 'pic-photo'} src={fallbackThumb} alt={alt} />;
  else pic = <div className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></div>;

  return (
    <div className="detail-picture-wrap">
      <div className={`detail-picture view-${view ?? 'none'}`}>
        {pic}
        {busy && <span className="badge badge-busy"><span className="spinner" aria-hidden="true" />{busyText}</span>}
      </div>
      {views.length > 1 && (
        <div className="segmented" role="group" aria-label="Picture">
          {views.map((v) => (
            <button key={v.key} type="button" className={view === v.key ? 'is-on' : ''} aria-pressed={view === v.key} onClick={() => setChosen(v.key)}>
              {v.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function NameField({ value, placeholder, disabled, onSave }: { value: string | null; placeholder: string; disabled: boolean; onSave(v: string | null): void }) {
  const [text, setText] = useState(value ?? '');
  useEffect(() => setText(value ?? ''), [value]);
  const commit = () => {
    const v = text.trim();
    if (v !== (value ?? '')) onSave(v || null);
  };
  return (
    <label className="name-field">
      <span className="visually-hidden">Name</span>
      <input value={text} placeholder={placeholder} disabled={disabled} maxLength={120}
        onChange={(e) => setText(e.target.value)} onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
          if (e.key === 'Escape') setText(value ?? '');
        }} />
    </label>
  );
}

interface TextFieldProps {
  label: string;
  value: string | null;
  disabled?: boolean;
  placeholder?: string;
  type?: string;
  multiline?: boolean;
  onSave(v: string | null): void;
}

function TextField({ label: text, value, disabled, placeholder, type = 'text', multiline, onSave }: TextFieldProps) {
  const [v, setV] = useState(value ?? '');
  useEffect(() => setV(value ?? ''), [value]);
  const commit = () => {
    const t = v.trim();
    if (t !== (value ?? '')) onSave(t || null);
  };
  return (
    <label className="field">
      <span>{text}</span>
      {multiline ? (
        <textarea value={v} rows={3} disabled={disabled} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={commit} />
      ) : (
        <input type={type} value={v} disabled={disabled} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
      )}
    </label>
  );
}

function PriceField({ cents, disabled, onSave, toastError }: { cents: number | null; disabled: boolean; onSave(c: number | null): void; toastError(m: string): void }) {
  const [v, setV] = useState(formatPrice(cents));
  useEffect(() => setV(formatPrice(cents)), [cents]);
  const commit = () => {
    const parsed = parsePrice(v);
    if (parsed === undefined) {
      toastError('Enter a price like 45 or 45.50.');
      setV(formatPrice(cents));
      return;
    }
    if (parsed !== cents) onSave(parsed);
  };
  return (
    <label className="field">
      <span>Price</span>
      <span className="input-prefix">
        <span aria-hidden="true">$</span>
        <input inputMode="decimal" value={v} disabled={disabled} placeholder="0.00" onChange={(e) => setV(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
      </span>
    </label>
  );
}

function Actions({ item, disabled, onArchive, onDelete }: { item: Item; disabled: boolean; onArchive(a: boolean): Promise<void>; onDelete(): Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const archived = item.status === 'archived';
  return (
    <div className="detail-actions">
      {!confirming ? (
        <div className="row">
          <button className="btn" disabled={disabled} onClick={() => onArchive(!archived)}>{archived ? 'Unarchive' : 'Archive'}</button>
          <button className="btn btn-danger-quiet" disabled={disabled} onClick={() => setConfirming(true)}>Delete</button>
        </div>
      ) : (
        <div className="confirm" role="alertdialog" aria-labelledby="del-q">
          <p id="del-q"><strong>Delete this item for good?</strong> Its photos are removed too. To just put it away, archive it instead.</p>
          <div className="row">
            <button className="btn btn-danger" onClick={onDelete} autoFocus>Delete</button>
            <button className="btn" onClick={() => setConfirming(false)}>Keep it</button>
          </div>
        </div>
      )}
    </div>
  );
}
