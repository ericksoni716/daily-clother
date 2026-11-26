/**
 * You might like: a small card in the Wardrobe with two views, For you (three things Claude found from what you wear
 * and love, not from a gap) and On sale (three marked down now, each checked on its page by Nines), each pick with Save
 * (onto the wishlist), More like this and Not for me (with Undo). Look now on a tap; by itself once a week once you have
 * looked. Its words and decisions are in picks.ts; the backend is closet/picks.py.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api';
import { CheckIcon, CloseIcon, HangerIcon } from '../components/Icons';
import { Toggle } from '../components/Toggle';
import { Button, Failed, Fold, Notice, Section, SegmentedControl, ShowMore, buttonClass } from '../components/ui';
import {
  cardState, DEMO, LOOK_SENDS, LOOKING, lookCostWords, NEVER_LOOKED, NOTHING, offerWords, pickName, PICK_NAME_BARE_MAX, PICK_NAME_MAX, picksOf, picksPoll,
  PICKS_SHOWN, REFUSED, runKind, SALE_NEVER, SALE_NOTHING, saleNote, salePriceLine, savedPicks, savedView, savePicks,
  saveView, SHOPS_OFFER, shopLine, THIN, verdictLine, VIEW_OPTIONS, WEEKLY_LABEL, withRefused,
  type PickKind, type ShopPick, type PicksAnswer,
} from '../picks';
import { touch } from '../queries';
import { queryKeys } from '../queryKeys';
import { Link } from '../router';
import { shownWithCopy } from '../savedCopy';
import { webLink } from '../shop';
import { useApp } from '../store';
import { OFFLINE_TITLE } from './Missing';
import './YouMightLike.css';

/** On a saved pick's "✓ Saved": what it says and what pressing it does. */
const SAVED_TITLE = 'On your wishlist. Press to take it off.';

export function YouMightLike({ locked }: { locked: boolean }) {
  const { profile, toast } = useApp();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: queryKeys.picks(),
    queryFn: async () => {
      const answer = await api.picks();
      savePicks(profile, answer);
      return answer;
    },
    refetchInterval: (query) => picksPoll(query.state.data),
  });
  const shown = shownWithCopy(q.data, q.error, () => savedPicks(profile), '');
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [refused, setRefused] = useState<{ pick: ShopPick; index: number } | null>(null);
  const [view, setView] = useState<PickKind>(() => savedView());
  if (shown.kind === 'loading') {   // its space kept, so nothing below moves when it comes
    return (
      <Section id="picks-title" title="You might like" className="picks">
        <div className="picks-skeleton" aria-hidden="true" />
      </Section>
    );
  }
  if (shown.kind === 'error') {
    // nothing read and nothing kept on this device: offline, the banner says it once; otherwise why, with Try again
    if (shown.offline) return null;
    return (
      <Section id="picks-title" title="You might like" className="picks">
        <Failed query={q} what="what you might like" testId="picks-failed" />
      </Section>
    );
  }
  const data = shown.data;
  const off = locked || shown.savedAt !== null;
  const title = off ? OFFLINE_TITLE : undefined;
  const state = cardState(data, view);
  const sale = view === 'sale';

  /** Sends one action and puts the card's answer in place; a look that cannot start says why in the card, once. */
  async function act(key: string, call: () => Promise<PicksAnswer>, done?: string): Promise<PicksAnswer | null> {
    setBusy(key);
    setProblem(null);
    try {
      const answer = await call();
      qc.setQueryData(queryKeys.picks(), answer);
      savePicks(profile, answer);
      void touch(qc, 'pick', ['picks']);
      if (done) toast(done);
      return answer;
    } catch (e) {
      setProblem((e as Error).message);
      return null;
    } finally {
      setBusy(null);
    }
  }

  const looking = state === 'looking';
  const anyLooking = data.run?.state === 'running';   // one look at a time, of either kind
  const lookNow = (variant: 'primary' | 'link') => (
    <Button small variant={variant} data-testid="picks-look" disabled={off || busy !== null || anyLooking} title={title}
      onClick={() => void act('look', () => api.lookForPicks(view))}>Look now</Button>
  );
  const run = data.run && runKind(data.run) === view ? data.run : null;
  const said = problem ?? (run?.state === 'failed' ? run.message : null);
  const list = picksOf(withRefused(data.picks, refused), view);
  const nothing = sale ? SALE_NOTHING : NOTHING;
  const cost = lookCostWords(data.estimate);   // beside Look now; in the fold once there are picks

  return (
    <Section id="picks-title" title="You might like" className="picks" action={(state === 'list' || looking) && lookNow('link')}
      hint={state === 'list' && run?.state === 'done' && run.added === 0 ? nothing : undefined}>
      {state !== 'demo' && (
        <SegmentedControl label="Which things to show" small className="picks-view" value={view} options={VIEW_OPTIONS}
          onChange={(v) => { setView(v); saveView(v); setProblem(null); }} />
      )}
      {state === 'demo' && <p className="picks-line">{DEMO}</p>}
      {state === 'thin' && <p className="picks-line" data-testid="picks-thin">{THIN}</p>}
      {(state === 'never' || state === 'nothing') && (
        <div className="picks-start">
          <p className="picks-line">{state === 'never' ? (sale ? SALE_NEVER : NEVER_LOOKED) : nothing}</p>
          {lookNow('primary')}
          {cost && <p className="muted picks-small">{cost}</p>}
          {sale && !data.shops && (
            <Link to="/settings?open=shops" className={buttonClass({ variant: 'link', small: true })}
              data-testid="picks-shops">{SHOPS_OFFER}</Link>
          )}
        </div>
      )}
      <div className={looking ? 'picks-room is-looking' : 'picks-room'}>
      {list.length > 0 && (
        <ShowMore key={view} items={list} first={PICKS_SHOWN} wide={PICKS_SHOWN} keyOf={(p) => p.id} moreLabel="See earlier ones"
          className="pick-list" label={sale ? 'Things on sale you might like' : 'Things you might like'} testId="picks"
          render={(p) => p.state === 'refused' ? (
            <div className="pick pick-refused" role="status">
              <p>{REFUSED}</p>
              <Button small variant="ghost" disabled={off || busy !== null} title={title}
                onClick={() => void act(p.id, () => api.unrefusePick(p.id)).then((a) => a && setRefused(null))}>Undo</Button>
            </div>
          ) : (
            <PickRow pick={p} off={off} busy={busy !== null} title={title}
              onSave={() => void act(p.id, () => api.savePick(p.id))}
              onUnsave={() => void act(p.id, () => api.unsavePick(p.id))}
              onMore={() => void act(`more-${p.id}`, () => api.moreLikePick(p.id))}
              onRefuse={() => {
                const index = list.findIndex((x) => x.id === p.id);
                void act(p.id, () => api.refusePick(p.id)).then((a) => a && setRefused({ pick: p, index }));
              }} />
          )} />
      )}
      {looking && (
        <Notice as="p" role="status" className="picks-notice" icon={<span className="spinner" aria-hidden="true" />}>{LOOKING}</Notice>
      )}
      </div>
      {said && <Notice as="p" tone="error" role="status" className="picks-notice">{said}</Notice>}
      {data.offer && <Offer offer={data.offer} off={off} busy={busy !== null} title={title}
        onAnswer={(answer) => void act('offer', () => api.answerPickOffer(data.offer!.id, answer))} />}
      {state !== 'demo' && (
        <Fold title="How Nines looks" className="picks-fold" testId="picks-fold">
          {data.looked && (
            <Toggle label={WEEKLY_LABEL} checked={data.weekly} disabled={off || busy !== null}
              onChange={(on) => void act('weekly', () => api.setPicksWeekly(on))} />
          )}
          <p className="muted picks-small" data-testid="picks-sends">{LOOK_SENDS}</p>
          {cost && state === 'list' && <p className="muted picks-small">{cost}</p>}
        </Fold>
      )}
    </Section>
  );
}

function PickRow({ pick, off, busy, title, onSave, onUnsave, onMore, onRefuse }: {
  pick: ShopPick; off: boolean; busy: boolean; title?: string; onSave(): void; onUnsave(): void; onMore(): void; onRefuse(): void;
}) {
  const link = webLink(pick.url);
  const image = webLink(pick.image_url);
  const [broken, setBroken] = useState(false);
  const why = verdictLine(pick);
  const prices = salePriceLine(pick);
  const note = saleNote(pick);
  // beside a hanger (no picture), the name has a third line, so the kind of piece is not cut off
  const bare = !image || broken;
  const name = pickName(pick.name, bare ? PICK_NAME_BARE_MAX : PICK_NAME_MAX);
  const nameClass = bare ? 'pick-name is-bare' : 'pick-name';
  const saved = pick.state === 'saved' && !!pick.wish_id;
  return (
    <article className="pick" data-testid="pick">
      <div className="pick-pic" aria-hidden="true">
        {image && !broken
          ? <img src={image} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} />
          : <HangerIcon />}
      </div>
      <div className="pick-body">
        {link
          ? <a className={nameClass} href={link} target="_blank" rel="noopener noreferrer" title={pick.name}>{name}</a>
          : <span className={nameClass} title={pick.name}>{name}</span>}
        <p className="pick-shop">{shopLine(pick)}</p>
        {prices && <p className="pick-price" data-testid="pick-price">{prices}</p>}
        {why && <p className="pick-why">{why}</p>}
        {note && <p className="pick-shop" data-testid="pick-note">{note}</p>}
      </div>
      <button type="button" className="pick-refuse" aria-label={`Not for me: ${pick.name}`} title="Not for me"
        disabled={off || busy} onClick={onRefuse}><CloseIcon /></button>
      <div className="pick-actions">
        {saved ? (
          // saved: Save becomes "✓ Saved" in its place and at its width; pressing it takes the pick off the wishlist
          <Button small className="pick-save pick-wished" disabled={off || busy} title={title ?? SAVED_TITLE}
            aria-label={`Saved: take ${pick.name} off your wishlist`} onClick={onUnsave}><CheckIcon /> Saved</Button>
        ) : (
          <Button small className="pick-save" disabled={off || busy} title={title} onClick={onSave}>Save</Button>
        )}
        <Button small variant="ghost" disabled={off || busy} title={title} onClick={onMore}>More like this</Button>
        {/* said when it changes, as the saved line was */}
        <span className="visually-hidden" role="status">{saved ? 'On your wishlist.' : ''}</span>
      </div>
    </article>
  );
}

/** The line offered for Your style after a few "Not for me" alike: kept only on a tap, with Undo. */
function Offer({ offer, off, busy, title, onAnswer }: {
  offer: NonNullable<PicksAnswer['offer']>; off: boolean; busy: boolean; title?: string;
  onAnswer(answer: { save?: boolean; undo?: boolean }): void;
}) {
  const words = offerWords(offer);
  if (offer.state === 'saved') {
    return (
      <div className="picks-offer" data-testid="picks-offer">
        <p>{words.saved}</p>
        <Button small variant="ghost" disabled={off || busy} title={title} onClick={() => onAnswer({ undo: true })}>Undo</Button>
      </div>
    );
  }
  return (
    <div className="picks-offer" role="group" aria-label={words.question} data-testid="picks-offer">
      <p>{words.question} <q>{offer.text}</q></p>
      <div className="row">
        <Button small disabled={off || busy} title={title} onClick={() => onAnswer({ save: true })}>{words.save}</Button>
        <Button small variant="ghost" disabled={off || busy} title={title} onClick={() => onAnswer({ save: false })}>No thanks</Button>
      </div>
    </div>
  );
}
