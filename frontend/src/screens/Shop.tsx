import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { api, ApiError } from '../api';
import { SearchIcon } from '../components/Icons';
import { Button, buttonClass, Card, Notice } from '../components/ui';
import type { Wish } from '../gaps';
import { dropWords, type Find, type FindsAnswer, priceWords, rangeWords, SHOP_POLL_MS, typedPrice, webLink } from '../shop';
import { aboutUsd } from '../spend';
import { useCloset } from '../store';
import { verdictTone } from '../wouldwork';

const DEMO_TITLE = 'The demo closet never sends anything to Claude, so it cannot search shops';

type PriceChange = { price_min: number | null; price_max: number | null; price_currency: string | null };

/** On a wish: its price range, "Find some", the products kept and how each would work with the closet. */
export function WishShop({ wish, locked, onPrice }: { wish: Wish; locked: boolean; onPrice(w: Wish, changes: PriceChange): Promise<boolean> }) {
  const { toast } = useCloset();
  const [answer, setAnswer] = useState<FindsAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const running = answer?.run?.state === 'running';
  const wasRunning = useRef(false);

  const load = useCallback(async () => {
    try {
      const a = await api.finds(wish.id);
      setAnswer(a);
      return a;
    } catch {
      return null;
    }
  }, [wish.id]);

  useEffect(() => {
    if (!locked) void load();
  }, [load, locked]);

  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => void load(), SHOP_POLL_MS);
    return () => window.clearInterval(t);
  }, [running, load]);

  useEffect(() => {
    const run = answer?.run;
    if (wasRunning.current && run && run.state !== 'running') {
      if (run.state === 'failed') toast(run.message ?? 'Something went wrong while looking.', 'error');
      else if (run.kind === 'find') toast(run.added ? `Found ${run.added} new for “${wish.name}”` : (run.message ?? 'Nothing new found'));
      else toast(run.message ?? 'Prices checked');
    }
    wasRunning.current = run?.state === 'running';
  }, [answer, toast, wish.name]);

  async function start(kind: 'find' | 'prices') {
    setStarting(true);
    setError(null);
    try {
      setAnswer(kind === 'find' ? await api.findSome(wish.id) : await api.checkPrices(wish.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  async function remove(f: Find) {
    try {
      await api.removeFind(wish.id, f.id);
      await load();
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }

  const finds = answer?.finds ?? [];
  const demo = answer?.demo ?? false;
  const disabled = locked || starting || running || demo || !answer;
  const title = demo ? DEMO_TITLE : undefined;
  const run = answer?.run;
  return (
    <section className="wish-shop" aria-label={`Shopping for ${wish.name}`}>
      <PriceRange wish={wish} locked={locked} onPrice={onPrice} />
      <div className="row wish-shop-actions">
        <Button small data-testid="find-some" disabled={disabled} title={title} onClick={() => void start('find')}>
          <SearchIcon /> {finds.length ? 'Find more' : 'Find some'}
        </Button>
        {finds.length > 0 && (
          <Button variant="ghost" small data-testid="check-prices" disabled={disabled} title={title}
            onClick={() => void start('prices')}>Check prices</Button>
        )}
      </div>
      {demo && <p className="muted wish-shop-line">The demo closet never searches shops. Open your own closet to look for this.</p>}
      {answer && !demo && answer.estimate.api && (
        <p className="muted wish-shop-line">
          If your plan can't be used, a search costs {aboutUsd(answer.estimate.find_usd)} at most with the API key
          {finds.length > 0 ? `, and a price check ${aboutUsd(answer.estimate.prices_usd)}` : ''}.
        </p>
      )}
      {running && (
        <Notice as="p" role="status" className="wish-shop-notice" icon={<span className="spinner" aria-hidden="true" />}>
          {run!.kind === 'find' ? 'Claude is searching shops. This can take a few minutes…' : 'Claude is checking the prices…'}
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
          <p className="muted wish-shop-line">Nothing is ever bought for you. Prices are checked again once a day while Closet is running.</p>
        </>
      )}
    </section>
  );
}

function FindCard({ find, locked, onRemove }: { find: Find; locked: boolean; onRemove(): void }) {
  const link = webLink(find.url);
  const image = webLink(find.image_url);
  const tone = find.verdict ? verdictTone(find.verdict) : 'plain';
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
