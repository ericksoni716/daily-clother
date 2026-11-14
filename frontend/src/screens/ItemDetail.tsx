import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { ChipGroup } from '../components/ui/Chips';
import { Notice, PHONE, Section, SegmentedControl, Sheet } from '../components/ui';
import { FixDetails, FixDetailsButton, ItemHistory } from '../components/FixDetails';
import { KindPicker } from '../components/KindPicker';
import { BackIcon, ChevronIcon, HangerIcon, WarnIcon } from '../components/Icons';
import { FIELD_TITLES, formatPrice, label, measuredColours, parsePrice, ratingLabel, SWATCH, swatchOf, tileCaption } from '../labels';
import { useWhenLeaving } from '../leave';
import { Link, navigate, useMediaQuery } from '../router';
import { silhouetteGroups } from '../silhouette';
import { useCloset } from '../store';
import { drawingPlaceholder, loadGridView, notInDrawing } from '../drawing';
import { describedBy, detailLines, tagNotice } from '../tagging';
import { kindDrawing, kindLine, type KindGroup } from '../kinds';
import { sureText } from '../review';
import type { Item, ItemPatch, PatternColour } from '../types';
import { localDay, sinceWash, wearDay, wearSummary } from '../wears';
import { busyLabel } from './Closet';

type View = 'drawing' | 'cutout' | 'photo';

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
  const { vocab, upsert, drop, toast, offline, model, items, profile } = useCloset();
  const [item, setItem] = useState<Item | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fixing, setFixing] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
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

  // Follow the cutout while it is being made, and the description while it is waited for or being written
  // (slowly while it waits: nothing changes until Claude can be reached). The closet grid follows along.
  const busy = item?.cutout_state === 'pending' || item?.cutout_state === 'processing';
  const describing = item?.tag_state === 'working';
  const awaiting = item?.tag_state === 'waiting';
  const measuring = item?.pattern_state === 'waiting' || item?.pattern_state === 'working';
  const followed = useRef('');
  useEffect(() => {
    if (!(busy || describing || awaiting || measuring) || offline) return;
    const t = window.setInterval(async () => {
      if (inflight.current) return;
      try {
        const fresh = await api.item(id);
        if (inflight.current) return;
        setItem(fresh);
        const states = `${fresh.cutout_state}/${fresh.tag_state}/${fresh.pattern_state}`;
        if (states !== followed.current) upsert(fresh);
        followed.current = states;
      } catch {
        /* the next tick tries again */
      }
    }, busy || describing ? 2000 : measuring ? 5000 : 10_000);
    return () => window.clearInterval(t);
  }, [busy, describing, awaiting, measuring, offline, id, upsert]);

  const retag = useCallback(async () => {
    try {
      const saved = await api.retag(id);
      setItem(saved);
      upsert(saved);
      toast('Asking Claude to describe it again');
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }, [id, upsert, toast]);

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

  // Wears and the laundry are changed through their own calls, each answering with the whole item.
  const act = useCallback(async (call: () => Promise<Item>, saidAs: string): Promise<Item | undefined> => {
    inflight.current++;
    try {
      const saved = await call();
      inflight.current--;
      setItem(saved);
      upsert(saved);
      toast(saidAs);
      return saved;
    } catch (e) {
      inflight.current--;
      toast((e as ApiError).message, 'error');
      if (!inflight.current) void load();
    }
  }, [upsert, toast, load]);

  if (error && !item) {
    const summary = items.active?.find((x) => x.id === id) ?? items.archived?.find((x) => x.id === id);
    if (offline && summary) {
      // Not saved for offline use yet: show what the closet list knows.
      const asItem = { ...summary, photos: [], silhouette: {}, illustration_svg: null, seen_not_drawn: [], drawing_notes: [] } as unknown as Item;
      return (
        <article className="detail" aria-label={summary.name || 'Item'}>
          <DetailTop inPanel={inPanel} backTo={backTo} />
          <Picture item={asItem} busyText={busyLabel(model)} fallbackThumb={summary.thumb_url} />
          <Notice as="p">You're offline, so this item can't be changed right now. Its full details show once Closet can be reached again.</Notice>
          <header className="detail-head">
            <h2 className="detail-title">{summary.name || label('category', summary.category) || 'Item'}</h2>
            <p className="detail-meta">{[label('category', summary.category), label('color', summary.color), label('pattern', summary.pattern), label('location', summary.location)].filter(Boolean).join(' · ')}</p>
          </header>
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
  const tagText = tagNotice(item.tag_state, item.tag_route, item.tag_error);
  const lines = detailLines(item.details);
  const seen = item.seen_not_drawn ?? [];
  const canRetag = profile !== 'demo' && item.cutout_state === 'ready' && item.has_photo &&
    (item.tag_state === 'done' || item.tag_state === 'none');
  const fixed = (saved: Item, saidAs: string) => {
    setItem(saved);
    upsert(saved);
    toast(saidAs);
  };
  const failed = (message: string) => toast(message, 'error');

  return (
    <article className="detail" aria-label={item.name || 'Item'}>
      <DetailTop inPanel={inPanel} backTo={backTo} />
      {locked && <Notice as="p">You're offline, so this item can't be changed right now.</Notice>}

      <Picture item={item} busyText={busyLabel(model)}
        fix={<FixDetailsButton open={fixing} disabled={locked} onToggle={() => setFixing((f) => !f)} />} />
      <FixDetails item={item} open={fixing} disabled={locked} onSaved={fixed} onError={failed} />

      {measuring && (
        <p className="notice" role="status" data-testid="pattern-measuring">
          Measuring the {patternWord(item.pattern)} from the photo, so the drawing can show it. This can take a minute or two.
        </p>
      )}
      {item.pattern_state === 'failed' && item.pattern_error && (
        <p className="muted tag-note" data-testid="pattern-failed">{item.pattern_error}</p>
      )}
      {item.cutout_state === 'failed' && (
        <div className="notice notice-warn">
          <WarnIcon />
          <div>
            <p><strong>The background couldn't be removed.</strong>{item.cutout_error ? ` ${item.cutout_error}` : ''}</p>
            <FailureDetails item={item} stage="cutout" />
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

      <header className="detail-head">
        <h2 className="detail-title">
          <NameField value={item.name} placeholder={label('category', item.category) || 'Name this item'} disabled={locked}
            onSave={(name) => save({ name })} />
        </h2>
        {tileCaption(item.category, item.color) && <p className="detail-meta">{tileCaption(item.category, item.color)}</p>}
      </header>

      <WearPanel item={item} disabled={locked}
        onWear={() => act(() => api.wear(id), 'Noted: worn today')}
        onUnwear={(day, said) => act(() => api.unwear(id, day), said)}
        onLaundry={(state) => act(() => api.setLaundry(id, state), state === 'laundry' ? 'In the laundry' : 'Marked clean')} />

      {item.tag_state === 'failed' ? (
        <div className="notice notice-warn">
          <WarnIcon />
          <div>
            <p><strong>Claude couldn't describe this item.</strong>{item.tag_error ? ` ${item.tag_error}` : ''}</p>
            <FailureDetails item={item} stage="description" />
            <button className="btn btn-small" disabled={locked} onClick={retag}>Try again</button>
          </div>
        </div>
      ) : item.tag_state !== 'done' && tagText ? (
        <p className="notice" role="status">
          {tagText}
          {item.tag_state === 'waiting' && item.tag_error && <> <Link to="/settings">Open Settings</Link></>}
        </p>
      ) : null}
      {item.pattern_state === 'failed' && item.pattern_error && (
        <p className="muted tag-note" data-testid="pattern-failed">{item.pattern_error}</p>
      )}

      <Section id={`details-${item.id}`} title="Details" className="detail-fields"
        hint={item.tag_state === 'done' && tagText ? tagText : undefined}>
        <Editing.Provider value={{ editing, setEditing }}>
        <ul className="detail-rows">
          <KindRow item={item} groups={vocab.kind_groups} disabled={locked} onSaved={fixed} onError={failed} />
          <DetailRow field="color" value={label('color', item.color)} swatch={item.color ? (item.color_hex ?? swatchOf(item.color)) : undefined} disabled={locked}>
            {(done) => <ChipGroup field="color" options={vocab.color} value={item.color} disabled={locked} swatches
              onChange={(v) => { done(); void save({ color: v, color_hex: v ? (SWATCH[v]?.startsWith('#') ? SWATCH[v] : null) : null }); }} />}
          </DetailRow>
          <DetailRow field="pattern" value={label('pattern', item.pattern)} disabled={locked}
            extra={<MeasuredColours colours={item.pattern_colors} />}
            extraWords={item.pattern_colors?.length ? `Colours measured from the photo: ${measuredColours(item.pattern_colors)}` : undefined}>
            {(done) => <ChipGroup field="pattern" options={vocab.pattern} value={item.pattern} disabled={locked}
              beside={<MeasuredColours colours={item.pattern_colors} />}
              onChange={(v) => { done(); void save({ pattern: v }); }} />}
          </DetailRow>
          {(['formality', 'season', 'location'] as const).map((f) => (
            <DetailRow key={f} field={f} value={label(f, item[f])} disabled={locked}>
              {(done) => <ChipGroup field={f} options={vocab[f]} value={item[f]} disabled={locked}
                onChange={(v) => { done(); void save({ [f]: v }); }} />}
            </DetailRow>
          ))}
          {groups.map((g) => (
            <DetailRow key={g} field={g} value={label(g, item.silhouette?.[g])} disabled={locked}>
              {(done) => <ChipGroup field={g} options={vocab.silhouette[g] ?? []} value={item.silhouette?.[g]} disabled={locked}
                onChange={(v) => { done(); void save({ silhouette: { [g]: v } }); }} />}
            </DetailRow>
          ))}
          <DetailRow field="rating" value={[item.rating ? ratingLabel(item.rating) : '', item.rating_reason].filter(Boolean).join(' · ')} disabled={locked}>
            {() => (
              <>
                <ChipGroup field="rating" options={vocab.rating} value={item.rating} disabled={locked} labelOf={ratingLabel}
                  onChange={(v) => save(v ? { rating: v } : { rating: null, rating_reason: null })} />
                {item.rating && (
                  <TextField label="Why? (optional)" value={item.rating_reason} disabled={locked} placeholder="e.g. great fit, itchy collar"
                    onSave={(v) => save({ rating_reason: v })} />
                )}
              </>
            )}
          </DetailRow>
        </ul>
        </Editing.Provider>
      </Section>

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

      {(lines.length > 0 || seen.length > 0) && (
        <details className="more">
          <summary>What Claude saw</summary>
          <div className="tag-body">
            {lines.length > 0 && (
              <dl className="tag-details">
                {lines.map((l) => (
                  <div key={l.title}><dt>{l.title}</dt><dd>{l.value}</dd></div>
                ))}
              </dl>
            )}
            {seen.length > 0 && (
              <>
                <h3 className="tag-seen-title">Seen but not drawn yet</h3>
                <ul className="tag-seen">{seen.map((f) => <li key={f}>{f}</li>)}</ul>
              </>
            )}
            {describedBy(item.tag_route, item.tagged_at) && <p className="muted">{describedBy(item.tag_route, item.tagged_at)}</p>}
          </div>
        </details>
      )}

      <ItemHistory item={item} disabled={locked} onSaved={fixed} onError={failed} />

      {canRetag && (
        <div className="row tag-again">
          <button className="btn" disabled={locked} onClick={retag}>Describe it again</button>
        </div>
      )}

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

const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';

/** Which of the Details rows is open: one at a time. */
const Editing = createContext<{ editing: string | null; setEditing(field: string | null): void }>({ editing: null, setEditing: () => {} });

/**
 * One row of the Details card: the field and its value, read first. Tapping it opens the field's choices in place,
 * or in a sheet on a phone, where it closes again once something is chosen.
 */
function DetailRow({ field, value, swatch, extra, extraWords, disabled, children }: {
  field: string;
  value: string;
  swatch?: string;
  /** shown after the value (the measured colours beside the pattern), with its words for the row's name */
  extra?: ReactNode;
  extraWords?: string;
  disabled: boolean;
  children(done: () => void): ReactNode;
}) {
  const { editing, setEditing } = useContext(Editing);
  const phone = useMediaQuery(PHONE);
  const editorId = useId();
  const open = editing === field && !disabled;
  const title = FIELD_TITLES[field] ?? field;
  const shown = value || 'Not set';
  const done = () => {
    if (phone) setEditing(null);
  };
  return (
    <li className={`detail-row${open ? ' is-open' : ''}`}>
      <button type="button" className="detail-row-button" aria-expanded={open} aria-controls={open ? editorId : undefined}
        aria-label={`${title}: ${shown}${extraWords ? `. ${extraWords}` : ''}`} disabled={disabled} title={disabled ? OFFLINE_TITLE : undefined}
        onClick={() => setEditing(open ? null : field)}>
        <span className="detail-row-label">{title}</span>
        <span className={`detail-row-value${value ? '' : ' is-empty'}`}>
          {swatch && <span className="swatch" style={{ background: swatch }} aria-hidden="true" />}
          <span className="detail-row-text">{shown}</span>
          {extra}
        </span>
        <ChevronIcon className="detail-row-chevron" />
      </button>
      {open && (
        <Sheet title={title} className="detail-editor" onClose={() => setEditing(null)}>
          <div id={editorId}>{children(done)}</div>
        </Sheet>
      )}
    </li>
  );
}

/**
 * "What is it?": the item's kind from the owner's taxonomy, with its small drawing, and how sure Claude was when it is
 * Claude's word. Tapping it opens the kinds to choose from: a sheet on a phone, a popover on a wider screen.
 */
function KindRow({ item, groups, disabled, onSaved, onError }: {
  item: Item;
  groups: KindGroup[] | undefined;
  disabled: boolean;
  onSaved(item: Item, saidAs: string): void;
  onError(message: string): void;
}) {
  const { editing, setEditing } = useContext(Editing);
  const button = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const open = editing === 'kind' && !disabled;
  const line = kindLine(item, groups) || 'Not said';
  const who = item.kind_by === 'owner' ? 'Set by you'
    : item.kind_by === 'claude' ? `Claude's guess${item.kind_confidence != null ? ` · ${sureText(item.kind_confidence)}` : ''}`
    : item.kind ? '' : 'Kind not said yet';
  return (
    <li className={`detail-row kind-row${open ? ' is-open' : ''}`}>
      <button ref={button} type="button" className="detail-row-button" aria-expanded={open} aria-haspopup="dialog"
        aria-label={`What is it?: ${line}${who ? `. ${who}` : ''}`} disabled={disabled} title={disabled ? OFFLINE_TITLE : undefined}
        data-testid="what-is-it" onClick={() => setEditing(open ? null : 'kind')}>
        <span className="detail-row-label">What is it?</span>
        <span className={`detail-row-value${item.kind ? '' : ' is-empty'}`}>
          {item.kind && (
            <img className="kind-row-pic" src={kindDrawing(item.kind, item.color_hex)} alt="" data-testid="kind-pic" />
          )}
          <span className="kind-row-words">
            <span className="detail-row-text">{line}</span>
            {who && <span className="kind-row-sure">{who}</span>}
          </span>
        </span>
        <ChevronIcon className="detail-row-chevron" />
      </button>
      {open && (
        <Sheet title="What is it?" popover keep={button} className="detail-editor kind-sheet" testId="kind-picker"
          onClose={() => setEditing(null)}>
          <KindPicker item={item} busy={busy} onPick={async (kind) => {
            if (kind.id === item.kind && item.kind_by === 'owner') {
              setEditing(null);
              return;
            }
            setBusy(true);
            try {
              const saved = await api.setKind(item.id, kind.id);
              setEditing(null);
              onSaved(saved, `What it is: ${kind.name}`);
            } catch (e) {
              onError((e as ApiError).message);
            } finally {
              setBusy(false);
            }
          }} />
        </Sheet>
      )}
    </li>
  );
}

interface WearPanelProps {
  item: Item;
  disabled: boolean;
  onWear(): Promise<Item | undefined>;
  onUnwear(day: string, saidAs: string): Promise<Item | undefined>;
  onLaundry(state: 'clean' | 'laundry'): Promise<Item | undefined>;
}

function WearPanel({ item, disabled, onWear, onUnwear, onLaundry }: WearPanelProps) {
  const today = localDay();
  // "today" is the computer's date on the server; remember the day it answered so undo works even if this device's date differs
  // (kept only for the local day it was pressed on, so it does not stick past midnight)
  const [logged, setLogged] = useState<{ server: string; local: string } | null>(null);
  const wornToday = !!item.last_worn && (item.last_worn === today || (logged?.local === today && item.last_worn === logged.server));
  const inLaundry = item.laundry === 'laundry';
  const title = disabled ? OFFLINE_TITLE : undefined;
  const recent = item.recent_wears ?? [];
  return (
    <section className="wear" aria-label="Wearing and washing">
      <div className="wear-text">
        <p className="wear-summary" data-testid="wear-summary">{wearSummary(item.wear_count, item.last_worn, today)}</p>
        <p className="muted" data-testid="laundry-state">
          {inLaundry ? 'In the laundry' : 'Clean'}{item.wear_count ? ` · ${sinceWash(item.wears_since_wash)}` : ''}
        </p>
      </div>
      <div className="row wear-actions">
        {wornToday ? (
          <>
            <span className="wear-done">Worn today</span>
            <button className="btn btn-small" disabled={disabled} title={title}
              onClick={() => onUnwear(item.last_worn!, 'Wear undone')}>Undo</button>
          </>
        ) : (
          <button className="btn btn-primary btn-small" disabled={disabled} title={title} onClick={async () => {
            const saved = await onWear();
            if (saved?.last_worn) setLogged({ server: saved.last_worn, local: localDay() });
          }}>Wore it today</button>
        )}
        {inLaundry ? (
          <button className="btn btn-small" disabled={disabled} title={title} onClick={() => onLaundry('clean')}>It's clean</button>
        ) : (
          <button className="btn btn-small" disabled={disabled} title={title} onClick={() => onLaundry('laundry')}>Put in the laundry</button>
        )}
      </div>
      {recent.length > 0 && (
        <div className="wear-recent">
          <p className="chip-group-title" id={`recent-${item.id}`}>Recent wears</p>
          <ul aria-labelledby={`recent-${item.id}`}>
            {recent.map((day) => (
              <li key={day}>
                <span>{wearDay(day, today)}</span>
                <button className="btn btn-link" disabled={disabled} title={title} aria-label={`Remove the wear: ${wearDay(day, today)}`}
                  onClick={() => onUnwear(day, 'Wear removed')}>Remove</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** What was recorded when the cutout or the description failed, folded away (keys and outside paths taken out). */
function FailureDetails({ item, stage }: { item: Item; stage: 'cutout' | 'description' }) {
  const details = item.failure?.stage === stage ? item.failure.details : null;
  if (!details) return null;
  return (
    <details className="failure-details" data-testid="failure-details">
      <summary>Details</summary>
      <p>What Closet recorded, for working out what went wrong:</p>
      <pre>{details}</pre>
    </details>
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

function Picture({ item, busyText, fallbackThumb, fix }: { item: Item; busyText: string; fallbackThumb?: string | null; fix?: ReactNode }) {
  const photo = item.photos[0];
  const hasDrawing = !!(item.illustration_url || item.has_illustration);
  const placeholder = drawingPlaceholder(item.tag_state, item.category, hasDrawing);
  const views: { key: View; label: string }[] = [];
  // the drawing's place is offered while one is on its way, so it can say so
  if (hasDrawing || item.tag_state === 'waiting' || item.tag_state === 'working') views.push({ key: 'drawing', label: 'Drawing' });
  if (photo?.cutout_url) views.push({ key: 'cutout', label: 'Cutout' });
  if (photo?.url) views.push({ key: 'photo', label: 'Photo' });
  const [liked] = useState(loadGridView);
  const preferred: View | undefined = liked === 'drawings' && hasDrawing ? 'drawing' : photo?.cutout_url ? 'cutout' : views[0]?.key;
  const [chosen, setChosen] = useState<View | undefined>(undefined);
  const view = chosen && views.some((v) => v.key === chosen) ? chosen : preferred;
  const alt = item.name || label('category', item.category) || 'Item';
  const busy = item.cutout_state === 'pending' || item.cutout_state === 'processing';
  const missing = view === 'drawing' && !placeholder ? notInDrawing(item.seen_not_drawn, item.drawing_notes) : [];

  let pic: ReactNode;
  if (view === 'cutout') pic = <img className="pic-cutout" src={photo!.cutout_url!} alt={`${alt}, background removed`} />;
  else if (view === 'photo') pic = <img className="pic-photo-full" src={photo!.url!} alt={`${alt}, original photo`} />;
  else if (view === 'drawing') {
    pic = placeholder
      ? <div className="pic-placeholder pic-waiting" role="status"><HangerIcon /><p>{placeholder}</p></div>
      : item.illustration_url
        ? <img className="pic-illustration" src={item.illustration_url} alt={`${alt}, drawing`} />
        : <div className="pic-illustration" role="img" aria-label={`${alt}, drawing`} dangerouslySetInnerHTML={{ __html: item.illustration_svg ?? '' }} />;
  } else if (fallbackThumb) pic = <img className={item.cutout_state === 'ready' ? 'pic-cutout' : 'pic-photo'} src={fallbackThumb} alt={alt} />;
  else pic = <div className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></div>;

  return (
    <div className={`detail-picture-wrap${missing.length ? ' has-notes' : ''}`}>
      <div className="detail-picture-main">
        <div className={`detail-picture view-${view ?? 'none'}`}>
          {pic}
          {busy && <span className="badge badge-busy"><span className="spinner" aria-hidden="true" />{busyText}</span>}
        </div>
        {(views.length > 1 || fix) && (
          <div className="picture-controls">
            {views.length > 1 && (
              <SegmentedControl label="Picture" small value={view} options={views.map((v) => ({ value: v.key, label: v.label }))} onChange={setChosen} />
            )}
            {fix}
          </div>
        )}
      </div>
      {missing.length > 0 && (
        <section className="drawing-notes" aria-labelledby="drawing-notes-title">
          <h3 id="drawing-notes-title">Not in the drawing</h3>
          <ul>{missing.map((m) => <li key={m}>{m}</li>)}</ul>
        </section>
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
  useWhenLeaving(commit);
  return (
    <span className="name-field">
      <input aria-label="Name" value={text} placeholder={placeholder} disabled={disabled} maxLength={120}
        onChange={(e) => setText(e.target.value)} onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
          if (e.key === 'Escape') setText(value ?? '');
        }} />
    </span>
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
  useWhenLeaving(commit);
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
  useWhenLeaving(() => {
    const parsed = parsePrice(v);
    if (parsed !== undefined && parsed !== cents) onSave(parsed);
  });
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

/** The colours measured from the pattern, as small swatches beside the pattern word. */
function MeasuredColours({ colours }: { colours?: PatternColour[] }) {
  if (!colours?.length) return null;
  const words = `Colours measured from the photo: ${measuredColours(colours)}`;
  return (
    <span className="measured-colours" role="img" aria-label={words} title={words} data-testid="pattern-colours">
      {colours.map((c) => <span key={c.color} className="swatch" style={{ background: c.hex }} />)}
    </span>
  );
}

function patternWord(pattern: string | null): string {
  return ({ stripe: 'stripes', plaid: 'plaid', floral: 'print', camo: 'camouflage' } as Record<string, string>)[pattern ?? ''] ?? 'pattern';
}
