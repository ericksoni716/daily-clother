/**
 * The parts of the Wardrobe page about how the closet is used: Your nines (the nine pieces worn most), what is not worn
 * (to archive or keep), one line on what your clothes cost you, and, behind "More numbers", how wears are spread, what
 * the closet is made of and what the clothes cost, year by year and per wear. The page, which reads the answer, is
 * Wardrobe.tsx.
 */
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { api } from '../api';
import { HangerIcon } from '../components/Icons';
import { Card as UiCard, Fold, ItemThumb, SegmentedControl } from '../components/ui';
import { useShowDrawings, type GridView } from '../drawing';
import {
  barWidth, earnedCaption, FIELD_WORDS, forgetKept, groupLabel, keepPiece, keptPieces, loadSavedInsights,
  MAKEUP_FIELDS, makeupHero, ninesWindow, plural, shortDate, spentWords, spreadHero, unwornCaption, windowLabel, wishlistCostWords,
  yearWords, type Counted, type Insights, type MakeupField, type NinesWindow, type PricedPiece, type Spending, type Unworn,
  type UnwornPiece,
} from '../insights';
import { amount } from '../spend';
import { categoryPlural, label } from '../labels';
import { Link } from '../router';
import { useItemEdit } from '../queries';
import { useApp } from '../store';
import type { ItemSummary } from '../types';
import { localDay } from '../wears';
import { TilePicture } from './Closet';
import './Insights.css';

const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';

export const INSIGHTS_OFFLINE = "You're offline, and how your clothes are used was not saved on this device yet. It shows here once Nines on your computer can be reached.";

/** This closet's own copy kept on this device, never another closet's. */
export function savedInsights(profile: string): { data: Insights; savedAt: string } | null {
  const saved = loadSavedInsights(profile);
  return saved ? { data: saved.answer, savedAt: saved.saved_at } : null;
}

/** An item opened from the Wardrobe opens there (beside the page on a computer), with "‹ Wardrobe" to come back. */
const piecePath = (id: string) => `/wardrobe/item/${encodeURIComponent(id)}`;

/**
 * How the closet is used, as sections of the Wardrobe page. `locked`: offline, or showing a copy saved earlier, so
 * nothing can be archived.
 */
export function Usage({ answer, byId, locked }: { answer: Insights; byId: ById; locked: boolean }) {
  const { profile, toast } = useApp();
  const today = localDay();
  const [kept, setKept] = useState(() => keptPieces(profile, today));
  const [archiving, setArchiving] = useState<string | null>(null);
  // pieces archived from here, until the answer is read again without them
  const [gone, setGone] = useState<{ from: Insights | undefined; ids: string[] }>({ from: undefined, ids: [] });
  const saveItem = useItemEdit('item');
  const goneIds = gone.from === answer ? gone.ids : [];
  // drawings or photos, as Settings says ("Show drawings instead of photos")
  const view: GridView = useShowDrawings() ? 'drawings' : 'photos';

  const archive = useCallback(async (id: string) => {
    setArchiving(id);
    try {
      // the item goes into the lists, and the answer is made stale, so it is read again without it
      await saveItem(() => api.patch(id, { status: 'archived' }));
      setGone((g) => ({ from: answer, ids: g.from === answer ? [...g.ids, id] : [id] }));
      toast('Archived. It is kept under Archived in your closet.');
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setArchiving(null);
    }
  }, [saveItem, toast, answer]);

  const keep = useCallback((id: string) => {
    const until = keepPiece(profile, id, today);
    setKept((k) => ({ ...k, [id]: until }));
    toast(`Kept. It is not listed here again until ${shortDate(until)}.`);
  }, [profile, today, toast]);

  const showKept = useCallback(() => {
    forgetKept(profile);
    setKept({});
  }, [profile]);

  const nothing = answer.log.wears === 0;
  const lately = answer.not_worn_lately;
  // after a break from recording, Not worn for a long time says so (once); with too short a record it says nothing here
  const quiet = !lately.enough && lately.items.length === 0 && answer.log.days >= 90;
  return (
    <ViewContext.Provider value={view}>
      {answer.nines && (
        <section className="wardrobe-section insights" aria-labelledby="nines-title">
          <h2 id="nines-title" className="missing-section-title">Your nines</h2>
          <p className="hint nines-hint">The nine pieces you wear most, with how many times you wore each.</p>
          <Nines windows={answer.nines.windows} byId={byId} />
        </section>
      )}
      {!nothing && (
        <section className="wardrobe-section insights" aria-labelledby="unworn-title">
          <h2 id="unworn-title" className="missing-section-title">Not worn</h2>
          <div className="insights-grid">
            <UnwornCard finding={answer.never_worn} testid="never-worn" byId={byId} kept={kept} gone={goneIds} offline={locked}
              archiving={archiving} onArchive={archive} onKeep={keep} onShowKept={showKept} />
            {(lately.items.length > 0 || quiet) && (
              <UnwornCard finding={lately} title={lately.title} testid="not-worn-lately" byId={byId} kept={kept} gone={goneIds} offline={locked}
                archiving={archiving} onArchive={archive} onKeep={keep} onShowKept={showKept} />
            )}
          </div>
        </section>
      )}
      {answer.spending && <Spent spending={answer.spending} byId={byId} />}
      <Fold title="More numbers" lazy className="insights more-numbers" testId="more-numbers">
        <div className="insights-grid">
          <SpreadCard answer={answer} byId={byId} />
          <MakeupCard answer={answer} />
          <CostCard answer={answer} byId={byId} />
        </div>
      </Fold>
    </ViewContext.Provider>
  );
}

type ById = Map<string, ItemSummary>;

/** A finding: a short label, the one figure it leads with (when there is one) and one sentence that says what it means. */
function Card({ title, hero, sentence, testid, wide, children }: {
  /** Left out where the section's heading already says it ("Not worn"), so a heading is never said twice. */
  title?: string; hero: string | null; sentence: string; testid: string; wide?: boolean; children?: ReactNode;
}) {
  const id = `insights-${testid}`;
  return (
    <UiCard as="section" className={`insights-card${wide ? ' is-wide' : ''}`} aria-labelledby={title ? id : undefined}
      aria-label={title ? undefined : sentence} data-testid={testid}>
      {title && <h3 id={id} className="insights-card-title">{title}</h3>}
      {hero && <p className="insights-hero" data-testid="insight-hero">{hero}</p>}
      <p className="insights-sentence">{sentence}</p>
      {children}
    </UiCard>
  );
}

function nameOf(item: ItemSummary | undefined): string {
  return item?.name || label('category', item?.category) || 'Item';
}

const ViewContext = createContext<GridView>('photos');

function Picture({ item }: { item: ItemSummary | undefined }) {
  const view = useContext(ViewContext);
  if (!item) return <div className="pic-placeholder" role="img" aria-label={nameOf(item)}><HangerIcon /></div>;
  return <TilePicture item={item} view={view} />;
}

/** A small picture that opens the item, with its name and a caption. */
function Piece({ id, byId, caption, title, children }: { id: string; byId: ById; caption: string; title?: string; children?: ReactNode }) {
  const item = byId.get(id);
  return (
    <li className="insights-piece" data-testid="insight-piece">
      <Link to={piecePath(id)} className="insights-piece-link" title={title}>
        <ItemThumb className="insights-piece-pic" picture={<Picture item={item} />} />
        <span className="insights-piece-name">{nameOf(item)}</span>
        <span className="insights-piece-caption">{caption}</span>
      </Link>
      {children}
    </li>
  );
}

function CostRow({ heading, detail, pieces, currency, byId }: {
  heading: string; detail?: ReactNode; pieces: PricedPiece[]; currency: string; byId: ById;
}) {
  if (!pieces.length) return null;
  return (
    <>
      <h4 className="chip-group-title">{heading}</h4>
      {detail}
      <ul className="insights-pieces">
        {pieces.map((p) => <Piece key={p.id} id={p.id} byId={byId} caption={earnedCaption(p, currency)} />)}
      </ul>
    </>
  );
}

/**
 * What your clothes cost you, in full: what was spent each year, the closet's cost per wear, the pieces that have
 * earned their price and those that have not yet (folded until asked for), and what the wishlist would cost. Worth
 * having, not what to judge every piece by (the owner, 16 November), so it is the last card of More numbers, with no
 * figure leading it. The one line in view is `Spent`.
 */
function CostCard({ answer, byId }: { answer: Insights; byId: ById }) {
  const f = answer.cost_per_wear;
  const s = answer.spending;
  const years = s ? yearWords(s) : [];
  const wishlist = s ? wishlistCostWords(s.wishlist) : null;
  const best = s?.earned[0];
  return (
    <Card title="What your clothes cost you" hero={null} sentence={f.sentence} testid="cost-per-wear">
      {years.length > 0 && (
        <ul className="insights-years" data-testid="cost-years">{years.map((y) => <li key={y}>{y}</li>)}</ul>
      )}
      {s && (s.earned.length > 0 || s.not_earned.length > 0) && (
        <details className="more insights-cost-pieces" data-testid="cost-pieces">
          <summary>Which pieces have earned their price</summary>
          <CostRow heading="Earned their price" pieces={s.earned} currency={s.currency} byId={byId}
            detail={best && <p className="insights-detail muted small" data-testid="cost-best">
              Your {nameOf(byId.get(best.id))} cost {amount(best.per_wear_cents ?? 0, s.currency, true)} a wear over {plural(best.wears, 'wear')}.
            </p>} />
          <CostRow heading="Not yet: a price, and few or no wears" pieces={s.not_earned} currency={s.currency} byId={byId} />
        </details>
      )}
      {wishlist && <p className="insights-detail" data-testid="cost-wishlist">{wishlist}</p>}
    </Card>
  );
}

/** The one line in view about what your clothes cost: this year's spending, or how many pieces have no price yet, with a
 * link to the piece to start with (the one you wear most), where the price and the date bought are filled in. */
function Spent({ spending, byId }: { spending: Spending; byId: ById }) {
  const words = spentWords(spending);
  if (!words) return null;
  const first = spending.first_missing;
  return (
    <p className="wardrobe-spent" data-testid="spent">
      {words.text}
      {words.fill && first && byId.has(first) && (
        <>
          {' '}
          <Link to={piecePath(first)} className="wardrobe-spent-link">
            {words.fill === 'price' ? 'Add one to the piece you wear most.' : 'Add the date to the piece you wear most.'}
          </Link>
        </>
      )}
    </p>
  );
}

/**
 * Your nines: the nine pieces worn most over the chosen time, as a three-by-three square of their pictures (photos or
 * drawings, as Settings says), each with its number of wears, each opening the piece. With fewer than nine it shows
 * what there is and says so in one line.
 */
function Nines({ windows, byId }: { windows: NinesWindow[]; byId: ById }) {
  const [index, setIndex] = useState(() => ninesWindow(windows));
  const w = windows[Math.min(index, windows.length - 1)];
  return (
    <div className="nines" data-testid="nines">
      <SegmentedControl label="Over" small className="insights-windows" value={String(index)}
        options={windows.map((x, i) => ({ value: String(i), label: windowLabel(x.days) }))}
        onChange={(i) => setIndex(Number(i))} />
      {w.items.length > 0 && (
        <ol className="nines-grid" aria-label={`Worn most, ${windowLabel(w.days).toLowerCase()}`}>
          {w.items.map((p) => (
            <li key={p.id}>
              <Link to={piecePath(p.id)} className="nines-tile" data-testid="nine" aria-label={`${nameOf(byId.get(p.id))}, ${plural(p.wears, 'wear')}`}>
                <ItemThumb className="nines-pic" picture={<Picture item={byId.get(p.id)} />} />
                <span className="nines-count">{p.wears}</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
      {w.sentence && <p className="insights-sentence nines-line">{w.sentence}</p>}
    </div>
  );
}

interface UnwornProps {
  finding: Unworn;
  title?: string;
  testid: string;
  byId: ById;
  kept: Record<string, string>;
  gone: string[];
  offline: boolean;
  archiving: string | null;
  onArchive(id: string): void;
  onKeep(id: string): void;
  onShowKept(): void;
}

function UnwornCard({ finding, title, testid, byId, kept, gone, offline, archiving, onArchive, onKeep, onShowKept }: UnwornProps) {
  const listed = finding.items.filter((p) => !gone.includes(p.id));
  const shown = listed.filter((p) => !kept[p.id]);
  const hidden = listed.length - shown.length;
  return (
    <Card title={title} hero={null} sentence={finding.sentence} testid={testid} wide>
      {shown.length > 0 && (
        <ul className="insights-pieces">
          {shown.map((p: UnwornPiece) => (
            <Piece key={p.id} id={p.id} byId={byId} caption={unwornCaption(p)} title={p.sentence}>
              <div className="insights-piece-actions">
                <button className="btn btn-small" disabled={offline || archiving !== null} title={offline ? OFFLINE_TITLE : undefined}
                  aria-label={`Archive ${nameOf(byId.get(p.id))}`} onClick={() => onArchive(p.id)}>
                  {archiving === p.id ? 'Archiving…' : 'Archive'}
                </button>
                <button className="btn btn-small btn-ghost" aria-label={`Keep ${nameOf(byId.get(p.id))}`} onClick={() => onKeep(p.id)}>Keep</button>
              </div>
            </Piece>
          ))}
        </ul>
      )}
      {hidden > 0 && (
        <p className="muted insights-kept">
          {plural(hidden, 'piece')} you chose to keep {hidden === 1 ? 'is' : 'are'} not shown (remembered on this device).{' '}
          <button className="btn btn-link" onClick={onShowKept}>Show again</button>
        </p>
      )}
    </Card>
  );
}

function Bars({ rows, byId }: { rows: Counted[]; byId: ById }) {
  const max = Math.max(0, ...rows.map((r) => r.wears));
  return (
    <ul className="insights-bars">
      {rows.map((r) => (
        <li key={r.id}>
          <Link to={piecePath(r.id)} className="insights-bar-row">
            <ItemThumb className="insights-bar-pic" picture={<Picture item={byId.get(r.id)} />} />
            <span className="insights-bar-text">
              <span className="insights-bar-name">{nameOf(byId.get(r.id))}</span>
              <span className="insights-bar" aria-hidden="true"><span style={{ width: `${barWidth(r.wears, max)}%` }} /></span>
            </span>
            <span className="insights-bar-count">{plural(r.wears, 'wear')}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function SpreadCard({ answer, byId }: { answer: Insights; byId: ById }) {
  const f = answer.spread;
  return (
    <Card title={f.title} hero={spreadHero(f)} sentence={f.sentence} testid="spread">
      {f.categories.map((c) => (
        <details key={c.category} className="insights-spread" open={c.kind === 'few'}>
          <summary>
            <span className="insights-spread-name">{categoryPlural(c.category)}</span>
            <span className={`insights-tag${c.kind === 'few' ? ' is-few' : ''}`}>{c.kind === 'few' ? 'A few do the work' : 'Fairly even'}</span>
          </summary>
          <p className="insights-detail">{c.sentence}</p>
          <Bars rows={c.items} byId={byId} />
        </details>
      ))}
    </Card>
  );
}

function MakeupCard({ answer }: { answer: Insights }) {
  const f = answer.makeup;
  const [field, setField] = useState<MakeupField>('category');
  const groups = f.by[field] ?? [];
  const max = Math.max(0, ...groups.map((g) => g.count));
  return (
    <Card title={f.title} hero={makeupHero(f)} sentence={f.sentence} testid="makeup">
      {f.pieces > 0 && (
        <>
          <SegmentedControl label="Count by" small className="insights-windows" value={field}
            options={MAKEUP_FIELDS.map((k) => ({ value: k, label: FIELD_WORDS[k] }))} onChange={setField} />
          <ul className="insights-bars">
            {groups.map((g) => (
              <li key={g.value ?? ''} className="insights-bar-row is-static">
                <span className="insights-bar-text">
                  <span className="insights-bar-name">{groupLabel(field, g.value)}</span>
                  <span className="insights-bar" aria-hidden="true">
                    <span className="is-all" style={{ width: `${barWidth(g.count, max)}%` }} />
                    {f.enough && <span className="is-worn" style={{ width: `${barWidth(g.worn, max)}%` }} />}
                  </span>
                </span>
                <span className="insights-bar-count">
                  {f.enough ? `${g.worn} of ${g.count} worn` : plural(g.count, 'piece')}
                </span>
              </li>
            ))}
          </ul>
          {f.enough && <p className="muted insights-key"><span className="insights-swatch" /> worn in the last {f.days} days</p>}
        </>
      )}
    </Card>
  );
}
