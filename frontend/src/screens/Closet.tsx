import { useQuery, useQueryClient } from '@tanstack/react-query';
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { CloseIcon, FilterIcon, HangerIcon, SearchIcon } from '../components/Icons';
import { StepMark } from '../components/Progress';
import { WorkingLine } from '../components/WorkingLine';
import { Button, buttonClass, EmptyState, Failed, PageHeader, SegmentedControl, Sheet } from '../components/ui';
import { gridViewOf, smallPicture, useShowDrawings, type GridView, type MomentView } from '../drawing';
import { cleanAll, putBack, type Cleaned } from '../laundry';
import { groupTitle, type KindGroup } from '../kinds';
import { categoryPlural, label, tileCaption } from '../labels';
import { goBack, itemPath, Link, navigate } from '../router';
import { ANY, chooseWhat, columnsFor, emptySentence, isWhat, laundryNotice, laundryPart, matchesSearch, searchedText, whatChoices, whatIn, whatName, type Choice, type What } from '../closet';
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
interface Filters { what: What; query: string; laundry: Laundry | null; check: boolean; away: boolean }
const NO_FILTERS: Filters = { what: ANY, query: '', laundry: null, check: false, away: false };
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
  // what a piece is: a group, then a category in it, then a kind (`closet.ts`, "What")
  const [what, setWhat] = useState<What>(kept.what);
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
    filterMemory.set(memoryKey, { what, query, laundry, check, away });
  }, [memoryKey, what, query, laundry, check, away]);
  const review = useQuery({ ...reviewQuery(), enabled: !offline && status === 'active' }).data;
  const toCheck = useMemo(() => new Set((review?.items ?? []).map((i) => i.id)), [review]);
  const showDrawings = useShowDrawings();
  const [moment, setMoment] = useState(gridMoment);
  const gridView = gridViewOf(showDrawings, moment);
  const [filtering, setFiltering] = useState(false);
  const [panelTop, setPanelTop] = useState(0);
  const filterButton = useRef<HTMLButtonElement>(null);
  const layout = useRef<HTMLDivElement>(null);
  const aside = useRef<HTMLElement>(null);
  const [layoutWidth, setLayoutWidth] = useState(0);

  const activeWhat = useMemo(() => whatIn(list ?? [], vocab?.kind_groups, what), [list, vocab, what]);
  const whatOn = activeWhat.group !== null;
  const choices = useMemo(() => whatChoices(list ?? [], vocab?.kind_groups, activeWhat), [list, vocab, activeWhat]);
  const activeLaundry = status === 'active' ? laundry : null;
  const activeCheck = status === 'active' && check && !offline;
  const activeAway = status === 'active' && away;

  const shown = useMemo(() => {
    return (list ?? []).filter((it) => {
      if (!isWhat(it, activeWhat)) return false;
      if (activeLaundry && (it.laundry ?? 'clean') !== activeLaundry) return false;
      if (activeCheck && !toCheck.has(it.id)) return false;
      if (activeAway && !it.away && !returned.has(it.id)) return false;
      return matchesSearch(searchedText(it, vocab?.kind_groups), query);
    });
  }, [list, activeWhat, activeLaundry, activeCheck, activeAway, returned, toCheck, query, vocab]);

  const empty = list !== null && list.length === 0;
  const title = status === 'archived' ? 'Archived' : profile === 'demo' ? 'Demo closet' : 'Your closet';
  const filters = (whatOn ? 1 : 0) + (activeLaundry ? 1 : 0) +
    (activeCheck ? 1 : 0) + (activeAway ? 1 : 0) + (status === 'archived' ? 1 : 0);
  // a piece away is said under away, not under the laundry (it is not in the basket at home)
  const inLaundry = useMemo(() => (list ?? []).filter((it) => it.laundry === 'laundry' && !it.away), [list]);
  const awayNow = useMemo(() => (list ?? []).filter((it) => it.away), [list]);
  // what "All clean" just washed, to put back with Undo while the laundry is shown
  const [cleaned, setCleaned] = useState<Cleaned['undo'] | null>(null);
  const laundryOn = activeLaundry === 'laundry';
  useEffect(() => {
    if (!laundryOn) setCleaned(null);
  }, [laundryOn]);
  const laundryAction = useRef<HTMLButtonElement>(null);
  const [focusAction, setFocusAction] = useState(false);
  useEffect(() => {
    if (!focusAction) return;
    setFocusAction(false);
    laundryAction.current?.focus();
  }, [focusAction]);
  const allClean = (pieces: ItemSummary[]) => {
    setWashing(true);
    void cleanAll(pieces.map((it) => it.id), (item) => itemSaved(qc, item, 'laundry'))
      .then(({ failed, undo }) => {
        if (failed) toast(`${failed} could not be marked clean. Try again.`, 'error');
        if (undo.length) setCleaned(undo);
        setFocusAction(true);
      })
      .finally(() => setWashing(false));
  };
  const undoClean = (undo: Cleaned['undo']) => {
    setWashing(true);
    void putBack(undo, (item) => itemSaved(qc, item, 'laundry'))
      .then((failed) => {
        if (failed) toast(`${failed} could not be put back in the laundry. Put ${failed === 1 ? 'it' : 'them'} back from ${failed === 1 ? 'its' : 'their'} page.`, 'error');
        setCleaned(null);
        setFocusAction(true);
      })
      .finally(() => setWashing(false));
  };
  const panel = wide && selectedId !== null;
  const closetPath = status === 'archived' ? '/archived' : '/';

  // On a computer the grid keeps as many tiles to a row as fit the whole width, the panel open or not: opening a piece
  // makes the tiles narrower and moves none of them to another row (`columnsFor`).
  useEffect(() => {
    const el = layout.current;
    if (!wide || !el) return;
    const measure = () => setLayoutWidth(el.clientWidth);
    measure();
    const seen = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    seen?.observe(el);
    return () => seen?.disconnect();
  }, [wide]);
  const columns = wide && layoutWidth > 0 ? columnsFor(layoutWidth, TILE_MIN_WIDE, GRID_GAP_WIDE) : null;

  // The piece chosen stays where it was on the screen while the panel opens beside the grid, and the panel opens level
  // with the top of the screen, so a tile far down does not open a panel out of sight.
  const anchor = useRef<{ id: string; top: number } | null>(null);
  const choose = useCallback((id: string, tile: HTMLElement) => {
    if (wide) anchor.current = { id, top: tile.getBoundingClientRect().top };
  }, [wide]);
  useLayoutEffect(() => {
    const el = layout.current;
    if (!panel || !el) return;
    const kept = anchor.current;
    anchor.current = null;
    const tile = kept && kept.id === selectedId ? el.querySelector<HTMLElement>(`[data-id="${CSS.escape(kept.id)}"]`) : null;
    if (kept && tile) {
      const moved = tile.getBoundingClientRect().top - kept.top;
      if (Math.abs(moved) >= 1) window.scrollBy(0, moved);
    }
    setPanelTop(Math.max(0, Math.round(16 - el.getBoundingClientRect().top)));
  }, [panel, selectedId]);

  // Focus goes into the panel as it opens, and back to the piece once it closes.
  const lastOpen = useRef<string | null>(null);
  useEffect(() => {
    if (panel && selectedId) {
      lastOpen.current = selectedId;
      aside.current?.focus({ preventScroll: true });
      return;
    }
    const id = lastOpen.current;
    lastOpen.current = null;
    const now = document.activeElement;
    if (id && (!now || now === document.body || !now.isConnected)) {
      layout.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
    }
  }, [panel, selectedId]);

  // Close and Escape go back to the closet: Back, when the page before is the closet, so history does not grow.
  const closePanel = useCallback(() => goBack(closetPath), [closetPath]);
  useEffect(() => {
    if (!panel) return;
    const key = (e: KeyboardEvent) => {
      // a sheet open over the page, or a field being typed in, takes Escape first
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      if ((e.target as HTMLElement | null)?.closest?.('input, textarea, select, [contenteditable="true"]')) return;
      e.preventDefault();
      closePanel();
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [panel, closePanel]);

  const grid = (
    <section className="closet-main" aria-labelledby="closet-title">
      <PageHeader title={title} titleId="closet-title" countTestId="item-count"
        count={list && !empty && (shown.length === list.length ? `${list.length} ${list.length === 1 ? 'item' : 'items'}` : `${shown.length} of ${list.length}`)} />

      {status === 'active' && list && (
        <StatusLine toCheck={offline ? 0 : toReview ?? 0} inLaundry={inLaundry.length} checking={activeCheck} washing={laundryOn}
          onCheck={() => setCheck(!activeCheck)} onLaundry={() => setLaundry(laundryOn ? null : 'laundry')}
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
            <div className="closet-toolbar-row">
              <div className="filter-wrap">
                <button ref={filterButton} type="button" className={`btn filter-button${filters ? ' has-filters' : ''}`} aria-expanded={filtering}
                  aria-haspopup="dialog" onClick={() => setFiltering((f) => !f)}>
                  <FilterIcon /><span className="filter-text">Filter</span>
                  {/* heard as "Filter, 1 on": the count is part of the name, as it is seen */}
                  {filters > 0 && <><span className="visually-hidden">, </span><span className="filter-count">{filters}</span><span className="visually-hidden"> on</span></>}
                </button>
                {filtering && (
                  <Sheet title="Filter" popover keep={filterButton} className="filter-sheet" onClose={() => setFiltering(false)}>
                    <FilterChoices status={status} laundry={activeLaundry} away={activeAway} onAway={setAway} onLaundry={setLaundry}
                      view={list && !empty ? gridView : null}
                      onView={(value) => { gridMoment = { view: value, setting: showDrawings }; setMoment(gridMoment); }}
                      choices={choices} what={activeWhat} onWhat={(level, id) => setWhat(chooseWhat(activeWhat, level, id))} />
                  </Sheet>
                )}
              </div>
              {filters > 0 && (
                <ul className="active-filters" aria-label="Filters on">
                  {status === 'archived' && (
                    <li><Link to="/" className="chip chip-remove" aria-label="Remove filter: Archived">Archived<CloseIcon /></Link></li>
                  )}
                  {whatOn && (
                    <li><button type="button" className="chip chip-remove" aria-label={`Remove filter: ${whatName(list ?? [], vocab?.kind_groups, activeWhat)}`}
                      onClick={() => setWhat(ANY)}>{whatName(list ?? [], vocab?.kind_groups, activeWhat)}<CloseIcon /></button></li>
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
            </div>
          </div>
          {status === 'active' && activeCheck && (toReview ?? 0) > 0 && (
            <p className="closet-next" data-testid="review-notice">
              <span className="muted">Claude wasn't sure of a detail on {toReview === 1 ? 'this piece' : 'these'}.</span>
              <Link to="/review" className={buttonClass({ small: true })}>Check them one at a time</Link>
            </p>
          )}
          {status === 'active' && laundryOn && (cleaned || inLaundry.length > 0) && (
            <p className="closet-next" data-testid="laundry-notice">
              <span className="muted">{laundryNotice(inLaundry.length, cleaned ? cleaned.length : null)}</span>
              {cleaned ? (
                <button ref={laundryAction} type="button" className={buttonClass({ small: true })} disabled={washing || offline} title={offline ? "You're offline" : undefined}
                  onClick={() => undoClean(cleaned)}>{washing ? 'Putting back…' : 'Undo'}</button>
              ) : (
                <button ref={laundryAction} type="button" className={buttonClass({ small: true })} disabled={washing || offline} title={offline ? "You're offline" : undefined}
                  onClick={() => allClean(inLaundry)}>{washing ? 'Marking clean…' : 'All clean'}</button>
              )}
            </p>
          )}
        </>
      ) : null}

      {empty && status === 'active' && <EmptyCloset demo={profile === 'demo'} />}
      {empty && status === 'archived' && (
        <EmptyState title="Nothing archived" body="Clothes you archive (given away, stored for good) are kept here, out of the way." />
      )}

      {list && !empty && (
        shown.length === 0 ? (
          <div className="empty"><p className="muted">{emptySentence({ check: activeCheck, toCheck: toCheck.size, away: activeAway,
            awayNow: awayNow.length, laundry: laundryOn, inLaundry: inLaundry.length, searching: !!query.trim(),
            what: whatOn })}</p></div>
        ) : activeAway ? (
          <AwayView pieces={shown} returned={returned} offline={offline} saved={(item) => itemSaved(qc, item, 'away')}
            failed={(m) => toast(m, 'error')}
            onReturned={(id, back) => setReturned((r) => { const n = new Set(r); if (back) n.add(id); else n.delete(id); return n; })} />
        ) : (
          <ul className={`grid${columns ? ' has-columns' : ''}`} aria-label="Clothes"
            style={columns ? { '--columns': columns } as CSSProperties : undefined}>
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
        <aside ref={aside} tabIndex={-1} className="detail-panel closet-panel" aria-label="Item details" style={{ marginTop: panelTop }}>
          <div className="closet-panel-head">
            <Button variant="ghost" small onClick={closePanel}><CloseIcon /> Close</Button>
          </div>
          <ItemDetail key={selectedId} id={selectedId} status={status} inPanel />
        </aside>
      )}
    </div>
  );
}

const LAUNDRY: Record<Laundry, string> = { clean: 'Clean', laundry: 'In the laundry' };
/** The grid's smallest tile and the room between tiles on a computer (styles.css, "grid & tiles"). */
const TILE_MIN_WIDE = 180;
const GRID_GAP_WIDE = 16;

const NEEDS_CHECK = 'Needs a check';
const AWAY = 'Away';

/**
 * One line over the grid for what wants seeing to: how many pieces need a quick check, how many are in the laundry and
 * how many are away. Each part shows only those pieces; what to do with them (check them one at a time, mark them all
 * clean) is said under the toolbar, so showing them puts nothing in above the search.
 */
function StatusLine({ toCheck, inLaundry: n, checking, washing, onCheck, onLaundry, away, awayOn, onAway }: {
  toCheck: number; inLaundry: number; checking: boolean; washing: boolean; onCheck(): void; onLaundry(): void;
  away: ItemSummary[]; awayOn: boolean; onAway(): void;
}) {
  const laundry = n > 0 || washing;
  if (!toCheck && !laundry && !checking && !away.length && !awayOn) return null;
  return (
    <div className="closet-status" data-testid="closet-status">
      <p className="closet-status-line">
        {(toCheck > 0 || checking) && (
          <button type="button" className={`btn btn-link closet-status-part${checking ? ' is-on' : ''}`} aria-pressed={checking}
            data-testid="to-check" onClick={onCheck}>
            {toCheck} to check
          </button>
        )}
        {(toCheck > 0 || checking) && laundry && <span aria-hidden="true"> · </span>}
        {laundry && (
          <button type="button" className={`btn btn-link closet-status-part${washing ? ' is-on' : ''}`} aria-pressed={washing}
            data-testid="in-laundry" onClick={onLaundry}>
            {laundryPart(n)}
          </button>
        )}
        {(away.length > 0 || awayOn) && (
          <span className={`closet-status-group${toCheck > 0 || checking || laundry ? ' is-own-line' : ''}`}>
            {(toCheck > 0 || checking || laundry) && <span className="closet-status-dot" aria-hidden="true"> · </span>}
            <button type="button" className={`btn btn-link closet-status-part${awayOn ? ' is-on' : ''}`} aria-pressed={awayOn}
              data-testid="away" onClick={onAway}>
              {awayPart(away)}
            </button>
          </span>
        )}
      </p>
    </div>
  );
}

function FilterChoices({ status, laundry, away, onLaundry, onAway, choices, what, onWhat, view, onView }: {
  status: 'active' | 'archived';
  /** what the grid shows, photos or drawings (null while there is nothing to show) */
  view: GridView | null;
  onView(view: GridView): void;
  laundry: Laundry | null;
  away: boolean;
  onLaundry(l: Laundry | null): void;
  onAway(on: boolean): void;
  /** what a piece is, one level at a time: the groups the closet's pieces are in, then what is in the one chosen */
  choices: { groups: KindGroup[]; categories: Choice[]; kinds: Choice[] };
  what: What;
  onWhat(level: keyof What, id: string | null): void;
}) {
  const groupName = groupTitle(choices.groups, what.group);
  const level = (key: 'category' | 'kind', list: Choice[]) => list.length > 0 && (
    <div className="chips filter-what-more" role="group"
      aria-label={key === 'category' ? `Which ${groupName}` : `Kinds of ${what.category ? categoryPlural(what.category) : groupName}`}>
      <button type="button" className={`chip${!what[key] ? ' is-on' : ''}`} aria-pressed={!what[key]} onClick={() => onWhat(key, null)}>
        {key === 'category' ? `All ${groupName.toLowerCase()}` : 'Any kind'}
      </button>
      {list.map((c) => (
        <button key={c.id} type="button" className={`chip${what[key] === c.id ? ' is-on' : ''}`} aria-pressed={what[key] === c.id}
          onClick={() => onWhat(key, c.id)}>{c.name}</button>
      ))}
    </div>
  );
  return (
    <div className="filter-choices">
      {view && (
        <div className="filter-group">
          <h3 className="chip-group-title">Show</h3>
          <div className="view-choices">
            <SegmentedControl label="Show" className="view-choice" value={view} onChange={onView}
              options={[{ value: 'photos', label: 'Photos' }, { value: 'drawings', label: 'Drawings' }]} />
          </div>
        </div>
      )}
      <div className="filter-group">
        <h3 className="chip-group-title">Which clothes</h3>
        <SegmentedControl label="Which clothes" small value={status}
          options={[{ value: 'active', label: 'In use', to: '/' }, { value: 'archived', label: 'Archived', to: '/archived' }]} />
      </div>
      {choices.groups.length > 1 && (
        <div className="filter-group">
          <h3 className="chip-group-title">What it is</h3>
          <div className="chips" role="group" aria-label="What it is">
            <button type="button" className={`chip${!what.group ? ' is-on' : ''}`} aria-pressed={!what.group} onClick={() => onWhat('group', null)}>All</button>
            {choices.groups.map((g) => (
              <button key={g.id} type="button" className={`chip${what.group === g.id ? ' is-on' : ''}`} aria-pressed={what.group === g.id}
                onClick={() => onWhat('group', g.id)}>{g.title}</button>
            ))}
          </div>
          {level('category', choices.categories)}
          {level('kind', choices.kinds)}
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
  item: ItemSummary; status: 'active' | 'archived'; selected: boolean; progress: Progress | null; view: GridView;
  onChoose(id: string, tile: HTMLElement): void;
}) {
  const name = item.name || label('category', item.category) || 'New item';
  const caption = tileCaption(item.category, item.color);
  return (
    <Link to={itemPath(item.id, status)} className={`tile${selected ? ' is-selected' : ''}`} aria-current={selected ? 'true' : undefined}
      data-testid="tile" data-id={item.id} onClick={(e) => onChoose(item.id, e.currentTarget)}>
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
