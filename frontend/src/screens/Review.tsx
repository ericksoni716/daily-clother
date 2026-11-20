import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { ChipGroup } from '../components/ui/Chips';
import { Button, EmptyState, PageHeader } from '../components/ui';
import { CloudOffIcon, HangerIcon } from '../components/Icons';
import { FIELD_TITLES, label } from '../labels';
import { notReadyText, progressText, reviewChanges, reviewRows, skippedText, sureText, type ReviewRow } from '../review';
import { itemSaved, itemsQuery, reviewQuery } from '../queries';
import { queryKeys } from '../queryKeys';
import { itemPath, Link, useMediaQuery } from '../router';
import { useApp } from '../store';
import type { ItemSummary, ReviewItem, ReviewQueue } from '../types';
import './Review.css';

// ------------------------------------------------------------ the badge
/** "id:tag_state" for every item: the review queue changes when a description arrives, fails or is asked again. */
const tagStates = (list: ItemSummary[]) => list.map((i) => `${i.id}:${i.tag_state}`).join(',');

/**
 * The number of items waiting for review; null until known. Asked again after an edit that touches the queue (see
 * `TOUCHES`) and when an item's description changes state, not on every move between screens.
 */
export function useReviewCount(): number | null {
  const { offline } = useApp();
  const qc = useQueryClient();
  const count = useQuery({ ...reviewQuery(), enabled: !offline, select: (q) => q.count }).data;
  const states = useQuery({ ...itemsQuery('active'), enabled: false, select: tagStates }).data;
  const seen = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (states === undefined) return;
    if (seen.current !== undefined && seen.current !== states) void qc.invalidateQueries({ queryKey: queryKeys.review() });
    seen.current = states;
  }, [states, qc]);
  return count ?? null;
}

/** What a screen reader hears after a link that leads to the review queue. */
export function reviewCountText(count: number): string {
  return ` (${count} ${count === 1 ? 'item' : 'items'} to review)`;
}

/**
 * The number beside a link that leads to the review queue (nothing when there is nothing to review).
 * `quiet`: only shown, because another link nearby already says it.
 */
export function ReviewBadge({ count, quiet = false }: { count: number | null; quiet?: boolean }) {
  if (!count) return null;
  return (
    <>
      <span className="nav-badge" data-testid="review-badge" aria-hidden="true">{count > 99 ? '99+' : count}</span>
      {!quiet && <span className="visually-hidden">{reviewCountText(count)}</span>}
    </>
  );
}

// ------------------------------------------------------------ the screen
export function ReviewScreen() {
  const { offline } = useApp();
  const review = useQuery({ ...reviewQuery(), enabled: !offline });
  const { refetch } = review;
  // The queue as it was when the screen opened, kept while it is worked through: each confirmed piece makes the
  // shared query read again behind it (the badge follows), which must not move the card.
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [index, setIndex] = useState(0);
  const [skipped, setSkipped] = useState(0);
  if (offline && queue) setQueue(null);   // back online, it is taken afresh
  else if (!offline && !queue && review.data && !review.isFetching) setQueue(review.data);
  const error = review.error ? review.error.message : null;

  const load = useCallback(async () => {
    const r = await refetch();
    if (!r.data) return;
    setQueue(r.data);
    setIndex(0);
    setSkipped(0);
  }, [refetch]);

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
        body="It needs Nines on your computer to be reachable. This page carries on by itself once it is." />
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
      <PageHeader title="Review" titleId="review-title" countTestId="review-progress" back={{ to: '/', label: 'Closet' }}
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

/** A computer with a mouse or a trackpad, where the keys on the card can be used. */
const KEYBOARD = '(hover: hover) and (pointer: fine)';

function ReviewCard({ item, onDone, onSkip }: { item: ReviewItem; onDone(): void; onSkip(): void }) {
  const { toast } = useApp();
  const qc = useQueryClient();
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
      if (saved) itemSaved(qc, saved);
      toast(Object.keys(changes).length ? 'Saved your changes' : 'Confirmed');
      onDone();
    } catch (e) {
      toast((e as Error).message, 'error');
      setBusy(false);
    }
  }, [busy, rows, chosen, item.id, qc, toast, onDone]);

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

  // the keys are said only where there is a keyboard and a mouse: never on a phone
  const keys = useMediaQuery(KEYBOARD);
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
        {keys && <p className="muted review-keys">
          On a computer: <kbd>←</kbd> <kbd>→</kbd> or <kbd>1</kbd>–<kbd>9</kbd> to choose{rows.length > 1 ? <>, <kbd>↑</kbd> <kbd>↓</kbd> for the next field</> : null}, <kbd>Enter</kbd> for “That's right”, <kbd>S</kbd> to skip.
        </p>}
      </div>
    </article>
  );
}
