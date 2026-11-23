import { useQuery, useQueryClient } from '@tanstack/react-query';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CloseIcon, DrawingIcon, FilterIcon, HangerIcon, ImagesIcon, SearchIcon } from '../components/Icons';
import { StepMark } from '../components/Progress';
import { WorkingLine } from '../components/WorkingLine';
import { Button, buttonClass, EmptyState, Failed, PageHeader, SegmentedControl, Sheet } from '../components/ui';
import { gridViewOf, smallPicture, useShowDrawings, type GridView, type MomentView } from '../drawing';
import { setLaundryMany } from '../laundry';
import { groupsIn, groupTitle, kindsOf, type KindGroup } from '../kinds';
import { categoryPlural, label, tileCaption } from '../labels';
import { itemPath, Link, navigate } from '../router';
import { progressOf } from '../progress';
import { itemSaved, itemsQuery, progressQuery, reviewQuery, useVocab } from '../queries';
import { useApp } from '../store';
import type { ItemSummary, Laundry, Progress } from '../types';
import { ItemDetail } from './ItemDetail';
import { AwayMark, AwayView } from '../components/AwayView';
import { awayPart } from '../away';

interface Props {
  status: 'active' | 'archived';
  selectedId: string | null;
  wide: boolean;
  /** How many pieces wait in the review queue (null until known). */
  toReview?: number | null;
}

/** The search and filters, kept while the app is open: on a phone the item page replaces the closet, and coming
 * back from it should find the list as it was left. Kept per closet (demo or real) and per In use / Archived. */
interface Filters { category: string | null; group: string | null; kind: string | null; query: string; laundry: Laundry | null; check: boolean; away: boolean }
const NO_FILTERS: Filters = { category: null, group: null, kind: null, query: '', laundry: null, check: false, away: false };
const filterMemory = new Map<string, Filters>();
/** The Photos / Drawings switch, used for the moment: kept while the app is open (not on the device), and set aside
 * once the setting changes (`gridViewOf`). */
let gridMoment: MomentView | null = null;

export function ClosetScreen({ status, selectedId, wide, toReview = null }: Props) {
  const { profile, offline, toast } = useApp();
  const qc = useQueryClient();
  // asked for again each time the closet opens (what is kept shows at once meanwhile): it is the main screen
  const items = useQuery({ ...itemsQuery(status), refetchOnMount: 'always' });
  // the work under way is asked again too (it may have been started elsewhere); the closet's provider polls it after
  const work = useQuery({ ...progressQuery(), refetchOnMount: 'always', enabled: !offline }).data ?? null;
  const vocab = useVocab();
  const [washing, setWashing] = useState(false);
  const list = items.data ?? null;
  const loadError = !!items.error;
  const memoryKey = `${profile}:${status}`;
  const kept = filterMemory.get(memoryKey) ?? NO_FILTERS;
  const [category, setCategory] = useState<string | null>(kept.category);
  const [group, setGroup] = useState<string | null>(kept.group);
  const [kind, setKind] = useState<string | null>(kept.kind);
  const [query, setQuery] = useState(kept.query);
  const [laundry, setLaundry] = useState<Laundry | null>(kept.laundry);
  // "Needs a check": the pieces added and not checked yet, and those with a detail Claude was unsure of (the review
  // queue, read once for the count too)
  const [check, setCheck] = useState(kept.check);
  // "Away": the pieces at the cleaner's, at the tailor's or lent out (`AwayView`); those brought back there stay listed
  const [away, setAwayOn] = useState(kept.away);
  const [returned, setReturned] = useState<Set<string>>(() => new Set());
  const setAway = (on: boolean) => { setAwayOn(on); setReturned(new Set()); };
  useEffect(() => {
    filterMemory.set(memoryKey, { category, group, kind, query, laundry, check, away });
  }, [memoryKey, category, group, kind, query, laundry, check, away]);
  const review = useQuery({ ...reviewQuery(), enabled: !offline && status === 'active' }).data;
  const toCheck = useMemo(() => new Set((review?.items ?? []).map((i) => i.id)), [review]);
  const showDrawings = useShowDrawings();
  const [moment, setMoment] = useState(gridMoment);
  const gridView = gridViewOf(showDrawings, moment);
  const [filtering, setFiltering] = useState(false);
  const [panelTop, setPanelTop] = useState(0);
  const filterButton = useRef<HTMLButtonElement>(null);
  const layout = useRef<HTMLDivElement>(null);

  const categories = useMemo(() => {
    const seen = new Map<string, number>();
    for (const it of list ?? []) if (it.category) seen.set(it.category, (seen.get(it.category) ?? 0) + 1);
    return [...seen.keys()].sort((a, b) => categoryPlural(a).localeCompare(categoryPlural(b)));
  }, [list]);

  const activeCategory = category && categories.includes(category) ? category : null;
  const groups = useMemo(() => groupsIn(list ?? [], vocab?.kind_groups), [list, vocab]);
  const activeGroup = group && groups.some((g) => g.id === group) ? group : null;
  const kinds = useMemo(() => kindsOf(list ?? [], activeGroup), [list, activeGroup]);
  const activeKind = kinds.find((k) => k.id === kind) ?? null;
  const activeLaundry = status === 'active' ? laundry : null;
  const activeCheck = status === 'active' && check && !offline;
  const activeAway = status === 'active' && away;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (list ?? []).filter((it) => {
      if (activeCategory && it.category !== activeCategory) return false;
      if (activeGroup && it.group !== activeGroup) return false;
      if (activeKind && it.kind !== activeKind.id) return false;
      if (activeLaundry && (it.laundry ?? 'clean') !== activeLaundry) return false;
      if (activeCheck && !toCheck.has(it.id)) return false;
      if (activeAway && !it.away && !returned.has(it.id)) return false;
      if (!q) return true;
      const hay = [it.name, label('category', it.category), label('color', it.color), label('pattern', it.pattern), it.category, it.color,
        it.kind_name, groupTitle(vocab?.kind_groups, it.group)]
        .filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [list, activeCategory, activeGroup, activeKind, activeLaundry, activeCheck, activeAway, returned, toCheck, query, vocab]);

  const empty = list !== null && list.length === 0;
  const title = status === 'archived' ? 'Archived' : profile === 'demo' ? 'Demo closet' : 'Your closet';
  const filters = (activeCategory ? 1 : 0) + (activeGroup ? 1 : 0) + (activeKind ? 1 : 0) + (activeLaundry ? 1 : 0) +
    (activeCheck ? 1 : 0) + (activeAway ? 1 : 0) + (status === 'archived' ? 1 : 0);
  // a piece away is said under away, not under the laundry (it is not in the basket at home)
  const inLaundry = useMemo(() => (list ?? []).filter((it) => it.laundry === 'laundry' && !it.away), [list]);
  const awayNow = useMemo(() => (list ?? []).filter((it) => it.away), [list]);
  const allClean = (pieces: ItemSummary[]) => {
    setWashing(true);
    void setLaundryMany(pieces.map((it) => it.id), 'clean', (item) => itemSaved(qc, item, 'laundry'))
      .then((failed) => toast(failed ? `${failed} could not be marked clean. Try again.` : `${pieces.length === 1 ? 'Marked' : `All ${pieces.length} marked`} clean`, failed ? 'error' : 'ok'))
      .finally(() => setWashing(false));
  };
  const panel = wide && selectedId !== null;

  // The panel scrolls with the page, so it opens level with where the owner is looking, not at the top of the grid.
  const choose = useCallback(() => {
    if (!wide || !layout.current) return;
    setPanelTop(Math.max(0, Math.round(16 - layout.current.getBoundingClientRect().top)));
  }, [wide]);

  const grid = (
    <section className="closet-main" aria-labelledby="closet-title">
      <PageHeader title={title} titleId="closet-title" countTestId="item-count"
        count={list && !empty && (shown.length === list.length ? `${list.length} ${list.length === 1 ? 'item' : 'items'}` : `${shown.length} of ${list.length}`)} />

      {status === 'active' && list && (
        <StatusLine toCheck={offline ? 0 : toReview ?? 0} inLaundry={inLaundry} checking={activeCheck} washing={activeLaundry === 'laundry'}
          busy={washing} offline={offline} onCheck={() => setCheck(!activeCheck)}
          onLaundry={() => setLaundry(activeLaundry === 'laundry' ? null : 'laundry')} onAllClean={allClean}
          away={awayNow} awayOn={activeAway} onAway={() => setAway(!activeAway)} />
      )}
      {status === 'active' && <WorkingLine />}

      {list === null && !loadError && <div className="grid grid-skeleton" aria-hidden="true">{Array.from({ length: 6 }, (_, i) => <div key={i} className="tile-skeleton" />)}</div>}
      <Failed query={items} what={status === 'archived' ? 'what you archived' : 'your closet'} />

      {list ? (
        <>
          <div className="closet-toolbar">
            {list && !empty && (
              <label className="search">
                <SearchIcon />
                <span className="visually-hidden">Search your clothes</span>
                <input type="search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} />
              </label>
            )}
            <div className="filter-wrap">
              <button ref={filterButton} type="button" className={`btn filter-button${filters ? ' has-filters' : ''}`} aria-expanded={filtering}
                aria-haspopup="dialog" onClick={() => setFiltering((f) => !f)}>
                <FilterIcon /><span className="filter-text">Filter</span>
                {/* heard as "Filter, 1 on": the count is part of the name, as it is seen */}
                {filters > 0 && <><span className="visually-hidden">, </span><span className="filter-count">{filters}</span><span className="visually-hidden"> on</span></>}
              </button>
              {filtering && (
                <Sheet title="Filter" popover keep={filterButton} className="filter-sheet" onClose={() => setFiltering(false)}>
                  <FilterChoices status={status} categories={categories} category={activeCategory} laundry={activeLaundry}
                    away={activeAway} onAway={setAway}
                    groups={groups} group={activeGroup} kinds={kinds} kind={activeKind?.id ?? null}
                    onCategory={setCategory} onLaundry={setLaundry} onGroup={(g) => { setGroup(g); setKind(null); }} onKind={setKind} />
                </Sheet>
              )}
            </div>
            {list && !empty && (
              <SegmentedControl label="Show" className="grid-view" value={gridView}
                options={[
                  { value: 'photos', label: <><ImagesIcon /><span className="seg-text">Photos</span></> },
                  { value: 'drawings', label: <><DrawingIcon /><span className="seg-text">Drawings</span></> },
                ]}
                onChange={(value) => { gridMoment = { view: value, setting: showDrawings }; setMoment(gridMoment); }} />
            )}
          </div>
          {filters > 0 && (
            <ul className="active-filters" aria-label="Filters on">
              {status === 'archived' && (
                <li><Link to="/" className="chip chip-remove" aria-label="Remove filter: Archived">Archived<CloseIcon /></Link></li>
              )}
              {activeCategory && (
                <li><button type="button" className="chip chip-remove" aria-label={`Remove filter: ${categoryPlural(activeCategory)}`}
                  onClick={() => setCategory(null)}>{categoryPlural(activeCategory)}<CloseIcon /></button></li>
              )}
              {activeGroup && (
                <li><button type="button" className="chip chip-remove" aria-label={`Remove filter: ${groupTitle(groups, activeGroup)}`}
                  onClick={() => { setGroup(null); setKind(null); }}>{groupTitle(groups, activeGroup)}<CloseIcon /></button></li>
              )}
              {activeKind && (
                <li><button type="button" className="chip chip-remove" aria-label={`Remove filter: ${activeKind.name}`}
                  onClick={() => setKind(null)}>{activeKind.name}<CloseIcon /></button></li>
              )}
              {activeLaundry && (
                <li><button type="button" className="chip chip-remove" aria-label={`Remove filter: ${LAUNDRY[activeLaundry]}`}
                  onClick={() => setLaundry(null)}>{LAUNDRY[activeLaundry]}<CloseIcon /></button></li>
              )}
              {activeCheck && (
                <li><button type="button" className="chip chip-remove" aria-label={`Remove filter: ${NEEDS_CHECK}`}
                  onClick={() => setCheck(false)}>{NEEDS_CHECK}<CloseIcon /></button></li>
              )}
              {activeAway && (
                <li><button type="button" className="chip chip-remove" aria-label={`Remove filter: ${AWAY}`}
                  onClick={() => setAway(false)}>{AWAY}<CloseIcon /></button></li>
              )}
            </ul>
          )}
        </>
      ) : null}

      {empty && status === 'active' && <EmptyCloset demo={profile === 'demo'} />}
      {empty && status === 'archived' && (
        <EmptyState title="Nothing archived" body="Clothes you archive (given away, stored for good) are kept here, out of the way." />
      )}

      {list && !empty && (
        shown.length === 0 ? (
          <div className="empty"><p className="muted">{activeCheck && toCheck.size === 0 ? 'Nothing needs a check now.'
            : activeAway && awayNow.length === 0 ? 'Everything is in your closet.' : 'Nothing matches. Try another word or filter.'}</p></div>
        ) : activeAway ? (
          <AwayView pieces={shown} returned={returned} offline={offline} saved={(item) => itemSaved(qc, item, 'away')}
            failed={(m) => toast(m, 'error')}
            onReturned={(id, back) => setReturned((r) => { const n = new Set(r); if (back) n.add(id); else n.delete(id); return n; })} />
        ) : (
          <ul className="grid" aria-label="Clothes">
            {shown.map((it) => (
              <li key={it.id}><Tile item={it} status={status} selected={it.id === selectedId} progress={progressOf(it, work)} view={gridView} onChoose={choose} /></li>
            ))}
          </ul>
        )
      )}
    </section>
  );

  return (
    <div ref={layout} className={`closet-layout${panel ? ' has-panel' : ''}`}>
      {grid}
      {panel && (
        <aside className="detail-panel closet-panel" aria-label="Item details" style={{ marginTop: panelTop }}>
          <ItemDetail key={selectedId} id={selectedId} status={status} inPanel />
        </aside>
      )}
    </div>
  );
}

const LAUNDRY: Record<Laundry, string> = { clean: 'Clean', laundry: 'In the laundry' };

const NEEDS_CHECK = 'Needs a check';
const AWAY = 'Away';

/**
 * One line over the grid for what wants seeing to: how many pieces need a quick check and how many are in the
 * laundry. Each part shows only those pieces; then the first offers to check them one at a time (the review) and the
 * second to mark them all clean.
 */
function StatusLine({ toCheck, inLaundry, checking, washing, busy, offline, onCheck, onLaundry, onAllClean, away, awayOn, onAway }: {
  toCheck: number; inLaundry: ItemSummary[]; checking: boolean; washing: boolean; busy: boolean; offline: boolean;
  onCheck(): void; onLaundry(): void; onAllClean(pieces: ItemSummary[]): void;
  away: ItemSummary[]; awayOn: boolean; onAway(): void;
}) {
  const n = inLaundry.length;
  if (!toCheck && !n && !checking && !away.length && !awayOn) return null;
  return (
    <div className="closet-status" data-testid="closet-status">
      <p className="closet-status-line">
        {(toCheck > 0 || checking) && (
          <button type="button" className={`btn btn-link closet-status-part${checking ? ' is-on' : ''}`} aria-pressed={checking}
            data-testid="to-check" onClick={onCheck}>
            {toCheck} to check
          </button>
        )}
        {(toCheck > 0 || checking) && n > 0 && <span aria-hidden="true"> · </span>}
        {n > 0 && (
          <button type="button" className={`btn btn-link closet-status-part${washing ? ' is-on' : ''}`} aria-pressed={washing}
            data-testid="in-laundry" onClick={onLaundry}>
            {n} in the laundry
          </button>
        )}
        {(away.length > 0 || awayOn) && (
          <span className={`closet-status-group${toCheck > 0 || checking || n > 0 ? ' is-own-line' : ''}`}>
            {(toCheck > 0 || checking || n > 0) && <span className="closet-status-dot" aria-hidden="true"> · </span>}
            <button type="button" className={`btn btn-link closet-status-part${awayOn ? ' is-on' : ''}`} aria-pressed={awayOn}
              data-testid="away" onClick={onAway}>
              {awayPart(away)}
            </button>
          </span>
        )}
      </p>
      {checking && toCheck > 0 && (
        <p className="closet-status-next" data-testid="review-notice">
          <span className="muted">Claude wasn't sure of a detail on {toCheck === 1 ? 'this piece' : 'these'}.</span>
          <Link to="/review" className={buttonClass({ small: true })}>Check them one at a time</Link>
        </p>
      )}
      {washing && n > 0 && (
        <p className="closet-status-next" data-testid="laundry-notice">
          <span className="muted">{n === 1 ? 'This piece is' : `These ${n} pieces are`} in the laundry.</span>
          <Button small disabled={busy || offline} title={offline ? "You're offline" : undefined} onClick={() => onAllClean(inLaundry)}>
            {busy ? 'Marking clean…' : 'All clean'}
          </Button>
        </p>
      )}
    </div>
  );
}

function FilterChoices({ status, categories, category, laundry, away, groups, group, kinds, kind, onCategory, onLaundry, onAway, onGroup, onKind }: {
  status: 'active' | 'archived';
  away: boolean;
  onAway(on: boolean): void;
  categories: string[];
  category: string | null;
  laundry: Laundry | null;
  /** the groups and the kinds (in the chosen group) the closet's items are */
  groups: KindGroup[];
  group: string | null;
  kinds: { id: string; name: string }[];
  kind: string | null;
  onCategory(c: string | null): void;
  onLaundry(l: Laundry | null): void;
  onGroup(g: string | null): void;
  onKind(k: string | null): void;
}) {
  return (
    <div className="filter-choices">
      <div className="filter-group">
        <h3 className="chip-group-title">Which clothes</h3>
        <SegmentedControl label="Which clothes" small value={status}
          options={[{ value: 'active', label: 'In use', to: '/' }, { value: 'archived', label: 'Archived', to: '/archived' }]} />
      </div>
      {categories.length > 1 && (
        <div className="filter-group">
          <h3 className="chip-group-title" id="filter-category">Category</h3>
          <div className="chips" role="group" aria-label="Filter by category">
            <button type="button" className={`chip${!category ? ' is-on' : ''}`} aria-pressed={!category} onClick={() => onCategory(null)}>All</button>
            {categories.map((c) => (
              <button key={c} type="button" className={`chip${category === c ? ' is-on' : ''}`} aria-pressed={category === c}
                onClick={() => onCategory(category === c ? null : c)}>{categoryPlural(c)}</button>
            ))}
          </div>
        </div>
      )}
      {groups.length > 1 && (
        <div className="filter-group">
          <h3 className="chip-group-title">Group</h3>
          <div className="chips" role="group" aria-label="Filter by group">
            {groups.map((g) => (
              <button key={g.id} type="button" className={`chip${group === g.id ? ' is-on' : ''}`} aria-pressed={group === g.id}
                onClick={() => onGroup(group === g.id ? null : g.id)}>{g.title}</button>
            ))}
          </div>
        </div>
      )}
      {kinds.length > 0 && (
        <div className="filter-group">
          <h3 className="chip-group-title">Kind</h3>
          <div className="chips" role="group" aria-label="Filter by kind">
            {kinds.map((k) => (
              <button key={k.id} type="button" className={`chip${kind === k.id ? ' is-on' : ''}`} aria-pressed={kind === k.id}
                onClick={() => onKind(kind === k.id ? null : k.id)}>{k.name}</button>
            ))}
          </div>
        </div>
      )}
      {status === 'active' && (
        <div className="filter-group">
          <h3 className="chip-group-title">Laundry and away</h3>
          <div className="chips" role="group" aria-label="Filter by laundry">
            {(['clean', 'laundry'] as const).map((value) => (
              <button key={value} type="button" className={`chip${laundry === value ? ' is-on' : ''}`} aria-pressed={laundry === value}
                onClick={() => onLaundry(laundry === value ? null : value)}>{LAUNDRY[value]}</button>
            ))}
            <button type="button" className={`chip${away ? ' is-on' : ''}`} aria-pressed={away} onClick={() => onAway(!away)}>{AWAY}</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** One tile of the grid. Memoised: a poll or a save that changes one item draws that item's tile only. `progress` is
 * how far the work on it has got (progress.ts), shown as the step's small mark. */
const Tile = memo(function Tile({ item, status, selected, progress, view, onChoose }: {
  item: ItemSummary; status: 'active' | 'archived'; selected: boolean; progress: Progress | null; view: GridView; onChoose(): void;
}) {
  const name = item.name || label('category', item.category) || 'New item';
  const caption = tileCaption(item.category, item.color);
  return (
    <Link to={itemPath(item.id, status)} className={`tile${selected ? ' is-selected' : ''}`} aria-current={selected ? 'true' : undefined}
      data-testid="tile" onClick={onChoose}>
      <div className="tile-card">
        <TilePicture item={item} view={view} />
        {progress && <StepMark progress={progress} />}
        {item.laundry === 'laundry' && <span className="tile-mark" data-testid="laundry-mark">In the laundry</span>}
        <AwayMark item={item} />
      </div>
      <span className="tile-name">{name}</span>
      <span className="tile-caption">{caption || ' '}</span>
    </Link>
  );
});

/** The picture the closet grid shows for an item (also used by trips and the Wardrobe's lists of pieces): its drawing
 * when `view` is drawings and it has one, else the cutout, the photo or the drawing (`smallPicture`). */
export function TilePicture({ item, view }: { item: ItemSummary; view: GridView }) {
  const alt = item.name || label('category', item.category) || 'Item';
  const shown = smallPicture(item, view === 'drawings', true);
  if (shown === 'drawing') return <img className="pic-illustration" src={item.illustration_url!} alt={view === 'drawings' ? `${alt}, drawing` : alt} loading="lazy" />;
  if (shown === 'none') return <div className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></div>;
  return <img className={shown === 'cutout' ? 'pic-cutout' : 'pic-photo'} src={item.thumb_url!} alt={alt} loading="lazy" />;
}

function EmptyCloset({ demo }: { demo: boolean }) {
  const { switchProfile, toast, offline } = useApp();
  return (
    <EmptyState big icon={<HangerIcon />} title={demo ? 'The demo closet is empty' : 'Your closet is empty'}
      body="Take a photo of a piece of clothing and Nines will cut it out and keep it here.">
      <div className="stack stack-narrow">
        <Button variant="primary" block disabled={offline} onClick={() => navigate('/add')}>Add your first item</Button>
        {!demo && (
          <Button variant="link" disabled={offline} onClick={() => switchProfile('demo').catch((e) => toast((e as Error).message, 'error'))}>
            or look around the demo closet
          </Button>
        )}
      </div>
    </EmptyState>
  );
}
