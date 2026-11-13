import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { BackIcon, HangerIcon } from '../components/Icons';
import {
  barWidth, costCaption, FIELD_WORDS, forgetKept, groupLabel, keepPiece, keptPieces, MAKEUP_FIELDS, plural, shortDate, unwornCaption,
  windowLabel, type CostPiece, type Counted, type Insights, type MakeupField, type Unworn, type UnwornPiece,
} from '../insights';
import { categoryPlural, label } from '../labels';
import { itemPath, Link } from '../router';
import { useCloset } from '../store';
import type { ItemSummary } from '../types';
import { localDay } from '../wears';
import './Insights.css';

const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';

type Phase =
  | { kind: 'loading' }
  | { kind: 'ready'; answer: Insights }
  | { kind: 'error'; message: string; offline: boolean };

/** The last answer while the app is open, so coming back from an item shows it at once (and it is fetched again). */
let memory: { profile: string; answer: Insights } | null = null;

export function InsightsScreen() {
  const { profile, items, loadItems, offline, upsert, toast } = useCloset();
  const [phase, setPhase] = useState<Phase>(() => (memory && memory.profile === profile ? { kind: 'ready', answer: memory.answer } : { kind: 'loading' }));
  const [attempt, setAttempt] = useState(0);
  const today = localDay();
  const [kept, setKept] = useState(() => keptPieces(profile, today));
  const [archiving, setArchiving] = useState<string | null>(null);
  const [gone, setGone] = useState<string[]>([]);

  useEffect(() => {
    if (items.active === null) void loadItems('active');
  }, [items.active, loadItems]);

  useEffect(() => {
    let live = true;
    api.insights().then(
      (answer) => {
        if (!live) return;
        memory = { profile, answer };
        setPhase({ kind: 'ready', answer });
        setGone([]);
      },
      (e) => {
        if (!live) return;
        const err = e as ApiError;
        // keep what is on screen if there is something; otherwise say why there is nothing
        setPhase((p) => (p.kind === 'ready' ? p : {
          kind: 'error', offline: err.status === 0,
          message: err.status === 0
            ? "You're offline, and Insights has not been opened on this device before. It shows here once Closet on your computer can be reached."
            : err.message,
        }));
      },
    );
    return () => {
      live = false;
    };
  }, [profile, attempt]);

  // Back online: ask again.
  const [wasOffline, setWasOffline] = useState(offline);
  if (wasOffline !== offline) {
    setWasOffline(offline);
    if (!offline) setAttempt((n) => n + 1);
  }

  const byId = useMemo(() => new Map((items.active ?? []).map((i) => [i.id, i])), [items.active]);

  const archive = useCallback(async (id: string) => {
    setArchiving(id);
    try {
      const item = await api.patch(id, { status: 'archived' });
      upsert(item);
      setGone((g) => [...g, id]);
      toast('Archived. It is kept under Archived in your closet.');
      setAttempt((n) => n + 1);
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setArchiving(null);
    }
  }, [upsert, toast]);

  const keep = useCallback((id: string) => {
    const until = keepPiece(profile, id, today);
    setKept((k) => ({ ...k, [id]: until }));
    toast(`Kept. It is not listed here again until ${shortDate(until)}.`);
  }, [profile, today, toast]);

  const showKept = useCallback(() => {
    forgetKept(profile);
    setKept({});
  }, [profile]);

  return (
    <section className="insights" aria-labelledby="insights-title">
      <header className="page-header insights-header">
        <div>
          <Link to="/" className="btn btn-ghost btn-small insights-back"><BackIcon /> Closet</Link>
          <h1 id="insights-title">Insights</h1>
          <p className="muted insights-lede">How your clothes are being used, from what you have recorded as worn.</p>
        </div>
      </header>

      {phase.kind === 'loading' && (
        <div className="insights-grid" aria-hidden="true">{Array.from({ length: 4 }, (_, i) => <div key={i} className="insights-skeleton" />)}</div>
      )}
      {phase.kind === 'error' && (
        <div className={phase.offline ? 'empty' : ''}>
          <p className={phase.offline ? 'muted' : 'form-error'} role="alert">{phase.message}</p>
          {!phase.offline && <button className="btn" onClick={() => setAttempt((n) => n + 1)}>Try again</button>}
        </div>
      )}
      {phase.kind === 'ready' && (
        <div className="insights-grid">
          <CostCard answer={phase.answer} byId={byId} />
          <UnwornCard finding={phase.answer.never_worn} testid="never-worn" byId={byId} kept={kept} gone={gone} offline={offline}
            archiving={archiving} onArchive={archive} onKeep={keep} onShowKept={showKept} />
          <UnwornCard finding={phase.answer.not_worn_lately} testid="not-worn-lately" byId={byId} kept={kept} gone={gone} offline={offline}
            archiving={archiving} onArchive={archive} onKeep={keep} onShowKept={showKept} />
          <WornMostCard answer={phase.answer} byId={byId} />
          <SpreadCard answer={phase.answer} byId={byId} />
          <MakeupCard answer={phase.answer} />
        </div>
      )}
    </section>
  );
}

type ById = Map<string, ItemSummary>;

function Card({ title, sentence, testid, wide, children }: { title: string; sentence: string; testid: string; wide?: boolean; children?: ReactNode }) {
  const id = `insights-${testid}`;
  return (
    <section className={`insights-card${wide ? ' is-wide' : ''}`} aria-labelledby={id} data-testid={testid}>
      <h2 id={id}>{title}</h2>
      <p className="insights-sentence">{sentence}</p>
      {children}
    </section>
  );
}

function nameOf(item: ItemSummary | undefined): string {
  return item?.name || label('category', item?.category) || 'Item';
}

function Picture({ item }: { item: ItemSummary | undefined }) {
  const alt = nameOf(item);
  if (item?.cutout_state === 'ready' && item.thumb_url) return <img className="pic-cutout" src={item.thumb_url} alt={alt} loading="lazy" />;
  if (item?.illustration_url) return <img className="pic-illustration" src={item.illustration_url} alt={alt} loading="lazy" />;
  if (item?.thumb_url) return <img className="pic-photo" src={item.thumb_url} alt={alt} loading="lazy" />;
  return <div className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></div>;
}

/** A small picture that opens the item, with its name and a caption. */
function Piece({ id, byId, caption, title, children }: { id: string; byId: ById; caption: string; title?: string; children?: ReactNode }) {
  const item = byId.get(id);
  return (
    <li className="insights-piece" data-testid="insight-piece">
      <Link to={itemPath(id, 'active')} className="insights-piece-link" title={title}>
        <span className="insights-piece-pic"><Picture item={item} /></span>
        <span className="insights-piece-name">{nameOf(item)}</span>
        <span className="insights-piece-caption">{caption}</span>
      </Link>
      {children}
    </li>
  );
}

function CostRow({ heading, pieces, byId }: { heading: string; pieces: CostPiece[]; byId: ById }) {
  if (!pieces.length) return null;
  return (
    <>
      <h3 className="chip-group-title">{heading}</h3>
      <ul className="insights-pieces">
        {pieces.map((p) => <Piece key={p.id} id={p.id} byId={byId} caption={costCaption(p)} title={p.sentence} />)}
      </ul>
    </>
  );
}

function CostCard({ answer, byId }: { answer: Insights; byId: ById }) {
  const f = answer.cost_per_wear;
  return (
    <Card title={f.title} sentence={f.sentence} testid="cost-per-wear" wide>
      {f.best[0] && <p className="insights-detail" data-testid="cost-best">{f.best[0].sentence}</p>}
      <CostRow heading="Best value" pieces={f.best} byId={byId} />
      <CostRow heading="Most per wear" pieces={f.worst} byId={byId} />
      <CostRow heading="Not worn yet" pieces={f.not_worn} byId={byId} />
    </Card>
  );
}

interface UnwornProps {
  finding: Unworn;
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

function UnwornCard({ finding, testid, byId, kept, gone, offline, archiving, onArchive, onKeep, onShowKept }: UnwornProps) {
  const listed = finding.items.filter((p) => !gone.includes(p.id));
  const shown = listed.filter((p) => !kept[p.id]);
  const hidden = listed.length - shown.length;
  return (
    <Card title={finding.title} sentence={finding.sentence} testid={testid} wide>
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
          <Link to={itemPath(r.id, 'active')} className="insights-bar-row">
            <span className="insights-bar-pic"><Picture item={byId.get(r.id)} /></span>
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

function WornMostCard({ answer, byId }: { answer: Insights; byId: ById }) {
  const windows = answer.worn_most.windows;
  const [index, setIndex] = useState(() => Math.max(0, windows.findIndex((w) => w.enough)));
  const w = windows[Math.min(index, windows.length - 1)];
  return (
    <Card title={answer.worn_most.title} sentence={w.sentence} testid="worn-most">
      <div className="segmented segmented-small insights-windows" role="group" aria-label="Over">
        {windows.map((x, i) => (
          <button key={String(x.days)} className={i === index ? 'is-on' : ''} aria-pressed={i === index} onClick={() => setIndex(i)}>
            {windowLabel(x.days)}
          </button>
        ))}
      </div>
      {w.items.length > 0 && <Bars rows={w.items} byId={byId} />}
    </Card>
  );
}

function SpreadCard({ answer, byId }: { answer: Insights; byId: ById }) {
  const f = answer.spread;
  return (
    <Card title={f.title} sentence={f.sentence} testid="spread">
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
    <Card title={f.title} sentence={f.sentence} testid="makeup">
      {f.pieces > 0 && (
        <>
          <div className="segmented segmented-small insights-windows" role="group" aria-label="Count by">
            {MAKEUP_FIELDS.map((k) => (
              <button key={k} className={k === field ? 'is-on' : ''} aria-pressed={k === field} onClick={() => setField(k)}>{FIELD_WORDS[k]}</button>
            ))}
          </div>
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
