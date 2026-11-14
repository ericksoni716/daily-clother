import { useEffect, useMemo, useRef, useState } from 'react';
import { CloseIcon, DrawingIcon, FilterIcon, HangerIcon, ImagesIcon, SearchIcon, WarnIcon } from '../components/Icons';
import { ModelBanner } from '../components/ModelBanner';
import { Button, buttonClass, EmptyState, Notice, PageHeader, SegmentedControl, Sheet } from '../components/ui';
import { loadGridView, saveGridView, type GridView } from '../drawing';
import { categoryPlural, label, tileCaption } from '../labels';
import { itemPath, Link, navigate } from '../router';
import { useCloset } from '../store';
import type { ItemSummary, Laundry, ModelInfo } from '../types';
import { ItemDetail } from './ItemDetail';

interface Props {
  status: 'active' | 'archived';
  selectedId: string | null;
  wide: boolean;
  /** How many pieces wait in the review queue (null until known). */
  toReview?: number | null;
}

export function ClosetScreen({ status, selectedId, wide, toReview = null }: Props) {
  const { items, loadItems, loadError, model, profile } = useCloset();
  const list = items[status];
  const [category, setCategory] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [laundry, setLaundry] = useState<Laundry | null>(null);
  const [gridView, setGridView] = useState<GridView>(loadGridView);
  const [filtering, setFiltering] = useState(false);
  const [panelTop, setPanelTop] = useState(0);
  const filterButton = useRef<HTMLButtonElement>(null);
  const layout = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void loadItems(status);
  }, [status, loadItems]);

  const categories = useMemo(() => {
    const seen = new Map<string, number>();
    for (const it of list ?? []) if (it.category) seen.set(it.category, (seen.get(it.category) ?? 0) + 1);
    return [...seen.keys()].sort((a, b) => categoryPlural(a).localeCompare(categoryPlural(b)));
  }, [list]);

  const activeCategory = category && categories.includes(category) ? category : null;
  const activeLaundry = status === 'active' ? laundry : null;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (list ?? []).filter((it) => {
      if (activeCategory && it.category !== activeCategory) return false;
      if (activeLaundry && (it.laundry ?? 'clean') !== activeLaundry) return false;
      if (!q) return true;
      const hay = [it.name, label('category', it.category), label('color', it.color), label('pattern', it.pattern), it.category, it.color]
        .filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [list, activeCategory, activeLaundry, query]);

  const empty = list !== null && list.length === 0;
  const title = status === 'archived' ? 'Archived' : profile === 'demo' ? 'Demo closet' : 'Your closet';
  const filters = (activeCategory ? 1 : 0) + (activeLaundry ? 1 : 0) + (status === 'archived' ? 1 : 0);
  const panel = wide && selectedId !== null;

  // The panel scrolls with the page, so it opens level with where the owner is looking, not at the top of the grid.
  const choose = () => {
    if (!wide || !layout.current) return;
    setPanelTop(Math.max(0, Math.round(16 - layout.current.getBoundingClientRect().top)));
  };

  const grid = (
    <section className="closet-main" aria-labelledby="closet-title">
      <PageHeader title={title} titleId="closet-title" countTestId="item-count"
        count={list && !empty && (shown.length === list.length ? `${list.length} ${list.length === 1 ? 'item' : 'items'}` : `${shown.length} of ${list.length}`)}
        secondary={status === 'active' && list && !empty && <Link to="/insights" className={buttonClass({ variant: 'ghost', small: true })}>Insights</Link>} />

      {status === 'active' && !!toReview && (
        <Notice className="review-notice" testId="review-notice"
          action={<Link to="/review" className={buttonClass({ variant: 'link', small: true })}>Review</Link>}>
          {toReview} {toReview === 1 ? 'piece needs' : 'pieces need'} a quick check
        </Notice>
      )}
      {status === 'active' && <ModelBanner />}

      {list === null && !loadError && <div className="grid grid-skeleton" aria-hidden="true">{Array.from({ length: 6 }, (_, i) => <div key={i} className="tile-skeleton" />)}</div>}
      {list === null && loadError && <p className="form-error" role="alert">{loadError}</p>}

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
                {filters > 0 && <><span className="filter-count" aria-hidden="true">{filters}</span><span className="visually-hidden">, {filters} on</span></>}
              </button>
              {filtering && (
                <Sheet title="Filter" popover keep={filterButton} className="filter-sheet" onClose={() => setFiltering(false)}>
                  <FilterChoices status={status} categories={categories} category={activeCategory} laundry={activeLaundry}
                    onCategory={setCategory} onLaundry={setLaundry} />
                </Sheet>
              )}
            </div>
            {list && !empty && (
              <SegmentedControl label="Show" className="grid-view" value={gridView}
                options={[
                  { value: 'photos', label: <><ImagesIcon /><span className="seg-text">Photos</span></> },
                  { value: 'drawings', label: <><DrawingIcon /><span className="seg-text">Drawings</span></> },
                ]}
                onChange={(value) => { setGridView(value); saveGridView(value); }} />
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
              {activeLaundry && (
                <li><button type="button" className="chip chip-remove" aria-label={`Remove filter: ${LAUNDRY[activeLaundry]}`}
                  onClick={() => setLaundry(null)}>{LAUNDRY[activeLaundry]}<CloseIcon /></button></li>
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
          <div className="empty"><p className="muted">Nothing matches. Try another word or filter.</p></div>
        ) : (
          <ul className="grid" aria-label="Clothes">
            {shown.map((it) => (
              <li key={it.id}><Tile item={it} status={status} selected={it.id === selectedId} model={model} view={gridView} onChoose={choose} /></li>
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

function FilterChoices({ status, categories, category, laundry, onCategory, onLaundry }: {
  status: 'active' | 'archived';
  categories: string[];
  category: string | null;
  laundry: Laundry | null;
  onCategory(c: string | null): void;
  onLaundry(l: Laundry | null): void;
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
      {status === 'active' && (
        <div className="filter-group">
          <h3 className="chip-group-title">Laundry</h3>
          <div className="chips" role="group" aria-label="Filter by laundry">
            {(['clean', 'laundry'] as const).map((value) => (
              <button key={value} type="button" className={`chip${laundry === value ? ' is-on' : ''}`} aria-pressed={laundry === value}
                onClick={() => onLaundry(laundry === value ? null : value)}>{LAUNDRY[value]}</button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function busyLabel(model: ModelInfo | null): string {
  return model && model.state !== 'ready' ? 'Waiting for the model' : 'Removing background…';
}

function Tile({ item, status, selected, model, view, onChoose }: {
  item: ItemSummary; status: 'active' | 'archived'; selected: boolean; model: ModelInfo | null; view: GridView; onChoose(): void;
}) {
  const name = item.name || label('category', item.category) || 'New item';
  const caption = tileCaption(item.category, item.color);
  const busy = item.cutout_state === 'pending' || item.cutout_state === 'processing';
  return (
    <Link to={itemPath(item.id, status)} className={`tile${selected ? ' is-selected' : ''}`} aria-current={selected ? 'true' : undefined}
      data-testid="tile" onClick={onChoose}>
      <div className="tile-card">
        <TilePicture item={item} view={view} />
        {busy && <span className="badge badge-busy"><span className="spinner" aria-hidden="true" />{busyLabel(model)}</span>}
        {item.cutout_state === 'failed' && <span className="badge badge-warn"><WarnIcon />Background not removed</span>}
        {item.laundry === 'laundry' && <span className="tile-mark" data-testid="laundry-mark">In the laundry</span>}
      </div>
      <span className="tile-name">{name}</span>
      <span className="tile-caption">{caption || ' '}</span>
    </Link>
  );
}

/** The picture the closet grid shows for an item (also used by Insights). */
export function TilePicture({ item, view }: { item: ItemSummary; view: GridView }) {
  const alt = item.name || label('category', item.category) || 'Item';
  if (view === 'drawings' && item.illustration_url) return <img className="pic-illustration" src={item.illustration_url} alt={`${alt}, drawing`} loading="lazy" />;
  if (item.cutout_state === 'ready' && item.thumb_url) return <img className="pic-cutout" src={item.thumb_url} alt={alt} loading="lazy" />;
  if (item.thumb_url) return <img className="pic-photo" src={item.thumb_url} alt={alt} loading="lazy" />;
  if (item.illustration_url) return <img className="pic-illustration" src={item.illustration_url} alt={alt} loading="lazy" />;
  return <div className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></div>;
}

function EmptyCloset({ demo }: { demo: boolean }) {
  const { switchProfile, toast, offline } = useCloset();
  return (
    <EmptyState big icon={<HangerIcon />} title={demo ? 'The demo closet is empty' : 'Your closet is empty'}
      body="Take a photo of a piece of clothing and Closet will cut it out and keep it here.">
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
