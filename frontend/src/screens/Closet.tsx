import { useEffect, useMemo, useState } from 'react';
import { HangerIcon, SearchIcon, WarnIcon } from '../components/Icons';
import { ModelBanner } from '../components/ModelBanner';
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
}

export function ClosetScreen({ status, selectedId, wide }: Props) {
  const { items, loadItems, loadError, model, profile } = useCloset();
  const list = items[status];
  const [category, setCategory] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [laundry, setLaundry] = useState<Laundry | null>(null);
  const [gridView, setGridView] = useState<GridView>(loadGridView);

  useEffect(() => {
    void loadItems(status);
  }, [status, loadItems]);

  const categories = useMemo(() => {
    const seen = new Map<string, number>();
    for (const it of list ?? []) if (it.category) seen.set(it.category, (seen.get(it.category) ?? 0) + 1);
    return [...seen.keys()].sort((a, b) => categoryPlural(a).localeCompare(categoryPlural(b)));
  }, [list]);

  const activeCategory = category && categories.includes(category) ? category : null;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (list ?? []).filter((it) => {
      if (activeCategory && it.category !== activeCategory) return false;
      if (laundry && status === 'active' && (it.laundry ?? 'clean') !== laundry) return false;
      if (!q) return true;
      const hay = [it.name, label('category', it.category), label('color', it.color), label('pattern', it.pattern), it.category, it.color]
        .filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [list, activeCategory, laundry, status, query]);

  const empty = list !== null && list.length === 0;
  const title = status === 'archived' ? 'Archived' : profile === 'demo' ? 'Demo closet' : 'Your closet';

  const grid = (
    <section className="closet-main" aria-labelledby="closet-title">
      <header className="page-header">
        <div className="page-title-row">
          <h1 id="closet-title">{title}</h1>
          {list && !empty && (
            <span className="count" data-testid="item-count">
              {shown.length === list.length ? `${list.length} ${list.length === 1 ? 'item' : 'items'}` : `${shown.length} of ${list.length}`}
            </span>
          )}
        </div>
        <div className="segmented segmented-small" role="group" aria-label="Which clothes">
          <Link to="/" className={status === 'active' ? 'is-on' : ''} aria-current={status === 'active' ? 'page' : undefined}>In use</Link>
          <Link to="/archived" className={status === 'archived' ? 'is-on' : ''} aria-current={status === 'archived' ? 'page' : undefined}>Archived</Link>
        </div>
      </header>

      {status === 'active' && <ModelBanner />}

      {list === null && !loadError && <div className="grid grid-skeleton" aria-hidden="true">{Array.from({ length: 6 }, (_, i) => <div key={i} className="tile-skeleton" />)}</div>}
      {list === null && loadError && <p className="form-error" role="alert">{loadError}</p>}

      {empty && status === 'active' && <EmptyCloset demo={profile === 'demo'} />}
      {empty && status === 'archived' && (
        <div className="empty">
          <p className="empty-title">Nothing archived</p>
          <p className="muted">Clothes you archive (given away, stored for good) are kept here, out of the way.</p>
        </div>
      )}

      {list && !empty && (
        <>
          <div className="filters">
            <label className="search">
              <SearchIcon />
              <span className="visually-hidden">Search your clothes</span>
              <input type="search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} />
            </label>
            {categories.length > 1 && (
              <div className="chips chips-scroll" role="group" aria-label="Filter by category">
                <button className={`chip${!activeCategory ? ' is-on' : ''}`} aria-pressed={!activeCategory} onClick={() => setCategory(null)}>All</button>
                {categories.map((c) => (
                  <button key={c} className={`chip${activeCategory === c ? ' is-on' : ''}`} aria-pressed={activeCategory === c}
                    onClick={() => setCategory(activeCategory === c ? null : c)}>{categoryPlural(c)}</button>
                ))}
              </div>
            )}
            <div className="filters-row">
              {status === 'active' && (
                <div className="chips" role="group" aria-label="Filter by laundry">
                  {([['clean', 'Clean'], ['laundry', 'In the laundry']] as const).map(([value, text]) => (
                    <button key={value} className={`chip${laundry === value ? ' is-on' : ''}`} aria-pressed={laundry === value}
                      onClick={() => setLaundry(laundry === value ? null : value)}>{text}</button>
                  ))}
                </div>
              )}
              <div className="segmented segmented-small grid-view" role="group" aria-label="Show">
                {([['photos', 'Photos'], ['drawings', 'Drawings']] as const).map(([value, text]) => (
                  <button key={value} type="button" className={gridView === value ? 'is-on' : ''} aria-pressed={gridView === value}
                    onClick={() => { setGridView(value); saveGridView(value); }}>{text}</button>
                ))}
              </div>
            </div>
          </div>
          {shown.length === 0 ? (
            <div className="empty"><p className="muted">Nothing matches. Try another word or category.</p></div>
          ) : (
            <ul className="grid" aria-label="Clothes">
              {shown.map((it) => (
                <li key={it.id}><Tile item={it} status={status} selected={it.id === selectedId} model={model} view={gridView} /></li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );

  if (!wide) return grid;
  return (
    <div className="master-detail">
      {grid}
      <aside className="detail-panel" aria-label="Item details">
        {selectedId ? (
          <ItemDetail key={selectedId} id={selectedId} status={status} inPanel />
        ) : (
          <div className="panel-empty">
            <HangerIcon />
            <p>{empty ? 'Your clothes will show up here.' : 'Choose something to see and change its details.'}</p>
          </div>
        )}
      </aside>
    </div>
  );
}

export function busyLabel(model: ModelInfo | null): string {
  return model && model.state !== 'ready' ? 'Waiting for the model' : 'Removing background…';
}

function Tile({ item, status, selected, model, view }: { item: ItemSummary; status: 'active' | 'archived'; selected: boolean; model: ModelInfo | null; view: GridView }) {
  const name = item.name || label('category', item.category) || 'New item';
  const caption = tileCaption(item.category, item.color);
  const busy = item.cutout_state === 'pending' || item.cutout_state === 'processing';
  return (
    <Link to={itemPath(item.id, status)} className={`tile${selected ? ' is-selected' : ''}`} aria-current={selected ? 'true' : undefined}
      data-testid="tile">
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
    <div className="empty empty-big">
      <div className="empty-art"><HangerIcon /></div>
      <p className="empty-title">{demo ? 'The demo closet is empty' : 'Your closet is empty'}</p>
      <p className="muted">Take a photo of a piece of clothing and Closet will cut it out and keep it here.</p>
      <div className="stack stack-narrow">
        <button className="btn btn-primary btn-block" disabled={offline} onClick={() => navigate('/add')}>Add your first item</button>
        {!demo && (
          <button className="btn btn-link" disabled={offline} onClick={() => switchProfile('demo').catch((e) => toast((e as Error).message, 'error'))}>
            or look around the demo closet
          </button>
        )}
      </div>
    </div>
  );
}
