import { useEffect, useId, useState } from 'react';
import { api, ApiError } from '../api';
import { SearchIcon } from './Icons';
import { alsoThought, kindDrawing, kindsIn, searchKinds, type KindCatalogue, type KindInfo } from '../kinds';
import type { Item } from '../types';
import './FixDetails.css';
import './KindPicker.css';

let asked: Promise<KindCatalogue> | null = null;

/** The kinds are the same for every item, so they are asked for once. */
function loadCatalogue(): Promise<KindCatalogue> {
  asked ??= api.kinds().catch((e) => {
    asked = null;
    throw e;
  });
  return asked;
}

export function useKindCatalogue(): { catalogue: KindCatalogue | null; error: string | null } {
  const [catalogue, setCatalogue] = useState<KindCatalogue | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    loadCatalogue().then((c) => { if (live) setCatalogue(c); }).catch((e) => { if (live) setError((e as ApiError).message); });
    return () => {
      live = false;
    };
  }, []);
  return { catalogue, error };
}

interface Props {
  item: Item;
  busy: boolean;
  onPick(kind: KindInfo): void;
}

/**
 * Choosing what an item is: a search first, then the kinds Claude also thought of, then every kind of the owner's
 * taxonomy in its group, each with a small drawing. The item's kind now is marked.
 */
export function KindPicker({ item, busy, onPick }: Props) {
  const { catalogue, error } = useKindCatalogue();
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState<string | null>(item.group ?? null);
  const panel = useId();
  if (error) return <p className="form-error" role="alert">{error}</p>;
  if (!catalogue) return <p className="muted" role="status">Getting the list of kinds…</p>;
  const found = query.trim() ? searchKinds(catalogue, query) : null;
  const also = alsoThought(catalogue, item.kind_alternatives, item.kind ?? null);
  const current = catalogue.groups.find((g) => g.id === group) ?? catalogue.groups[0];
  const tiles = (kinds: KindInfo[]) => <KindTiles kinds={kinds} item={item} busy={busy} onPick={onPick} />;
  return (
    <div className="kind-picker">
      <label className="search kind-search">
        <SearchIcon />
        <span className="visually-hidden">Search the kinds</span>
        <input type="search" placeholder="Search, e.g. chelsea, jogger, snap" value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>
      {found ? (
        <section aria-label="Kinds found">
          {found.length ? tiles(found) : <p className="muted">No kind goes by that word. Try another, or clear the search to look by group.</p>}
        </section>
      ) : (
        <>
          {also.length > 0 && (
            <section aria-label="Claude also thought">
              <h3 className="chip-group-title">Claude also thought</h3>
              {tiles(also)}
            </section>
          )}
          <div className="chips kind-groups" role="group" aria-label="Groups">
            {catalogue.groups.map((g) => (
              <button key={g.id} type="button" className={`chip${g.id === current.id ? ' is-on' : ''}`} aria-pressed={g.id === current.id}
                aria-controls={panel} onClick={() => setGroup(g.id)}>{g.title}</button>
            ))}
          </div>
          <section id={panel} aria-label={current.title}>
            {tiles(kindsIn(catalogue, current.id))}
          </section>
        </>
      )}
    </div>
  );
}

function KindTiles({ kinds, item, busy, onPick }: { kinds: KindInfo[] } & Props) {
  return (
    <div className="fix-tiles kind-tiles">
      {kinds.map((k) => {
        const on = k.id === item.kind;
        return (
          <button key={k.id} type="button" className={`fix-tile${on ? ' is-on' : ''}`} aria-pressed={on} disabled={busy}
            onClick={() => onPick(k)}>
            {k.drawn ? <img src={kindDrawing(k.id, item.color_hex)} alt="" loading="lazy" /> : <span className="fix-tile-blank" />}
            <span>{k.name}</span>
          </button>
        );
      })}
    </div>
  );
}
