import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { api } from '../api';
import { LinkIcon, SearchIcon } from '../components/Icons';
import { Button, buttonClass, Card, Notice } from '../components/ui';
import type { Wish } from '../gaps';
import {
  dropWords, type Find, LINK_PROBLEM, linkIn, linkLine, priceWords, rangeWords, runDoneWords, runWords, shopPoll, typedPrice,
  webLink,
} from '../shop';
import { aboutUsd } from '../spend';
import { queryKeys } from '../queryKeys';
import { useApp } from '../store';
import { verdictTone } from '../wouldwork';

const DEMO_TITLE = 'The demo closet never sends anything to Claude, so it cannot search shops';

type PriceChange = { price_min: number | null; price_max: number | null; price_currency: string | null };

/**
 * The box for a product page's address: on the wishlist (a new wish made from it), on a wish's page (a find added to
 * it) and on the page a shared link opens. Nothing is added until its button is pressed. `onSubmit` gives back the
 * sentence to show when the link was not taken, or null.
 */
export function LinkForm({ initial = '', submit, busy, locked, lockedTitle, onSubmit, onCancel, autoFocus = true }: {
  initial?: string; submit: string; busy: boolean; locked: boolean; lockedTitle?: string;
  onSubmit(url: string): Promise<string | null>; onCancel(): void; autoFocus?: boolean;
}) {
  const [text, setText] = useState(initial);
  const [problem, setProblem] = useState<string | null>(null);
  const hint = useId();
  async function send(e: FormEvent) {
    e.preventDefault();
    const url = linkIn(text);
    if (!url) return setProblem(LINK_PROBLEM);
    setProblem(null);
    setProblem(await onSubmit(url));
  }
  return (
    <form className="wish-add wish-link" onSubmit={send} noValidate aria-label="Add a link">
      <label className="field">
        <span>The address of a product's page</span>
        <input type="url" inputMode="url" value={text} onChange={(e) => setText(e.target.value)} placeholder="https://…"
          autoComplete="off" autoCapitalize="off" spellCheck={false} autoFocus={autoFocus} aria-describedby={hint} />
      </label>
      <p className="hint wish-link-hint" id={hint}>Nines reads its name and price, then checks the price once a day.</p>
      {problem && <p className="form-error" role="alert">{problem}</p>}
      <div className="row">
        <button className="btn btn-primary btn-small" type="submit" disabled={busy || locked || !text.trim()}
          title={locked ? lockedTitle : undefined}>{submit}</button>
        <button className="btn btn-ghost btn-small" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** On a wish: its price range, "Find some", "Add a link", the products kept and how each would work with the closet. */
export function WishShop({ wish, locked, onPrice }: { wish: Wish; locked: boolean; onPrice(w: Wish, changes: PriceChange): Promise<boolean> }) {
  const { toast } = useApp();
  const qc = useQueryClient();
  const key = queryKeys.finds(wish.id);
  const [linking, setLinking] = useState(false);
  // Asked again every few seconds while a search, a price check or a link's reading runs, and not at all otherwise;
  // never while the page is hidden. Reading never starts one: only the owner does, below.
  const answer = useQuery({
    queryKey: key, queryFn: () => api.finds(wish.id), enabled: !locked,
    refetchInterval: (q) => shopPoll(q.state.data),
  }).data ?? null;
  // Starting a search or a price check asks Claude (it costs money): only ever by the owner's tap.
  const begin = useMutation({
    mutationFn: (kind: 'find' | 'prices') => (kind === 'find' ? api.findSome(wish.id) : api.checkPrices(wish.id)),
    onSuccess: (a) => qc.setQueryData(key, a),
  });
  const addLink = useMutation({ mutationFn: (url: string) => api.addLinkTo(wish.id, url), onSuccess: (a) => qc.setQueryData(key, a) });
  const starting = begin.isPending || addLink.isPending;
  const error = begin.error ? begin.error.message : null;
  const running = answer?.run?.state === 'running';
  const wasRunning = useRef(false);

  useEffect(() => {
    const run = answer?.run;
    if (wasRunning.current && run && run.state !== 'running') {
      toast(runDoneWords(run, wish.name), run.state === 'failed' ? 'error' : undefined);
      // the wish's name (a link names it) and its row's price may have changed
      void qc.invalidateQueries({ queryKey: queryKeys.wishlist() });
    }
    wasRunning.current = run?.state === 'running';
  }, [answer, toast, wish.name, qc]);

  function start(kind: 'find' | 'prices') {
    begin.mutate(kind);
  }

  async function remove(f: Find) {
    try {
      await api.removeFind(wish.id, f.id);
      // only this wish's finds changed
      await qc.invalidateQueries({ queryKey: key, exact: true });
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }

  const finds = answer?.finds ?? [];
  const demo = answer?.demo ?? false;
  const busy = locked || starting || running || !answer;
  const disabled = busy || demo;
  // in the demo closet only the pages sent as links can have their prices checked: Nines reads them, Claude is not asked
  const pricesOff = busy || (demo && !finds.some((f) => f.link));
  const title = demo ? DEMO_TITLE : undefined;
  const run = answer?.run;
  return (
    <section className="wish-shop" aria-label={`Shopping for ${wish.name}`}>
      <PriceRange wish={wish} locked={locked} onPrice={onPrice} />
      <div className="row wish-shop-actions">
        <Button small data-testid="find-some" disabled={disabled} title={title} onClick={() => start('find')}>
          <SearchIcon /> {finds.length ? 'Find more' : 'Find some'}
        </Button>
        {finds.length > 0 && (
          <Button variant="ghost" small data-testid="check-prices" disabled={pricesOff} title={pricesOff ? title : undefined}
            onClick={() => start('prices')}>Check prices</Button>
        )}
        {!linking && (
          <Button variant="ghost" small data-testid="add-link" disabled={busy} onClick={() => setLinking(true)}>
            <LinkIcon /> Add a link
          </Button>
        )}
      </div>
      {linking && (
        <LinkForm submit="Add to this wish" busy={starting || running} locked={locked} onCancel={() => setLinking(false)}
          onSubmit={async (url) => {
            try {
              await addLink.mutateAsync(url);
              setLinking(false);
              return null;
            } catch (e) {
              return (e as Error).message;
            }
          }} />
      )}
      {demo && <p className="muted wish-shop-line">The demo closet never searches shops. Open your own closet to look for this.</p>}
      {answer && !demo && answer.estimate.api && (
        <p className="muted wish-shop-line">
          If your plan can't be used, a search costs {aboutUsd(answer.estimate.find_usd)} at most with the API key
          {finds.length > 0 ? `, and a price check ${aboutUsd(answer.estimate.prices_usd)}` : ''}.
        </p>
      )}
      {running && (
        <Notice as="p" role="status" className="wish-shop-notice" icon={<span className="spinner" aria-hidden="true" />}>
          {runWords(run!)}
        </Notice>
      )}
      {!running && run?.message && (run.state === 'failed'
        ? <Notice as="p" tone="error" role="status" className="wish-shop-notice">{run.message}</Notice>
        : <p className="muted wish-shop-line" role="status">{run.message}</p>)}
      {error && <Notice as="p" tone="error" role="alert" className="wish-shop-notice">{error}</Notice>}
      {finds.length > 0 && (
        <>
          <ul className="find-list" aria-label="Found in shops">
            {finds.map((f) => <li key={f.id}><FindCard find={f} locked={locked} onRemove={() => void remove(f)} /></li>)}
          </ul>
          {answer?.prices_checked_at && <p className="muted wish-shop-line">Prices last checked {new Date(answer.prices_checked_at).toLocaleString()}.</p>}
          <p className="muted wish-shop-line">Nothing is ever bought for you. Prices are checked again once a day while Nines is running.</p>
        </>
      )}
    </section>
  );
}

function FindCard({ find, locked, onRemove }: { find: Find; locked: boolean; onRemove(): void }) {
  const link = webLink(find.url);
  const image = webLink(find.image_url);
  const tone = find.verdict ? verdictTone(find.verdict) : 'plain';
  const sent = linkLine(find);
  return (
    <Card as="article" className="find-card" data-testid="find" aria-label={find.name} data-verdict={find.verdict ?? ''}>
      {image && <img className="find-image" src={image} alt="" loading="lazy" referrerPolicy="no-referrer" />}
      <div className="find-body">
        <h4>{find.name}</h4>
        <p className="find-shop">
          {find.shop} · <strong>{priceWords(find.price, find.currency)}</strong>
          {!find.available && <span className="find-sold"> · Sold out</span>}
        </p>
        {find.drop && <p className="find-drop" data-testid="find-drop">{dropWords(find.drop)}</p>}
        {find.verdict_words && <p className={`find-verdict is-${tone}`} data-testid="find-verdict">{find.verdict_words}</p>}
        {find.reasons.length > 0 && (
          <ul className="gap-why find-reasons" aria-label="Why">
            {find.reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
        )}
        {find.piece_words && <p className="muted find-piece">Claude saw: {find.piece_words}</p>}
        {sent && <p className="muted find-piece" data-testid="find-link">{sent}</p>}
        <div className="row">
          {link && <a className={buttonClass({ small: true })} href={link} target="_blank" rel="noopener noreferrer">Open in shop</a>}
          <Button variant="ghost" small disabled={locked} onClick={onRemove}>Remove</Button>
        </div>
      </div>
    </Card>
  );
}

function PriceRange({ wish, locked, onPrice }: { wish: Wish; locked: boolean; onPrice(w: Wish, changes: PriceChange): Promise<boolean> }) {
  const [open, setOpen] = useState(false);
  const [low, setLow] = useState('');
  const [high, setHigh] = useState('');
  const [currency, setCurrency] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const id = useId();
  const words = rangeWords(wish);

  function edit() {
    setLow(wish.price_min != null ? String(wish.price_min) : '');
    setHigh(wish.price_max != null ? String(wish.price_max) : '');
    setCurrency(wish.price_currency ?? 'USD');
    setProblem(null);
    setOpen(true);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    const min = typedPrice(low);
    const max = typedPrice(high);
    const cur = currency.trim().toUpperCase();
    if (min === undefined || max === undefined) return setProblem('Type a price as a number, like 80 or 120.50.');
    if (min !== null && max !== null && min > max) return setProblem('The lowest price must not be more than the highest.');
    if (!/^[A-Z]{3}$/.test(cur)) return setProblem('The currency is three letters, like USD, EUR or GBP.');
    const none = min === null && max === null;
    if (await onPrice(wish, { price_min: min, price_max: max, price_currency: none ? null : cur })) setOpen(false);
  }

  if (!open) {
    return (
      <p className="wish-price">
        <span className="muted">Price range: </span>{words || <span className="muted">any</span>}{' '}
        <Button variant="link" small disabled={locked} onClick={edit}>{words ? 'Change' : 'Set one'}</Button>
      </p>
    );
  }
  return (
    <form className="wish-price-form" onSubmit={save} aria-label="Price range">
      <label className="field">
        <span>From</span>
        <input id={`${id}-min`} inputMode="decimal" value={low} onChange={(e) => setLow(e.target.value)} placeholder="any" />
      </label>
      <label className="field">
        <span>To</span>
        <input id={`${id}-max`} inputMode="decimal" value={high} onChange={(e) => setHigh(e.target.value)} placeholder="any" />
      </label>
      <label className="field wish-currency">
        <span>Currency</span>
        <input value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value)} />
      </label>
      {problem && <p className="form-error" role="alert">{problem}</p>}
      <div className="row">
        <Button variant="primary" small type="submit" disabled={locked}>Save price range</Button>
        <Button variant="ghost" small onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </form>
  );
}
