import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type RefObject } from 'react';
import { api } from '../api';
import { LinkIcon, SearchIcon } from '../components/Icons';
import { useNewsSeen } from '../components/PriceNews';
import { SeeItWorn } from '../components/WornWith';
import { Button, buttonClass, Card, Failed, Notice, SegmentedControl, Sheet } from '../components/ui';
import type { Wish } from '../gaps';
import { touch, useItems } from '../queries';
import {
  canSeeWorn, checkedWords, codeFromWords, codeWords, dropWords, type Find, type FindsAnswer, findsInOrder, withStopped, googleShoppingLink,
  historyWords, lastChecked, LINK_PROBLEM, linkIn, linkLine, notJudgedWords, priceWords, runDoneWords, runWords, searchWords, shopPoll,
  type ShopRun, typedCode, watchWords, webLink, wishlistAgain,
} from '../shop';
import { SEARCH_SENDS } from '../shop';
import { aboutUsd, PRICE_HINT, readAmount } from '../spend';
import { queryKeys } from '../queryKeys';
import { useApp } from '../store';
import type { ItemSummary } from '../types';
import { drawnFromWords, verdictTone, wornError } from '../wouldwork';
import './Shop.css';

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
  const items = useItems().data;
  const byId = useMemo(() => new Map((items ?? []).map((i) => [i.id, i])), [items]);
  // Asked again every few seconds while a search, a price check or a link's reading runs, and not at all otherwise;
  // never while the page is hidden. Reading never starts one: only the owner does, below.
  const read = useQuery({
    queryKey: key, queryFn: () => api.finds(wish.id), enabled: !locked,
    refetchInterval: (q) => shopPoll(q.state.data),
  });
  const answer = read.data ?? null;
  // Starting a search or a price check asks Claude (it costs money): only ever by the owner's tap.
  const begin = useMutation({
    mutationFn: (kind: 'find' | 'prices') => (kind === 'find' ? api.findSome(wish.id) : api.checkPrices(wish.id)),
    onSuccess: (a) => qc.setQueryData(key, a),
  });
  const addLink = useMutation({ mutationFn: (url: string) => api.addLinkTo(wish.id, url), onSuccess: (a) => qc.setQueryData(key, a) });
  const starting = begin.isPending || addLink.isPending;
  const running = answer?.run?.state === 'running';
  const lastRun = useRef<Pick<ShopRun, 'state' | 'step'> | null>(null);
  const answered = useRef(false);
  const watching = !locked && profile !== 'demo';

  // You are looking at the wish: its price news is seen (on the phone and the computer alike), and again whenever a
  // search or a price check on it ends, since what it found is in front of you.
  useEffect(() => {
    if (watching) seen([wish.id]).catch(() => undefined);
  }, [watching, wish.id, seen]);

  useEffect(() => {
    if (!answer) return;
    const run = answer.run;
    // the wish's name (a link's page names it) and its row's price may have changed: asked for again as soon as the
    // pages are read, not only when the run ends (src/shop.ts, wishlistAgain)
    if (wishlistAgain(answered.current ? lastRun.current : undefined, run)) {
      void qc.invalidateQueries({ queryKey: queryKeys.wishlist() });
    }
    if (lastRun.current?.state === 'running' && run && run.state !== 'running') {
      toast(runDoneWords(run, wish.name), run.state === 'failed' ? 'error' : undefined);
      if (watching) seen([wish.id]).catch(() => undefined);
    }
    answered.current = true;
    lastRun.current = run ? { state: run.state, step: run.step } : null;
  }, [answer, toast, wish.name, wish.id, qc, watching, seen]);

  // the finds you stopped watching on this visit: each stays in its place, with Undo, until you leave the page
  const [stopped, setStopped] = useState<{ find: Find; at: number }[]>([]);
  async function stop(f: Find, at: number) {
    try {
      await api.removeFind(wish.id, f.id);
      setStopped((was) => [...was.filter((s) => s.find.id !== f.id), { find: f, at }]);
      // only this wish's finds changed
      await qc.invalidateQueries({ queryKey: key, exact: true });
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }
  async function undoStop(f: Find) {
    try {
      qc.setQueryData(key, await api.restoreFind(wish.id, f.id));
      setStopped((was) => was.filter((s) => s.find.id !== f.id));
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }

  const listed = findsInOrder(answer?.finds ?? []);
  const finds = withStopped(listed, stopped);
  const isStopped = (f: Find) => stopped.some((s) => s.find.id === f.id) && !listed.some((l) => l.id === f.id);
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
  if (!answer && !locked) {
    return read.error ? <Failed query={read} what="what is watched for this wish" />
      : <div className="missing-skeleton missing-skeleton-small" aria-hidden="true" />;
  }
  return (
    <>
      <Failed query={read} what="what is watched for this wish" />
      {finds.length > 0 && (
        <section className="wish-watch" aria-label={`Watching for ${wish.name}`}>
          <ul className="find-list" aria-label="Found in shops">
            {finds.map((f, i) => (
              <li key={f.id}>
                <FindCard find={f} demo={demo} locked={locked} byId={byId} stopped={isStopped(f)}
                  onStop={() => void stop(f, i)} onUndo={() => void undoStop(f)} />
              </li>
            ))}
          </ul>
          <PriceLine wish={wish} currency={currency} locked={locked} onPrice={onPrice}>{watchWords(wish)}</PriceLine>
          <p className="muted wish-shop-line" data-testid="prices-checked">
            {checkedWords(lastChecked({ ...answer!, finds: listed }))}{' '}
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
        <p className="wish-shop-line">
          <a className={buttonClass({ variant: 'link', small: true, className: 'wish-inline-button' })} data-testid="google-shopping"
            href={googleShoppingLink(wish)} target="_blank" rel="noopener noreferrer">Search Google Shopping</a>
        </p>
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
        {!demo && <p className="muted wish-shop-line" data-testid="search-sends">{SEARCH_SENDS}</p>}
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

function FindCard({ find, demo, locked, byId, stopped, onStop, onUndo }: {
  find: Find; demo: boolean; locked: boolean; byId: Map<string, ItemSummary>;
  /** you stopped watching it on this visit: it stays, saying so, with Undo where its buttons were */
  stopped: boolean;
  onStop(): void;
  onUndo(): void;
}) {
  const link = webLink(find.url);
  const image = webLink(find.image_url);
  const tone = find.verdict ? verdictTone(find.verdict) : 'plain';
  const sent = linkLine(find);
  const went = historyWords(find.history);
  const unjudged = notJudgedWords(find, demo);
  return (
    <Card as="article" className="find-card" data-testid="find" aria-label={find.name} data-verdict={find.verdict ?? ''}>
      {image && <img className="find-image" src={image} alt="" loading="lazy" referrerPolicy="no-referrer" />}
      <div className="find-body">
        <h2 className="find-name">{find.name}</h2>
        <p className="find-shop">
          {find.shop} · <strong>{priceWords(find.price, find.currency)}</strong>
          {!find.available && <span className="find-sold"> · Sold out</span>}
        </p>
        <FindCode find={find} locked={locked} />
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
        {unjudged && <p className="muted find-piece" data-testid="find-not-judged">{unjudged}</p>}
        {canSeeWorn(find) && <SeeWorn find={find} image={image} locked={locked} byId={byId} />}
        {stopped ? (
          <p className="find-stopped" role="status" data-testid="find-stopped">
            You stopped watching it, and its daily check.{' '}
            <Button variant="link" small autoFocus disabled={locked} onClick={onUndo}>Undo</Button>
          </p>
        ) : (
          <div className="row">
            {link && <a className={buttonClass({ small: true })} href={link} target="_blank" rel="noopener noreferrer">Open in shop</a>}
            {/* the find goes, and with it its daily check; Undo puts it back as it was */}
            <Button variant="ghost" small disabled={locked} onClick={onStop}>Stop watching</Button>
          </div>
        )}
      </div>
    </Card>
  );
}

/** Under a find's price: its checkout code and the price after it ("$106.20 with code SAVE40 at checkout (40% off)"),
 * who saw it, and the button that opens the code in a sheet (a popover under it on a computer): "Add a code", or
 * "Change the code" when there is one. */
function FindCode({ find, locked }: { find: Find; locked: boolean }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const said = codeWords(find);
  const from = codeFromWords(find.code);
  return (
    <div className="find-code-line">
      {said && <p className="find-code" data-testid="find-code">{said}</p>}
      <p className="muted find-piece find-code-from">
        {from && <span data-testid="find-code-from">{from} </span>}
        <button ref={button} type="button" className="btn btn-link btn-small wish-inline-button" aria-haspopup="dialog"
          aria-expanded={open} disabled={locked} onClick={() => setOpen(!open)}>
          {find.code ? 'Change the code' : 'Add a code'}
        </button>
      </p>
      {open && <CodeSheet find={find} keep={button} onClose={() => setOpen(false)} />}
    </div>
  );
}

/**
 * "See it with your clothes": one quiet button on a judged find's card, opening the outfits made with it, drawn as
 * worn on this computer (nothing is asked of Claude). They are worked out when the sheet opens.
 */
function SeeWorn({ find, image, locked, byId }: { find: Find; image: string | null; locked: boolean; byId: Map<string, ItemSummary> }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const outfits = useQuery({
    queryKey: queryKeys.findOutfits(find.wish_id, find.id), queryFn: () => api.findOutfits(find.wish_id, find.id), enabled: open,
  });
  return (
    <div className="find-worn">
      <button ref={button} type="button" className="btn btn-link btn-small wish-inline-button" data-testid="see-worn"
        aria-haspopup="dialog" aria-expanded={open} disabled={locked && !outfits.data} onClick={() => setOpen(!open)}>
        See it with your clothes
      </button>
      {open && (
        <SeeItWorn title="With your clothes" piece={outfits.data?.piece ?? find.piece} outfits={outfits.data?.outfits ?? null}
          image={image} note={drawnFromWords('shop', (outfits.data?.piece ?? find.piece)?.pattern)} error={outfits.error ? wornError(outfits.error) : null} byId={byId} keep={button}
          onClose={() => setOpen(false)} />
      )}
    </div>
  );
}

/** A find's checkout code: the code, and either its percent or its amount off in the find's currency; Save, Remove the
 * code (when there is one), and Cancel beside the title. The price after it is worked out by Nines, never typed. */
function CodeSheet({ find, keep, onClose }: { find: Find; keep: RefObject<HTMLButtonElement | null>; onClose(): void }) {
  const qc = useQueryClient();
  const [code, setCode] = useState(find.code?.code ?? '');
  const [kind, setKind] = useState<'percent' | 'amount'>(find.code?.amount != null ? 'amount' : 'percent');
  const [value, setValue] = useState(find.code ? String(find.code.percent ?? find.code.amount ?? '') : '');
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const hint = useId();

  async function send(call: () => Promise<FindsAnswer>) {
    setSaving(true);
    try {
      qc.setQueryData(queryKeys.finds(find.wish_id), await call());
      void touch(qc, 'findCode', ['finds']);
      onClose();
    } catch (e) {
      setProblem((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function save(e: FormEvent) {
    e.preventDefault();
    const typed = typedCode(code, kind, value);
    if (typeof typed === 'string') return setProblem(typed);
    setProblem(null);
    void send(() => api.setFindCode(find.wish_id, find.id, typed));
  }

  return (
    <Sheet title="A code at checkout" popover keep={keep} closeLabel="Cancel" className="find-code-sheet" testId="code-sheet" onClose={onClose}>
      <form onSubmit={save} noValidate aria-label="A code at checkout" aria-describedby={hint}>
        <p className="hint" id={hint}>Nines works out the price with the code, and tells you when that price goes down.</p>
        <label className="field">
          <span>Code</span>
          <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={30} autoCapitalize="characters"
            autoComplete="off" spellCheck={false} autoFocus />
        </label>
        <SegmentedControl label="What the code takes off" className="find-code-kind" value={kind} onChange={setKind}
          options={[{ value: 'percent', label: '% off' }, { value: 'amount', label: 'Amount off' }]} />
        <label className="field">
          <span>{kind === 'percent' ? 'Percent off' : `Amount off, in ${find.currency}`}</span>
          <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)}
            placeholder={kind === 'percent' ? 'e.g. 40' : 'e.g. 20'} />
        </label>
        {problem && <p className="form-error" role="alert">{problem}</p>}
        <div className="row">
          <Button variant="primary" small type="submit" disabled={saving}>Save</Button>
          {find.code && (
            <Button variant="ghost" small disabled={saving}
              onClick={() => void send(() => api.removeFindCode(find.wish_id, find.id))}>Remove the code</Button>
          )}
        </div>
      </form>
    </Sheet>
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
    const most = readAmount(amount);
    const cur = currency.trim().toUpperCase();
    if (most === undefined) return setProblem(PRICE_HINT);
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
