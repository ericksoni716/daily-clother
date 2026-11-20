import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { ChipGroup } from '../components/ui/Chips';
import { BackLink, confirmKeys, Notice, PHONE, Section, SegmentedControl, Sheet, useConfirmFocus } from '../components/ui';
import { FixDetails, ItemHistory } from '../components/FixDetails';
import { KindPicker } from '../components/KindPicker';
import { RetakeButton } from '../components/RetakeButton';
import { ShoeDrawn } from '../components/ShoeDrawn';
import { ShoePhotos } from '../components/ShoePhotos';
import { TraceNotice } from '../components/ShoeTrace';
import { ProgressStrip } from '../components/Progress';
import { BackIcon, ChevronIcon, HangerIcon, WarnIcon } from '../components/Icons';
import { FIELD_TITLES, formatPrice, label, shadeLabel, measuredColours, parsePrice, ratingLabel, SWATCH, swatchOf, tileCaption, wornWords } from '../labels';
import { SaveLine, useWhenLeaving } from '../leave';
import { navigate, useMediaQuery } from '../router';
import { silhouetteGroups } from '../silhouette';
import { dropItem, itemQuery, itemSaved, touch, useItemProgress, useItemSummary, useVocab, writeSummary } from '../queries';
import { queryKeys, type EditKind } from '../queryKeys';
import { useApp } from '../store';
import { loadGridView, notInDrawing } from '../drawing';
import { busy, drawingOnItsWay, drawingPlaceholder } from '../progress';
import { describedBy, describedHint, detailLines } from '../tagging';
import { kindDrawing, kindLine, type KindGroup } from '../kinds';
import { retakeOffer, retakeSaid } from '../retake';
import { sureText } from '../review';
import type { Item, ItemPatch, PatternColour, Progress } from '../types';
import { localDay, sinceWash, wearDay, wearSummary } from '../wears';

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
  const { toast, offline, profile } = useApp();
  const qc = useQueryClient();
  const vocab = useVocab();
  // The closet's summary of it, shown at once while the full item is read (or when it cannot be, offline).
  const summary = useItemSummary(id);
  const query = useQuery(itemQuery(id));
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
          {away && <Notice as="p">You're offline, so this item can't be changed right now. Its full details show once Closet can be reached again.</Notice>}
          <header className="detail-head">
            <h2 className="detail-title">{summary.name || label('category', summary.category) || 'Item'}</h2>
            <p className="detail-meta">{[label('category', summary.category), label('color', summary.color), label('pattern', summary.pattern), label('location', summary.location)].filter(Boolean).join(' · ')}</p>
          </header>
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
  const groups = silhouetteGroups(item.category);
  const tagText = item.tag_state === 'done' ? describedHint(item.tag_route) : null;
  const failure = progress?.state === 'failed' ? progress : null;
  const lines = detailLines(item.details);
  const seen = item.seen_not_drawn ?? [];
  const canRetag = profile !== 'demo' && item.cutout_state === 'ready' && item.has_photo &&
    (item.tag_state === 'done' || item.tag_state === 'none');
  const fixed = (saved: Item, saidAs: string) => {
    itemSaved(qc, saved);
    toast(saidAs);
  };
  const failed = (message: string) => toast(message, 'error');
  // clothes: a new photo when the background couldn't be removed or the pattern couldn't be measured (one button)
  const offer = retakeOffer(item);
  const retake = offer && (
    <RetakeButton item={item} disabled={locked} said={retakeSaid(item, profile === 'demo')} onError={failed}
      onSaved={fixed} />
  );

  return (
    <article className="detail" aria-label={item.name || 'Item'}>
      <DetailTop inPanel={inPanel} backTo={backTo} />
      {locked && <Notice as="p">You're offline, so this item can't be changed right now.</Notice>}

      <Picture item={item} progress={progress}
        fix={<FixDetails item={item} open={fixing} focus={focus} demo={profile === 'demo'} disabled={locked}
          onOpen={() => {
            setFocus(null);
            setFixing(true);
          }}
          onClose={() => setFixing(false)} onSaved={fixed} onError={failed} />} />
      <TraceNotice item={item} disabled={locked} onSaved={fixed} onError={failed} />
      <ShoePhotos item={item} disabled={locked} onSaved={fixed} onError={failed} />
      <ShoeDrawn item={item} disabled={locked} demo={profile === 'demo'} onSaved={fixed} onError={failed} />

      {item.pattern_state === 'failed' && item.pattern_error && (
        <div className="tag-note pattern-failed" data-testid="pattern-failed">
          <p className="muted">{item.pattern_error}</p>
          {offer === 'pattern' && <div className="row">{retake}</div>}
        </div>
      )}
      {failure?.retry === 'cutout' && (
        <div className="notice notice-warn" data-testid="progress-failed">
          <WarnIcon />
          <div>
            <p><strong>{failure.words}.</strong>{failure.error ? ` ${failure.error}` : ''}</p>
            <FailureDetails item={item} stage="cutout" />
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
          </div>
        </div>
      )}

      <header className="detail-head">
        <h2 className="detail-title">
          <NameField value={item.name} placeholder={label('category', item.category) || 'Name this item'} disabled={locked}
            onSave={(name) => save({ name })} />
        </h2>
        {tileCaption(item.category, item.color) && <p className="detail-meta">{tileCaption(item.category, item.color)}</p>}
        <WornLine item={item} disabled={locked} onPick={(field) => {
          setFixing(true);
          setFocus({ field, at: Date.now() });
        }} />
      </header>

      <WearPanel item={item} disabled={locked}
        onWear={() => act(() => api.wear(id), 'wear', 'Noted: worn today')}
        onUnwear={(day, said) => act(() => api.unwear(id, day), 'wear', said)}
        onLaundry={(state) => act(() => api.setLaundry(id, state), 'laundry', state === 'laundry' ? 'In the laundry' : 'Marked clean')} />

      {failure?.retry === 'describe' && (
        <div className="notice notice-warn" data-testid="progress-failed">
          <WarnIcon />
          <div>
            <p><strong>{failure.words}.</strong>{failure.error ? ` ${failure.error}` : ''}</p>
            <FailureDetails item={item} stage="description" />
            <button className="btn btn-small" disabled={locked} onClick={retag}>Try again</button>
          </div>
        </div>
      )}

      <Section id={`details-${item.id}`} title="Details" className="detail-fields"
        hint={tagText ?? undefined}>
        <Editing.Provider value={{ editing, setEditing }}>
        <ul className="detail-rows">
          <KindRow item={item} groups={vocab.kind_groups} disabled={locked} onSaved={fixed} onError={failed} />
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
          <TextField label="How I wear it" multiline value={item.wear_notes} disabled={locked}
            placeholder="e.g. only with the navy suit; runs warm; for dinners out"
            hint="Claude reads this when it chooses your outfits." onSave={(v) => save({ wear_notes: v })} />
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
          dropItem(qc, id);
          void touch(qc, 'removeItem', ['items', 'item']);
          toast('Deleted');
          navigate(backTo, { replace: true });   // Back must not return to the page of an item that is gone
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
        <span className="detail-row-label">What is it?</span>{' '}
        <span className={`detail-row-value${item.kind ? '' : ' is-empty'}`}>
          {item.kind && (
            <img className="kind-row-pic" src={kindDrawing(item.kind, item.color_hex)} alt="" data-testid="kind-pic" />
          )}
          <span className="kind-row-words">
            <span className="detail-row-text">{line}</span>{' '}
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
      <BackLink to={backTo} className="btn btn-ghost back-link"><BackIcon /> Closet</BackLink>
    </div>
  );
}

function Picture({ item, progress, fallbackThumb, fix }: { item: Item; progress: Progress | null; fallbackThumb?: string | null; fix?: ReactNode }) {
  const photo = item.photos[0];
  const hasDrawing = !!(item.illustration_url || item.has_illustration);
  const placeholder = drawingPlaceholder(progress, item.category, hasDrawing);
  const views: { key: View; label: string }[] = [];
  // the drawing's place is offered while one is on its way, so it can say so
  if (hasDrawing || drawingOnItsWay(progress)) views.push({ key: 'drawing', label: 'Drawing' });
  if (photo?.cutout_url) views.push({ key: 'cutout', label: 'Cutout' });
  if (photo?.url) views.push({ key: 'photo', label: 'Photo' });
  const [liked] = useState(loadGridView);
  const preferred: View | undefined = liked === 'drawings' && hasDrawing ? 'drawing' : photo?.cutout_url ? 'cutout' : views[0]?.key;
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
    <div className={`detail-picture-wrap${missing.length ? ' has-notes' : ''}`}>
      <div className="detail-picture-main">
        <div className={`detail-picture view-${view ?? 'none'}`}>
          {pic}
          {busy(progress) && <ProgressStrip progress={progress} />}
        </div>
        {view === 'drawing' && !placeholder && item.back_url && (
          <figure className="back-view">
            <img src={item.back_url} alt={`${alt}, drawing from the back`} />
            <figcaption>From the back</figcaption>
          </figure>
        )}
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

/** Fresh data may update an untouched field, but must not replace text still being typed. */
function useFieldText(value: string) {
  const [text, setText] = useState(value);
  const previous = useRef(value);
  useEffect(() => {
    const before = previous.current;
    previous.current = value;
    setText((current) => current === before ? value : current);
  }, [value]);
  return [text, setText] as const;
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
/** How it sits on the outfit figure, in a short line under its name ("Relaxed fit · hip length · long sleeves"): each
 * word opens its detail in "Fix the details", where the owner can correct it and the figure is drawn again. */
function WornLine({ item, disabled, onPick }: { item: Item; disabled: boolean; onPick(field: string): void }) {
  const words = wornWords(item.as_worn);
  if (!words.length) return null;
  return (
    <p className="detail-worn" data-testid="worn-line" aria-label="How it is worn">
      {words.map((w, i) => (
        <span key={w.part} className="detail-worn-item">
          {i > 0 && <span className="detail-worn-sep" aria-hidden="true"> · </span>}
          <button type="button" className="btn-link detail-worn-word" disabled={disabled}
            title={`Fix the ${w.text.toLowerCase()} in the details`} onClick={() => onPick(w.field)}>{w.text}</button>
        </span>
      ))}
    </p>
  );
}

function MeasuredColours({ colours }: { colours?: PatternColour[] }) {
  if (!colours?.length) return null;
  const words = `Colours measured from the photo: ${measuredColours(colours)}`;
  return (
    <span className="measured-colours" role="img" aria-label={words} title={words} data-testid="pattern-colours">
      {colours.map((c) => <span key={c.color} className="swatch" style={{ background: c.hex }} />)}
    </span>
  );
}
