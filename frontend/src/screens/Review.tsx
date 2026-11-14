import { useCallback, useEffect, useMemo, useState, useSyncExternalStore, type SVGProps } from 'react';
import { api, ApiError } from '../api';
import { ChipGroup } from '../components/ui/Chips';
import { Button, EmptyState, PageHeader } from '../components/ui';
import { CloudOffIcon, HangerIcon } from '../components/Icons';
import { FIELD_TITLES, label } from '../labels';
import { notReadyText, progressText, reviewChanges, reviewRows, skippedText, sureText, type ReviewRow } from '../review';
import { itemPath, Link, usePath } from '../router';
import { useCloset } from '../store';
import type { Profile, ReviewItem, ReviewQueue } from '../types';
import './Review.css';

export const ReviewIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true" {...p}>
    <path d="M20 11.5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8.5" /><path d="m8.5 11.5 3 3L20 6" />
  </svg>
);

// ------------------------------------------------------------ the badge
// How many items wait for review, per closet; the navigation shows it.
const counts = new Map<Profile, number>();
const listeners = new Set<() => void>();
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};

/** The number of items waiting for review, kept up to date as items change; null until known. */
export function useReviewCount(): number | null {
  const { profile, offline, items } = useCloset();
  const path = usePath();
  const count = useSyncExternalStore(subscribe, () => counts.get(profile) ?? null);
  // asked again whenever an item changes (described, edited, confirmed) and on every move between screens
  const changes = (items.active ?? []).map((i) => `${i.id}:${i.tag_state}:${i.updated_at}`).join(',');
  useEffect(() => {
    if (offline) return;
    let live = true;
    api.review().then((q) => {
      if (!live) return;
      counts.set(profile, q.count);
      listeners.forEach((l) => l());
    }).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [profile, offline, changes, path]);
  return count;
}

/** The number on the Review link (nothing when there is nothing to review). */
export function ReviewBadge({ count }: { count: number | null }) {
  if (!count) return null;
  return (
    <>
      <span className="nav-badge" data-testid="review-badge" aria-hidden="true">{count > 99 ? '99+' : count}</span>
      <span className="visually-hidden"> ({count} {count === 1 ? 'item' : 'items'} to review)</span>
    </>
  );
}

// ------------------------------------------------------------ the screen
export function ReviewScreen() {
  const { offline } = useCloset();
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [skipped, setSkipped] = useState(0);

  const load = useCallback(async () => {
    try {
      const q = await api.review();
      setQueue(q);
      setIndex(0);
      setSkipped(0);
      setError(null);
    } catch (e) {
      setError((e as ApiError).message);
    }
  }, []);

  useEffect(() => {
    if (!offline) void load();
  }, [offline, load]);

  const next = useCallback((didSkip: boolean) => {
    if (!queue) return;
    const left = skipped + (didSkip ? 1 : 0);
    setSkipped(left);
    setIndex(index + 1);
    if (index + 1 >= queue.items.length && left === 0) void load();   // all done: look again, in case more were described meanwhile
  }, [queue, index, skipped, load]);

  const total = queue?.items.length ?? 0;
  const current = queue && index < total ? queue.items[index] : null;

  let body;
  if (offline) {
    body = (
      <EmptyState big icon={<CloudOffIcon />} title="Reviewing is unavailable offline"
        body="It needs Closet on your computer to be reachable. This page carries on by itself once it is." />
    );
  } else if (current) {
    body = <ReviewCard key={current.id} item={current} onDone={() => next(false)} onSkip={() => next(true)} />;
  } else if (!queue || (total > 0 && skipped === 0)) {
    body = error ? <p className="form-error" role="alert">{error}</p> : <div className="detail-picture tile-skeleton review-skeleton" aria-busy="true" />;
  } else if (total > 0) {
    body = (
      <EmptyState big testId="review-end" title="That's all for now" body={skippedText(skipped)}
        action={<Button onClick={() => void load()}>Look at the skipped ones again</Button>} />
    );
  } else {
    body = <NothingToReview queue={queue} />;
  }

  return (
    <section className="review" aria-labelledby="review-title">
      <PageHeader title="Review" titleId="review-title" countTestId="review-progress"
        count={!offline && current && progressText(index + 1, total)} />
      {body}
    </section>
  );
}

function NothingToReview({ queue }: { queue: ReviewQueue }) {
  const others = [...queue.failed_items, ...queue.waiting_items];
  const shown = others.slice(0, 8);
  const name = (o: { name: string | null; category: string | null }) => o.name || label('category', o.category) || 'New item';
  return (
    <EmptyState big testId="review-empty" icon={<HangerIcon />} title="Nothing to review"
      body="Claude was sure of everything it described, or you have already checked it.">
      {others.length > 0 && (
        <div className="review-others">
          <p data-testid="review-not-ready">{notReadyText(queue.waiting, queue.failed)}</p>
          <ul>
            {shown.map((o) => (
              <li key={o.id}>
                <Link to={itemPath(o.id, 'active')}>{name(o)}</Link>
                {queue.failed_items.includes(o) && <span className="muted"> · couldn't be described</span>}
              </li>
            ))}
          </ul>
          {others.length > shown.length && <Link to="/">and {others.length - shown.length} more in your closet</Link>}
        </div>
      )}
    </EmptyState>
  );
}

function ReviewCard({ item, onDone, onSkip }: { item: ReviewItem; onDone(): void; onSkip(): void }) {
  const { upsert, toast } = useCloset();
  const rows = useMemo(() => reviewRows(item.fields), [item.fields]);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const name = item.name || label('category', item.category) || 'Item';

  const choose = useCallback((row: ReviewRow, value: string) => setChosen((c) => ({ ...c, [row.key]: value })), []);

  const confirm = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    const { changes, confirm: keep } = reviewChanges(rows, chosen);
    try {
      let saved = Object.keys(changes).length ? await api.patch(item.id, changes) : null;
      if (keep.length) saved = await api.confirm(item.id, keep);
      if (saved) upsert(saved);
      toast(Object.keys(changes).length ? 'Saved your changes' : 'Confirmed');
      onDone();
    } catch (e) {
      toast((e as Error).message, 'error');
      setBusy(false);
    }
  }, [busy, rows, chosen, item.id, upsert, toast, onDone]);

  // On a computer: up and down move between fields, left and right (or 1–9) choose, Enter confirms, S skips.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || busy) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest('input, textarea, select, a, summary')) return;
      // a focused button outside the choices (Skip, the navigation) keeps its own Enter and space
      const onOtherButton = !!target?.closest('button') && !target.closest('.review-fields');
      const row = rows[Math.min(active, rows.length - 1)];
      const current = row ? (chosen[row.key] ?? row.value) : '';
      const step = (by: number) => {
        if (!row) return;
        const at = row.options.indexOf(current);
        choose(row, row.options[(at + by + row.options.length) % row.options.length]);
      };
      if (e.key === 'Enter' && !onOtherButton) {
        e.preventDefault();
        void confirm();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        step(1);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        step(-1);
      } else if (e.key === 'ArrowDown' && rows.length > 1) {
        e.preventDefault();
        setActive((a) => Math.min(a + 1, rows.length - 1));
      } else if (e.key === 'ArrowUp' && rows.length > 1) {
        e.preventDefault();
        setActive((a) => Math.max(a - 1, 0));
      } else if (/^[1-9]$/.test(e.key) && row) {
        const option = row.options[Number(e.key) - 1];
        if (option) choose(row, option);
      } else if ((e.key === 's' || e.key === 'S') && !onOtherButton) {
        onSkip();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [rows, active, chosen, busy, choose, confirm, onSkip]);

  const pictureClass = item.picture_kind === 'cutout' ? 'pic-cutout' : item.picture_kind === 'photo' ? 'pic-photo-full' : 'pic-illustration';

  return (
    <article className="review-card" aria-label={name} data-testid="review-card">
      <div className={`detail-picture review-picture view-${item.picture_kind ?? 'none'}`}>
        {item.picture_url
          ? <img className={pictureClass} src={item.picture_url} alt={name} />
          : <div className="pic-placeholder" role="img" aria-label={name}><HangerIcon /></div>}
      </div>
      <div className="review-body">
        <h2 className="review-name">{name}</h2>
        <p className="muted">Claude wasn't sure about {rows.length === 1 ? 'this' : 'these'}. Its guess is chosen; tap another if it's wrong.</p>
        <div className="review-fields">
          {rows.map((r, i) => (
            <div key={r.key} className={`review-field${i === active && rows.length > 1 ? ' is-active' : ''}`} data-testid="review-field"
              onFocusCapture={() => setActive(i)} onPointerDown={() => setActive(i)}>
              <ChipGroup field={r.part ?? r.field} options={r.options} value={chosen[r.key] ?? r.value} clearable={false}
                swatches={r.field === 'color'} disabled={busy} title={FIELD_TITLES[r.part ?? r.field] ?? r.field}
                onChange={(v) => v && choose(r, v)} />
              <p className="review-sure">{sureText(r.confidence)}</p>
            </div>
          ))}
        </div>
        <div className="row review-actions">
          <button className="btn btn-primary" disabled={busy} onClick={() => void confirm()}>That's right</button>
          <button className="btn" disabled={busy} onClick={onSkip}>Skip for now</button>
        </div>
        <p className="muted review-keys">
          On a computer: <kbd>←</kbd> <kbd>→</kbd> or <kbd>1</kbd>–<kbd>9</kbd> to choose{rows.length > 1 ? <>, <kbd>↑</kbd> <kbd>↓</kbd> for the next field</> : null}, <kbd>Enter</kbd> for “That's right”, <kbd>S</kbd> to skip.
        </p>
      </div>
    </article>
  );
}
