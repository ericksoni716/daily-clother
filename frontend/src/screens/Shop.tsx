import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type RefObject } from 'react';
import { api } from '../api';
import { LinkIcon, SearchIcon } from '../components/Icons';
import { useNewsSeen } from '../components/PriceNews';
import { SeeItWorn } from '../components/WornWith';
import { Button, buttonClass, Card, Failed, Fold, HowItWorks, Notice, SegmentedControl, Sheet } from '../components/ui';
import type { Wish } from '../gaps';
import { stale, touch, useItems } from '../queries';
import {
  addedByHand, canSeeWorn, checkedWords, codeFromWords, codeWords, dropWords, type Find, type FindsAnswer, findsInOrder, withStopped, googleShoppingLink,
  historyWords, isTheWish, lastChecked, LINK_PROBLEM, linkIn, linkLine, mostWords, notJudgedWords, priceWords, runDoneWords, runWords, shopPoll,
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
export function LinkForm({ initial = '', submit, busy, locked, lockedTitle, onSubmit, onCancel, autoFocus = true, cancel = true }: {
  initial?: string; submit: string; busy: boolean; locked: boolean; lockedTitle?: string;
  onSubmit(url: string): Promise<string | null>; onCancel(): void; autoFocus?: boolean;
  /** its own Cancel; false in a sheet, whose Cancel is beside its title */
  cancel?: boolean;
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
        {cancel && <button className="btn btn-ghost btn-small" type="button" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}

/**
 * On a wish, below what to look for: "Added by hand" when it was, what is watched (the pages you sent, then Claude's
 * finds), one line for when it was last checked with Check now, and the most you'd pay; then looking for more in one row
 * ("Find some", "Add a link", "Search Google Shopping") and one closed "How this works" for what is true every day.
 * Opening the page tells the server you have seen the wish's price news.
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
      void stale(qc, queryKeys.wishlist());
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
      // this wish's finds changed, and with them its row in the wishlist (its link and its drop)
      await stale(qc, key, { exact: true });
      void stale(qc, queryKeys.wishlist());
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }
  async function undoStop(f: Find) {
    try {
      qc.setQueryData(key, await api.restoreFind(wish.id, f.id));
      setStopped((was) => was.filter((s) => s.find.id !== f.id));
      // the wish reads as before the stop again, its row in the wishlist too
      void stale(qc, queryKeys.wishlist());
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
  // a price check running is said in place of "Last checked …", so nothing under it moves (DESIGN, "The page holds
  // still")
  const pricing = finds.length > 0 && run?.state === 'running' && run.kind === 'prices';
  const said = <RunSaid run={pricing ? null : run} error={begin.error?.message ?? null} />;
  // the currency the most you'd pay starts in when none is set: the newest find's
  const currency = answer?.finds[0]?.currency;
  // above what is watched, and decided with it, so that stopping a link's find on this visit, or the wishlist read again
  // meanwhile, never puts this line in above the find (DESIGN, "The page holds still")
  const byHand = addedByHand(wish, answer ? finds : null) && <p className="wish-look muted">Added by hand</p>;
  // what is watched comes first, so the page waits for it (a moment: Nines is on this computer) before laying out the rest
  if (!answer && !locked) {
    return (
      <>
        {byHand}
        {read.error ? <Failed query={read} what="what is watched for this wish" />
          : <div className="missing-skeleton missing-skeleton-small" aria-hidden="true" />}
      </>
    );
  }
  return (
    <>
      {byHand}
      <Failed query={read} what="what is watched for this wish" />
      {finds.length > 0 && (
        <section className="wish-watch" aria-label={`Watching for ${wish.name}`}>
          <ul className="find-list" aria-label="Found in shops">
            {finds.map((f, i) => (
              <li key={f.id}>
                <FindCard find={f} demo={demo} locked={locked} byId={byId} stopped={isStopped(f)} own={isTheWish(f, wish)}
                  onStop={() => void stop(f, i)} onUndo={() => void undoStop(f)} />
              </li>
            ))}
          </ul>
          {/* one quiet line: when it was last checked, or that it is being checked now, in the same place */}
          <div className="wish-line">
            <p className="muted" data-testid="prices-checked">
              {pricing ? runWords(run!) : checkedWords(lastChecked({ ...answer!, finds: listed }))}
            </p>
            <Button small data-testid="check-prices" disabled={pricesOff} title={pricesOff ? title : undefined}
              onClick={() => begin.mutate('prices')}>Check now</Button>
          </div>
          {checking && said}
          <PriceLine wish={wish} currency={currency} locked={locked} onPrice={onPrice} />
        </section>
      )}
      <section className="wish-shop" aria-label={`Looking for more for ${wish.name}`}>
        {finds.length === 0 && <PriceLine wish={wish} currency={currency} locked={locked} onPrice={onPrice} />}
        <div className="row wish-shop-actions">
          <Button small data-testid="find-some" disabled={disabled} title={title} onClick={() => begin.mutate('find')}>
            <SearchIcon /> {finds.length ? 'Find more' : 'Find some'}
          </Button>
          {!linking && (
            <Button small data-testid="add-link" disabled={busy} onClick={() => setLinking(true)}>
              <LinkIcon /> Add a link
            </Button>
          )}
          <a className={buttonClass({ small: true })} data-testid="google-shopping" href={googleShoppingLink(wish)}
            target="_blank" rel="noopener noreferrer">Search Google Shopping</a>
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
        {!checking && said}
        {/* what is true every day, behind one closed line (DESIGN, "Reading load is a budget") */}
        <HowItWorks className="wish-how" testId="shop-how">
          <p>{watchWords(wish)}</p>
          {!demo && <p data-testid="search-sends">{SEARCH_SENDS}</p>}
          {demo && <p>The demo closet never searches shops. Open your own closet to look for this.</p>}
          {answer && !demo && answer.estimate.api && (
            <p>
              If your plan can't be used, a search costs {aboutUsd(answer.estimate.find_usd)} at most with the API key
              {finds.length > 0 ? `, and a price check ${aboutUsd(answer.estimate.prices_usd)}` : ''}.
            </p>
          )}
        </HowItWorks>
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

/**
 * A find's card, in the order it is read (DESIGN, "Lead with the answer"): what it is and what it costs (the price, the
 * price with a code, the drop), then whether it works (the verdict and its reasons, or why it is not judged), then the
 * two things to do with it, and one closed fold for everything else (the price so far, who read it, what Claude saw,
 * who saw the code, and the two occasional actions: the code and Stop watching).
 */
function FindCard({ find, demo, locked, byId, stopped, own = false, onStop, onUndo }: {
  find: Find; demo: boolean; locked: boolean; byId: Map<string, ItemSummary>;
  /** the wish itself (made from it, with its name): the page's heading names it, so the card starts at its shop */
  own?: boolean;
  /** you stopped watching it on this visit: it stays, saying so, with Undo where its two small buttons were */
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
  const code = codeWords(find);
  const from = codeFromWords(find.code);
  return (
    // a grid: the picture beside what it is and what it costs; on a phone the rest runs under both, the card's whole
    // width, and on a computer beside the picture
    <Card as="article" className={image ? 'find-card has-image' : 'find-card'} data-testid="find" aria-label={find.name}
      data-verdict={find.verdict ?? ''}>
      {image && <img className="find-image" src={image} alt="" loading="lazy" referrerPolicy="no-referrer" />}
      {/* what it is and what it costs */}
      <div className="find-what">
        {!own && <h2 className="find-name">{find.name}</h2>}
        <p className="find-shop">
          <span className="find-shop-name">{find.shop}</span> · <strong className={find.price == null ? 'find-price is-none' : 'find-price'}>{priceWords(find.price, find.currency)}</strong>
          {!find.available && <span className="find-sold"> · Sold out</span>}
        </p>
        {code && <p className="find-code" data-testid="find-code">{code}</p>}
        {find.drop && <p className="find-drop" data-testid="find-drop">{dropWords(find.drop)}</p>}
      </div>
      {/* whether it works: the verdict and its reasons, or why it is not judged, in the same place */}
      {(find.verdict_words || find.reasons.length > 0 || unjudged) && (
        <div className="find-answer">
          {find.verdict_words && <p className={`find-verdict is-${tone}`} data-testid="find-verdict">{find.verdict_words}</p>}
          {find.reasons.length > 0 && (
            <ul className="find-reasons" aria-label="Why">
              {find.reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
          )}
          {unjudged && <p className="find-not-judged" data-testid="find-not-judged">{unjudged}</p>}
        </div>
      )}
      {/* what you can do */}
      {(canSeeWorn(find) || link) && (
        <div className="row find-actions">
          {canSeeWorn(find) && <SeeWorn find={find} image={image} locked={locked || stopped} byId={byId} />}
          {link && <a className={buttonClass({ small: true })} href={link} target="_blank" rel="noopener noreferrer">Open in shop</a>}
        </div>
      )}
      {/* everything else, closed */}
      <Fold title="About this find" className="find-more" testId="find-more">
        {went && <p data-testid="find-history">{went}</p>}
        {sent && <p data-testid="find-link">{sent}</p>}
        {find.piece_words && <p>Claude saw: {find.piece_words}</p>}
        {from && <p data-testid="find-code-from">{from}</p>}
        {stopped ? (
          <p className="find-stopped" role="status" data-testid="find-stopped">
            You stopped watching it, and its daily check.{' '}
            <Button variant="link" small autoFocus disabled={locked} onClick={onUndo}>Undo</Button>
          </p>
        ) : (
          <div className="row find-more-actions">
            <CodeButton find={find} locked={locked} />
            {/* the find goes, and with it its daily check; Undo puts it back as it was */}
            <Button small disabled={locked} onClick={onStop}>Stop watching</Button>
          </div>
        )}
      </Fold>
    </Card>
  );
}

/** "Add a code", or "Change the code" when there is one, in a find's fold: it opens the code in a sheet (a popover under
 * it on a computer). The price after the code is said under the find's price. */
function CodeButton({ find, locked }: { find: Find; locked: boolean }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  return (
    <div className="find-code-line">
      <button ref={button} type="button" className="btn btn-small" aria-haspopup="dialog" aria-expanded={open} disabled={locked}
        onClick={() => setOpen(!open)}>
        {find.code ? 'Change the code' : 'Add a code'}
      </button>
      {open && <CodeSheet find={find} keep={button} onClose={() => setOpen(false)} />}
    </div>
  );
}

/**
 * "See it with your clothes": a button on a judged find's card, opening the outfits made with it, drawn as worn on this
 * computer (nothing is asked of Claude). They are worked out when the sheet opens.
 */
function SeeWorn({ find, image, locked, byId }: { find: Find; image: string | null; locked: boolean; byId: Map<string, ItemSummary> }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const outfits = useQuery({
    queryKey: queryKeys.findOutfits(find.wish_id, find.id), queryFn: () => api.findOutfits(find.wish_id, find.id), enabled: open,
  });
  return (
    <div className="find-worn">
      <button ref={button} type="button" className="btn btn-small" data-testid="see-worn"
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

/** The most you'd pay: a small button that opens it in a sheet (a popover under it on a computer), "Set the most you'd
 * pay"; once set, what it is and "Change". */
function PriceLine({ wish, currency, locked, onPrice }: {
  wish: Wish; currency?: string; locked: boolean; onPrice(w: Wish, changes: PriceChange): Promise<boolean>;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const words = mostWords(wish);
  return (
    <div className="wish-price-line">
      <p className="wish-line wish-price" data-testid="wish-price">
        {words && <span>{words}</span>}{words && ' '}
        <button ref={button} type="button" className="btn btn-small" aria-haspopup="dialog"
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
