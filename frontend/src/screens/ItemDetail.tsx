import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { ChipGroup } from '../components/ui/Chips';
import { BackLink, confirmKeys, Notice, PHONE, Section, SegmentedControl, Sheet, useConfirmFocus } from '../components/ui';
import { FixDetails, ItemHistory } from '../components/FixDetails';
import { WhatItIs } from '../components/WhatItIs';
import { RetakeButton } from '../components/RetakeButton';
import { ShoeDrawn } from '../components/ShoeDrawn';
import { ShoePhotos } from '../components/ShoePhotos';
import { TraceNotice } from '../components/ShoeTrace';
import { ProgressStrip } from '../components/Progress';
import { BackIcon, ChevronIcon, HangerIcon, InfoIcon, WarnIcon } from '../components/Icons';
import { FIELD_TITLES, formatPrice, label, shadeLabel, measuredColours, parsePrice, PRICE_HINT, ratingLabel, SWATCH, swatchOf } from '../labels';
import { fixLabel, lastFoldTitle } from '../look';
import { LookLine, NotesBox, useFieldText } from '../components/ItemAbout';
import { SaveLine, useWhenLeaving } from '../leave';
import { navigate, useMediaQuery } from '../router';
import { dropItem, itemQuery, itemSaved, touch, useItemProgress, useItemSummary, useVocab, writeSummary } from '../queries';
import { itemPoll } from '../work';
import { queryKeys, type EditKind } from '../queryKeys';
import { useApp } from '../store';
import { notInDrawing, useShowDrawings } from '../drawing';
import { busy, drawingOnItsWay, drawingPlaceholder } from '../progress';
import { retakeOffer, retakeSaid } from '../retake';
import type { Item, ItemPatch, PatternColour, Progress } from '../types';
import { localDay, sinceWash, wearDay, wearSummary } from '../wears';

type View = 'drawing' | 'cutout' | 'photo';

interface Props {
  id: string;
  status: 'active' | 'archived';
  inPanel?: boolean;
}

/** What a save shows at once, before the server answers. The look (the shape and the details) is never changed here:
 * it is corrected in "Fix the details", and the server answers with the drawing and the words together. */
function applyPatch(item: Item, changes: ItemPatch): Item {
  const rest: Partial<ItemPatch> = { ...changes };
  delete rest.silhouette;
  return { ...item, ...(rest as Partial<Item>) };
}

export function ItemDetail({ id, status, inPanel }: Props) {
  const { toast, offline, profile } = useApp();
  const qc = useQueryClient();
  const vocab = useVocab();
  // The closet's summary of it, shown at once while the full item is read (or when it cannot be, offline).
  const summary = useItemSummary(id);
  // read again by itself only while Claude draws onto its drawing (`itemPoll`); the closet's poll does the rest
  const query = useQuery({ ...itemQuery(id), refetchInterval: (q) => itemPoll(q.state.data, offline) ?? false });
  const item = query.data ?? null;
  const error = query.error ? query.error.message : null;
  const [fixing, setFixing] = useState(false);
  const [focus, setFocus] = useState<{ field: string; at: number } | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  // Saves still on their way: the item is not read again meanwhile, so what the owner just chose stays on screen.
  const inflight = useRef(0);
  const saves = useRef(new SaveLine());
  const backTo = status === 'archived' ? '/archived' : '/';

  const load = useCallback(() => {
    if (!inflight.current) void qc.refetchQueries({ queryKey: queryKeys.item(id), exact: true }, { cancelRefetch: false });
  }, [qc, id]);

  // How far the work on it has got. The closet's provider follows the work under way and reads the item again each
  // time it moves on (src/work.ts), so the page itself never polls.
  const progress = useItemProgress(item ?? summary);

  const retag = useCallback(async () => {
    try {
      itemSaved(qc, await api.retag(id));
      toast('Asking Claude to describe it again');
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }, [id, qc, toast]);

  const save = useCallback(async (changes: ItemPatch, saidAs = 'Saved') => {
    if (!item) return;
    const key = queryKeys.item(id);
    const before = item;
    void qc.cancelQueries({ queryKey: key, exact: true });
    qc.setQueryData<Item>(key, (cur) => (cur ? applyPatch(cur, changes) : cur));
    inflight.current++;
    try {
      const saved = await saves.current.add(() => api.patch(id, changes));
      inflight.current--;
      if (!inflight.current) itemSaved(qc, saved);
      else {   // a later save is still on its way: the page keeps what was chosen, the lists take this answer
        writeSummary(qc, saved);
        void touch(qc, 'item', ['items', 'item']);
      }
      toast(saidAs);
    } catch (e) {
      inflight.current--;
      toast((e as ApiError).message, 'error');
      if (!inflight.current) {
        qc.setQueryData(key, before);
        load();
      }
    }
  }, [item, id, qc, toast, load]);

  // Wears and the laundry are changed through their own calls, each answering with the whole item.
  const act = useCallback(async (call: () => Promise<Item>, kind: EditKind, saidAs: string): Promise<Item | undefined> => {
    inflight.current++;
    try {
      const saved = await call();
      inflight.current--;
      itemSaved(qc, saved, kind);
      toast(saidAs);
      return saved;
    } catch (e) {
      inflight.current--;
      toast((e as ApiError).message, 'error');
      load();
    }
  }, [qc, toast, load]);

  if (error && !item && !(offline && summary)) {
    return (
      <div className="detail">
        <DetailTop inPanel={inPanel} backTo={backTo} />
        <div className="empty"><p className="form-error" role="alert">{error}</p></div>
      </div>
    );
  }
  if (!item || !vocab) {
    if (summary) {
      // What the closet list knows, until the full item is here; offline and not saved for offline use, that is all.
      const asItem = { ...summary, photos: [], silhouette: {}, illustration_svg: null, seen_not_drawn: [], drawing_notes: [] } as unknown as Item;
      const away = !!error && offline;
      return (
        <article className="detail" aria-label={summary.name || 'Item'} aria-busy={away ? undefined : 'true'}>
          <DetailTop inPanel={inPanel} backTo={backTo} />
          <Picture item={asItem} progress={progress} fallbackThumb={summary.thumb_url} />
          {away && <Notice as="p">You're offline, so this item can't be changed right now. Its full details show once Nines can be reached again.</Notice>}
          <header className="detail-head">
            <h2 className="detail-title"><span className="name-field name-field-static">{summary.name || label('category', summary.category) || 'Item'}</span></h2>
          </header>
          <section className="essentials" aria-label="What it is, brand and price">
            <WhatItIs item={{ ...summary, kind_by: null, kind_confidence: null }} groups={vocab?.kind_groups} disabled />
          </section>
        </article>
      );
    }
    return (
      <div className="detail" aria-busy="true">
        <DetailTop inPanel={inPanel} backTo={backTo} />
        <div className="detail-picture tile-skeleton" />
      </div>
    );
  }

  const locked = offline;
  const demo = profile === 'demo';
  const failure = progress?.state === 'failed' ? progress : null;
  const canRetag = !demo && item.cutout_state === 'ready' && item.has_photo &&
    (item.tag_state === 'done' || item.tag_state === 'none');
  const fixed = (saved: Item, saidAs: string) => {
    itemSaved(qc, saved);
    toast(saidAs);
  };
  const failed = (message: string) => toast(message, 'error');
  const openFix = (field: string | null) => {
    setFocus(field ? { field, at: Date.now() } : null);
    setFixing(true);
  };
  // clothes: a new photo when the background couldn't be removed or the pattern couldn't be measured (one button)
  const offer = retakeOffer(item);
  const retake = offer && (
    <RetakeButton item={item} disabled={locked} said={retakeSaid(item, demo)} onError={failed}
      onSaved={fixed} />
  );

  return (
    <article className="detail" aria-label={item.name || 'Item'}>
      <DetailTop inPanel={inPanel} backTo={backTo} />
      {locked && <Notice as="p">You're offline, so this item can't be changed right now.</Notice>}

      {/* 1. the picture and the name, the name typed over in place; what went wrong with the picture sits under it */}
      <Picture item={item} progress={progress} />
      {item.pattern_state === 'failed' && item.pattern_error && (
        <div className="tag-note pattern-failed" data-testid="pattern-failed">
          <p className="muted">{item.pattern_error}</p>
          {offer === 'pattern' && <div className="row">{retake}</div>}
        </div>
      )}
      {failure && (failure.retry === 'cutout' || failure.retry === 'describe') && (
        <div className="notice notice-warn" data-testid="progress-failed">
          <WarnIcon />
          <div>
            <p><strong>{failure.words}.</strong>{failure.error ? ` ${failure.error}` : ''}</p>
            <FailureDetails item={item} stage={failure.retry === 'cutout' ? 'cutout' : 'description'} />
            {failure.retry === 'cutout' ? (
              <div className="row">
                <button className="btn btn-small" disabled={locked} onClick={async () => {
                  try {
                    itemSaved(qc, await api.retryCutout(id));
                    toast('Trying the cutout again');
                  } catch (e) {
                    toast((e as Error).message, 'error');
                  }
                }}>Try the cutout again</button>
                {offer === 'cutout' && retake}
              </div>
            ) : <button className="btn btn-small" disabled={locked} onClick={retag}>Try again</button>}
          </div>
        </div>
      )}

      <header className="detail-head">
        <h2 className="detail-title">
          <NameField value={item.name} placeholder={label('category', item.category) || 'Name this item'} disabled={locked}
            onSave={(name) => save({ name })} />
        </h2>
      </header>

      {/* 2. the essentials, gone through on every new piece: what it is, its brand and its price */}
      <section className="essentials" aria-label="What it is, brand and price" data-testid="essentials">
        <WhatItIs item={item} groups={vocab.kind_groups} disabled={locked} onPick={async (kind) => {
          if (kind.id === item.kind && item.kind_by === 'owner') return true;
          try {
            fixed(await api.setKind(item.id, kind.id), `What it is: ${kind.name}`);
            return true;
          } catch (e) {
            failed((e as ApiError).message);
            return false;
          }
        }} />
        <div className="essentials-fields">
          <TextField label="Brand" value={item.brand} disabled={locked} onSave={(v) => save({ brand: v })} />
          <PriceField cents={item.price_cents} disabled={locked} onSave={(c) => save({ price_cents: c })} toastError={(m) => toast(m, 'error')} />
        </div>
      </section>

      {/* 3. its state: worn, washed; then what you think of it */}
      <WearPanel item={item} disabled={locked}
        onWear={() => act(() => api.wear(id), 'wear', 'Noted: worn today')}
        onUnwear={(day, said) => act(() => api.unwear(id, day), 'wear', said)}
        onLaundry={(state) => act(() => api.setLaundry(id, state), 'laundry', state === 'laundry' ? 'In the laundry' : 'Marked clean')} />

      <Section id={`about-${item.id}`} title="About it" className="detail-about">
        <ChipGroup field="rating" options={vocab.rating} value={item.rating} disabled={locked} labelOf={ratingLabel}
          onChange={(v) => save({ rating: v })} />
        <NotesBox item={item} disabled={locked} onSave={(patch) => save(patch)} />
      </Section>

      {/* 4. how it looks: the description the drawing is made from, fixing it, a shoe's drawings by Claude */}
      <section className="detail-looks" aria-label="How it looks" data-testid="how-it-looks">
        <LookLine item={item} disabled={locked} onPick={openFix} />
        <FixDetails item={item} label={fixLabel(demo)} open={fixing} focus={focus} demo={demo} disabled={locked}
          onOpen={() => openFix(null)} onClose={() => setFixing(false)} onSaved={fixed} onError={failed} />
        <TraceNotice item={item} disabled={locked} onSaved={fixed} onError={failed} />
        <ShoeDrawn item={item} disabled={locked} demo={demo} onSaved={fixed} onError={failed} />
      </section>

      <details className="more detail-fold" data-testid="details-fold">
        <summary>Details</summary>
        <Editing.Provider value={{ editing, setEditing }}>
          <ul className="detail-rows">
            <DetailRow field="color" value={shadeLabel(label('color', item.color), item.shade)} swatch={item.color ? (item.color_hex ?? swatchOf(item.color)) : undefined} disabled={locked}>
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
            {(['location', 'formality', 'season'] as const).map((f) => (
              <DetailRow key={f} field={f} value={label(f, item[f])} disabled={locked}>
                {(done) => <ChipGroup field={f} options={vocab[f]} value={item[f]} disabled={locked}
                  onChange={(v) => { done(); void save({ [f]: v }); }} />}
              </DetailRow>
            ))}
          </ul>
        </Editing.Provider>
      </details>

      <details className="more">
        <summary>Size, material and more</summary>
        <div className="more-body">
          <TextField label="Size" value={item.size} disabled={locked} onSave={(v) => save({ size: v })} />
          <TextField label="Material" value={item.material} disabled={locked} placeholder="e.g. cotton, wool blend" onSave={(v) => save({ material: v })} />
          <TextField label="Date acquired" type="date" value={item.acquired_on} disabled={locked} onSave={(v) => save({ acquired_on: v })} />
          <ChipGroup field="condition" options={vocab.condition} value={item.condition} disabled={locked} onChange={(v) => save({ condition: v })} />
        </div>
      </details>

      {/* 5. the photos last: a shoe's other views, and which of them shows the outside */}
      <ShoePhotos item={item} disabled={locked} onSaved={fixed} onError={failed} />

      <ItemHistory item={item} disabled={locked} onSaved={fixed} onError={failed} />

      <details className="more">
        <summary>{lastFoldTitle(item.status === 'archived', canRetag)}</summary>
        <div className="tag-body">
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
              dropItem(qc, id);
              void touch(qc, 'removeItem', ['items', 'item']);
              toast('Deleted');
              navigate(backTo, { replace: true });   // Back must not return to the page of an item that is gone
            } catch (e) {
              toast((e as Error).message, 'error');
            }
          }} />
        </div>
      </details>
    </article>
  );
}

const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';

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
        <span className="detail-row-label">{title}</span>{' '}
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
      <p>What Nines recorded, for working out what went wrong:</p>
      <pre>{details}</pre>
    </details>
  );
}

function DetailTop({ inPanel, backTo }: { inPanel?: boolean; backTo: string }) {
  if (inPanel) return null;
  return (
    <div className="detail-top">
      <BackLink to={backTo} className="btn btn-ghost back-link"><BackIcon /> Closet</BackLink>
    </div>
  );
}

function Picture({ item, progress, fallbackThumb }: { item: Item; progress: Progress | null; fallbackThumb?: string | null }) {
  const photo = item.photos[0];
  const hasDrawing = !!(item.illustration_url || item.has_illustration);
  const placeholder = drawingPlaceholder(progress, item.category, hasDrawing);
  const views: { key: View; label: string }[] = [];
  // the drawing's place is offered while one is on its way, so it can say so
  if (hasDrawing || drawingOnItsWay(progress)) views.push({ key: 'drawing', label: 'Drawing' });
  if (photo?.cutout_url) views.push({ key: 'cutout', label: 'Cutout' });
  if (photo?.url) views.push({ key: 'photo', label: 'Photo' });
  const drawings = useShowDrawings();
  const preferred: View | undefined = drawings && hasDrawing ? 'drawing' : photo?.cutout_url ? 'cutout' : views[0]?.key;
  const [chosen, setChosen] = useState<View | undefined>(undefined);
  const view = chosen && views.some((v) => v.key === chosen) ? chosen : preferred;
  const alt = item.name || label('category', item.category) || 'Item';
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
    <div className="detail-picture-wrap">
      <div className="detail-picture-main">
        <div className="detail-picture-frame">
          <div className={`detail-picture view-${view ?? 'none'}`}>
            {pic}
            {busy(progress) && <ProgressStrip progress={progress} />}
          </div>
          {missing.length > 0 && <NotDrawn missing={missing} />}
        </div>
        {view === 'drawing' && !placeholder && item.back_url && (
          <figure className="back-view">
            <img src={item.back_url} alt={`${alt}, drawing from the back`} />
            <figcaption>From the back</figcaption>
          </figure>
        )}
        {views.length > 1 && (
          <div className="picture-controls">
            <SegmentedControl label="Picture" small value={view} options={views.map((v) => ({ value: v.key, label: v.label }))} onChange={setChosen} />
          </div>
        )}
      </div>
    </div>
  );
}

/** What the drawing leaves out or shows only roughly: a small mark on the drawing that opens the list. */
function NotDrawn({ missing }: { missing: string[] }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={button} type="button" className="btn btn-ghost not-drawn-open" aria-expanded={open} aria-haspopup="dialog"
        aria-label="Not in the drawing" title="Not in the drawing" onClick={() => setOpen(!open)}>
        <InfoIcon />
      </button>
      {open && (
        <Sheet title="Not in the drawing" popover keep={button} className="not-drawn-sheet" testId="not-drawn" onClose={() => setOpen(false)}>
          <ul className="not-drawn-list">{missing.map((m) => <li key={m}>{m}</li>)}</ul>
        </Sheet>
      )}
    </>
  );
}

function NameField({ value, placeholder, disabled, onSave }: { value: string | null; placeholder: string; disabled: boolean; onSave(v: string | null): void }) {
  const [text, setText] = useFieldText(value ?? '');
  const commit = () => {
    const v = text.trim();
    if (v !== (value ?? '')) onSave(v || null);
  };
  useWhenLeaving(commit);
  // a long name wraps onto more lines rather than running out of sight: the box grows with it
  const box = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el || CSS.supports?.('field-sizing', 'content')) return;
    const fit = () => {
      el.style.height = 'auto';
      el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`;
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, [text]);
  return (
    <span className="name-field">
      <textarea ref={box} aria-label="Name" value={text} placeholder={placeholder} disabled={disabled} maxLength={120} rows={1}
        onChange={(e) => setText(e.target.value.replace(/\s*\n\s*/g, ' '))} onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            e.currentTarget.blur();
          }
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
  /** A short line under the field, read out with it. */
  hint?: string;
  onSave(v: string | null): void;
}

function TextField({ label: text, value, disabled, placeholder, type = 'text', multiline, hint, onSave }: TextFieldProps) {
  const [v, setV] = useFieldText(value ?? '');
  const hintId = useId();
  const commit = () => {
    const t = v.trim();
    if (t !== (value ?? '')) onSave(t || null);
  };
  useWhenLeaving(commit);
  const described = hint ? hintId : undefined;
  const field = (
    <label className="field">
      <span>{text}</span>
      {multiline ? (
        <textarea value={v} rows={3} disabled={disabled} placeholder={placeholder} aria-describedby={described}
          onChange={(e) => setV(e.target.value)} onBlur={commit} />
      ) : (
        <input type={type} value={v} disabled={disabled} placeholder={placeholder} aria-describedby={described}
          onChange={(e) => setV(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
      )}
    </label>
  );
  if (!hint) return field;
  return (
    <div className="field-with-hint">
      {field}
      <p className="hint" id={hintId}>{hint}</p>
    </div>
  );
}

function PriceField({ cents, disabled, onSave, toastError }: { cents: number | null; disabled: boolean; onSave(c: number | null): void; toastError(m: string): void }) {
  const [v, setV] = useFieldText(formatPrice(cents));
  const commit = () => {
    const parsed = parsePrice(v);
    if (parsed === undefined) {
      toastError(PRICE_HINT);
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
        <input inputMode="decimal" value={v} disabled={disabled} onChange={(e) => setV(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
      </span>
    </label>
  );
}

function Actions({ item, disabled, onArchive, onDelete }: { item: Item; disabled: boolean; onArchive(a: boolean): Promise<void>; onDelete(): Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const back = useConfirmFocus(confirming);
  const archived = item.status === 'archived';
  return (
    <div className="detail-actions">
      {!confirming ? (
        <div className="row">
          <button className="btn" disabled={disabled} onClick={() => onArchive(!archived)}>{archived ? 'Unarchive' : 'Archive'}</button>
          <button ref={back} className="btn btn-danger-quiet" disabled={disabled} onClick={() => setConfirming(true)}>Delete</button>
        </div>
      ) : (
        <div className="confirm" role="alertdialog" aria-labelledby="del-q" onKeyDown={confirmKeys(() => setConfirming(false))}>
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
