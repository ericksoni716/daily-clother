/**
 * You might like: a small card in the Wardrobe with three things Claude found from what you wear and love (not from a
 * gap), each with Save (onto the wishlist), More like this and Not for me (with Undo). Look now on a tap; by itself
 * once a week once you have looked. Its words and decisions are in picks.ts; the backend is closet/picks.py.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api';
import { CloseIcon, HangerIcon } from '../components/Icons';
import { Toggle } from '../components/Toggle';
import { Button, Fold, Notice, Section, ShowMore, buttonClass } from '../components/ui';
import {
  cardState, DEMO, LOOK_SENDS, LOOKING, lookCostWords, NEVER_LOOKED, NOTHING, offerWords, pickName, picksPoll,
  PICKS_SHOWN, REFUSED, savedPicks, savePicks, shopLine, THIN, verdictLine, WEEKLY_LABEL, withRefused,
  type ShopPick, type PicksAnswer,
} from '../picks';
import { touch } from '../queries';
import { queryKeys } from '../queryKeys';
import { Link, wishPath } from '../router';
import { shownWithCopy } from '../savedCopy';
import { webLink } from '../shop';
import { useApp } from '../store';
import { OFFLINE_TITLE } from './Missing';
import './YouMightLike.css';

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
  if (shown.kind === 'loading') {   // its space kept, so nothing below moves when it comes
    return (
      <Section id="picks-title" title="You might like" className="picks">
        <div className="picks-skeleton" aria-hidden="true" />
      </Section>
    );
  }
  if (shown.kind === 'error') return null;   // nothing read and nothing kept on this device: nothing to back it
  const data = shown.data;
  const off = locked || shown.savedAt !== null;
  const title = off ? OFFLINE_TITLE : undefined;
  const state = cardState(data);

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
  const lookNow = (variant: 'primary' | 'link') => (
    <Button small variant={variant} data-testid="picks-look" disabled={off || busy !== null || looking} title={title}
      onClick={() => void act('look', api.lookForPicks)}>Look now</Button>
  );
  const run = data.run;
  const said = problem ?? (run?.state === 'failed' ? run.message : null);
  const list = withRefused(data.picks, refused);
  const cost = lookCostWords(data.estimate);   // beside Look now; in the fold once there are picks

  return (
    <Section id="picks-title" title="You might like" className="picks" action={state === 'list' && lookNow('link')}
      hint={state === 'list' && run?.state === 'done' && run.added === 0 ? NOTHING : undefined}>
      {state === 'demo' && <p className="picks-line">{DEMO}</p>}
      {state === 'thin' && <p className="picks-line" data-testid="picks-thin">{THIN}</p>}
      {(state === 'never' || state === 'nothing') && (
        <div className="picks-start">
          <p className="picks-line">{state === 'never' ? NEVER_LOOKED : NOTHING}</p>
          {lookNow('primary')}
          {cost && <p className="muted picks-small">{cost}</p>}
        </div>
      )}
      {list.length > 0 && (
        <ShowMore items={list} first={PICKS_SHOWN} wide={PICKS_SHOWN} keyOf={(p) => p.id} moreLabel="See earlier ones"
          className="pick-list" label="Things you might like" testId="picks"
          render={(p) => p.state === 'refused' ? (
            <div className="pick pick-refused" role="status">
              <p>{REFUSED}</p>
              <Button small variant="ghost" disabled={off || busy !== null} title={title}
                onClick={() => void act(p.id, () => api.unrefusePick(p.id)).then((a) => a && setRefused(null))}>Undo</Button>
            </div>
          ) : (
            <PickRow pick={p} off={off} busy={busy !== null} title={title}
              onSave={() => void act(p.id, () => api.savePick(p.id), 'On your wishlist')}
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

function PickRow({ pick, off, busy, title, onSave, onMore, onRefuse }: {
  pick: ShopPick; off: boolean; busy: boolean; title?: string; onSave(): void; onMore(): void; onRefuse(): void;
}) {
  const link = webLink(pick.url);
  const image = webLink(pick.image_url);
  const [broken, setBroken] = useState(false);
  const why = verdictLine(pick);
  return (
    <article className="pick" data-testid="pick">
      <div className="pick-pic" aria-hidden="true">
        {image && !broken
          ? <img src={image} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} />
          : <HangerIcon />}
      </div>
      <div className="pick-body">
        {link
          ? <a className="pick-name" href={link} target="_blank" rel="noopener noreferrer" title={pick.name}>{pickName(pick.name)}</a>
          : <span className="pick-name" title={pick.name}>{pickName(pick.name)}</span>}
        <p className="pick-shop">{shopLine(pick)}</p>
        {why && <p className="pick-why">{why}</p>}
      </div>
      <button type="button" className="pick-refuse" aria-label={`Not for me: ${pick.name}`} title="Not for me"
        disabled={off || busy} onClick={onRefuse}><CloseIcon /></button>
      <div className="pick-actions">
        {pick.state === 'saved' && pick.wish_id
          ? <Link to={wishPath(pick.wish_id)} className={buttonClass({ variant: 'ghost', small: true })}>On your wishlist</Link>
          : <Button small disabled={off || busy} title={title} onClick={onSave}>Save</Button>}
        <Button small variant="ghost" disabled={off || busy} title={title} onClick={onMore}>More like this</Button>
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
