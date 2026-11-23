import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useRef, useState, type FormEvent, type RefObject } from 'react';
import { api } from '../api';
import { LinkIcon, SearchIcon } from '../components/Icons';
import { useNewsSeen } from '../components/PriceNews';
import { Button, buttonClass, Card, Notice, Sheet } from '../components/ui';
import type { Wish } from '../gaps';
import {
  checkedWords, dropWords, type Find, findsInOrder, historyWords, lastChecked, LINK_PROBLEM, linkIn, linkLine, priceWords,
  runDoneWords, runWords, searchWords, shopPoll, type ShopRun, typedPrice, watchWords, webLink,
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

/**
 * On a wish, below what to look for: what is watched (the pages you sent, then Claude's finds) with the one sentence
 * about watching, the most you'd pay and Check now; then looking for more ("Find some", "Add a link"). Opening the
 * page tells the server you have seen the wish's price news.
 */
export function WishShop({ wish, locked, onPrice }: { wish: Wish; locked: boolean; onPrice(w: Wish, changes: PriceChange): Promise<boolean> }) {
  const { profile, toast } = useApp();
  const qc = useQueryClient();
  const key = queryKeys.finds(wish.id);
  const [linking, setLinking] = useState(false);
  const seen = useNewsSeen();
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
  const running = answer?.run?.state === 'running';
  const wasRunning = useRef(false);
  const answered = useRef(false);
  const watching = !locked && profile !== 'demo';

  // You are looking at the wish: its price news is seen (on the phone and the computer alike), and again whenever a
  // search or a price check on it ends, since what it found is in front of you.
  useEffect(() => {
    if (watching) seen([wish.id]).catch(() => undefined);
  }, [watching, wish.id, seen]);

  useEffect(() => {
    const run = answer?.run;
    if (wasRunning.current && run && run.state !== 'running') {
      toast(runDoneWords(run, wish.name), run.state === 'failed' ? 'error' : undefined);
      // the wish's name (a link names it) and its row's price may have changed
      void qc.invalidateQueries({ queryKey: queryKeys.wishlist() });
      if (watching) seen([wish.id]).catch(() => undefined);
    } else if (!answered.current && run && run.state !== 'running') {
      // one that ended before the page first asked (a link read in the moment the page took to open): the list may
      // have been read before it ended, so it is asked for again, once
      void qc.invalidateQueries({ queryKey: queryKeys.wishlist() });
    }
    if (answer) answered.current = true;
    wasRunning.current = run?.state === 'running';
  }, [answer, toast, wish.name, wish.id, qc, watching, seen]);

  async function stop(f: Find) {
    try {
      await api.removeFind(wish.id, f.id);
      // only this wish's finds changed
      await qc.invalidateQueries({ queryKey: key, exact: true });
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }

  const finds = findsInOrder(answer?.finds ?? []);
  const demo = answer?.demo ?? false;
  const busy = locked || starting || running || !answer;
  const disabled = busy || demo;
  // in the demo closet only the pages sent as links can have their prices checked: Nines reads them, Claude is not asked
  const pricesOff = busy || (demo && !finds.some((f) => f.link));
  const title = demo ? DEMO_TITLE : undefined;
  const run = answer?.run ?? null;
  // what a run says goes under what started it: a price check (and a link being read) under Check now, a search under
  // Find some; a refusal, under the button that was refused
  const checking = finds.length > 0 && (begin.error ? begin.variables === 'prices' : run !== null && run.kind !== 'find');
  const said = <RunSaid run={run} error={begin.error?.message ?? null} />;
  // the currency the most you'd pay starts in when none is set: the newest find's
  const currency = answer?.finds[0]?.currency;
  // what is watched comes first, so the page waits for it (a moment: Nines is on this computer) before laying out the rest
  if (!answer && !locked) return <div className="missing-skeleton missing-skeleton-small" aria-hidden="true" />;
  return (
    <>
      {finds.length > 0 && (
        <section className="wish-watch" aria-label={`Watching for ${wish.name}`}>
          <ul className="find-list" aria-label="Found in shops">
            {finds.map((f) => <li key={f.id}><FindCard find={f} locked={locked} onStop={() => void stop(f)} /></li>)}
          </ul>
          <PriceLine wish={wish} currency={currency} locked={locked} onPrice={onPrice}>{watchWords(wish)}</PriceLine>
          <p className="muted wish-shop-line" data-testid="prices-checked">
            {checkedWords(lastChecked({ ...answer!, finds }))}{' '}
            <Button variant="link" small className="wish-inline-button" data-testid="check-prices" disabled={pricesOff}
              title={pricesOff ? title : undefined} onClick={() => begin.mutate('prices')}>Check now</Button>
          </p>
          {checking && said}
        </section>
      )}
      <section className="wish-shop" aria-label={`Looking for more for ${wish.name}`}>
        {finds.length === 0 && <PriceLine wish={wish} currency={currency} locked={locked} onPrice={onPrice}>{searchWords(wish)}</PriceLine>}
        <div className="row wish-shop-actions">
          <Button small data-testid="find-some" disabled={disabled} title={title} onClick={() => begin.mutate('find')}>
            <SearchIcon /> {finds.length ? 'Find more' : 'Find some'}
          </Button>
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
        {!checking && said}
      </section>
    </>
  );
}

/** What a search, a price check or a link's reading says: who is reading while it runs, then what came of it. */
function RunSaid({ run, error }: { run: ShopRun | null; error: string | null }) {
  const running = run?.state === 'running';
  return (
    <>
      {running && (
        <Notice as="p" role="status" className="wish-shop-notice" icon={<span className="spinner" aria-hidden="true" />}>
          {runWords(run!)}
        </Notice>
      )}
      {!running && run?.message && (run.state === 'failed'
        ? <Notice as="p" tone="error" role="status" className="wish-shop-notice">{run.message}</Notice>
        : <p className="muted wish-shop-line" role="status">{run.message}</p>)}
      {error && <Notice as="p" tone="error" role="alert" className="wish-shop-notice">{error}</Notice>}
    </>
  );
}

function FindCard({ find, locked, onStop }: { find: Find; locked: boolean; onStop(): void }) {
  const link = webLink(find.url);
  const image = webLink(find.image_url);
  const tone = find.verdict ? verdictTone(find.verdict) : 'plain';
  const sent = linkLine(find);
  const went = historyWords(find.history);
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
        {went && <p className="muted find-piece" data-testid="find-history">{went}</p>}
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
          {/* the find goes, and with it its daily check */}
          <Button variant="ghost" small disabled={locked} onClick={onStop}>Stop watching</Button>
        </div>
      </div>
    </Card>
  );
}

/** A sentence about the price, with the button that opens the most you'd pay in a sheet (a popover under the sentence
 * on a computer). */
function PriceLine({ wish, currency, locked, onPrice, children }: {
  wish: Wish; currency?: string; locked: boolean; onPrice(w: Wish, changes: PriceChange): Promise<boolean>; children: string;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  return (
    <div className="wish-price-line">
      <p className="wish-price" data-testid="wish-price">
        {children}{' '}
        <button ref={button} type="button" className="btn btn-link btn-small wish-inline-button" aria-haspopup="dialog"
          aria-expanded={open} disabled={locked} onClick={() => setOpen(!open)}>
          {wish.price_max != null ? 'Change' : "Set the most you'd pay"}
        </button>
      </p>
      {open && <PriceSheet wish={wish} currency={currency} keep={button} onPrice={onPrice} onClose={() => setOpen(false)} />}
    </div>
  );
}

/** The most you'd pay, and its currency: Save, Clear (when one is set), and Cancel beside the title. No lower limit:
 * saving clears one an older wish may still have. */
function PriceSheet({ wish, currency: newest, keep, onPrice, onClose }: {
  wish: Wish; currency?: string; keep: RefObject<HTMLButtonElement | null>; onPrice(w: Wish, changes: PriceChange): Promise<boolean>;
  onClose(): void;
}) {
  const [amount, setAmount] = useState(wish.price_max != null ? String(wish.price_max) : '');
  const [currency, setCurrency] = useState(wish.price_currency ?? newest ?? 'USD');
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const hint = useId();

  async function send(changes: PriceChange) {
    setSaving(true);
    try {
      if (await onPrice(wish, changes)) onClose();
    } finally {
      setSaving(false);
    }
  }

  function save(e: FormEvent) {
    e.preventDefault();
    const most = typedPrice(amount);
    const cur = currency.trim().toUpperCase();
    if (most === undefined) return setProblem('Type a price as a number, like 80 or 120.50.');
    if (!/^[A-Z]{3}$/.test(cur)) return setProblem('The currency is three letters, like USD, EUR or GBP.');
    setProblem(null);
    void send({ price_min: null, price_max: most, price_currency: most === null ? null : cur });
  }

  return (
    <Sheet title="The most you'd pay" popover keep={keep} closeLabel="Cancel" className="wish-price-sheet" testId="price-sheet" onClose={onClose}>
      <form onSubmit={save} noValidate aria-label="The most you'd pay" aria-describedby={hint}>
        <p className="hint" id={hint}>Nines tells you when a price here goes down to this or less, and Claude looks for ones that cost no more.</p>
        <div className="wish-price-fields">
          <label className="field">
            <span>Amount</span>
            <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 150" autoFocus />
          </label>
          <label className="field wish-currency">
            <span>Currency</span>
            <input value={currency} maxLength={3} autoCapitalize="characters" onChange={(e) => setCurrency(e.target.value)} />
          </label>
        </div>
        {problem && <p className="form-error" role="alert">{problem}</p>}
        <div className="row">
          <Button variant="primary" small type="submit" disabled={saving}>Save</Button>
          {(wish.price_max != null || wish.price_min != null) && (
            <Button variant="ghost" small disabled={saving}
              onClick={() => void send({ price_min: null, price_max: null, price_currency: null })}>Clear</Button>
          )}
        </div>
      </form>
    </Sheet>
  );
}
