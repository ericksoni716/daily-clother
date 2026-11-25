/**
 * Wardrobe: what to buy and how the closet is used, on one page (it was What's missing and Insights). The few things
 * most worth buying; "Thinking of buying something?" with Would this work? and the row that opens the wishlist; what is
 * not worn and what is worn most; the other figures behind "More numbers". The wishlist, a wish, Would this work? and an
 * item have pages of their own under /wardrobe. The parts are in Missing.tsx (buying) and Insights.tsx (how the closet
 * is used).
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { ChevronLeftIcon, WarnIcon } from '../components/Icons';
import { LifeQuestions } from '../components/LifeQuestions';
import { BackLink, EmptyState, Failed, Notice, PageHeader } from '../components/ui';
import { savedWhen, saveGaps, type Wish } from '../gaps';
import { saveInsights } from '../insights';
import { goBack, navigate, WISHLIST_PATH, wishPath } from '../router';
import { touch, useItems } from '../queries';
import { queryKeys, type EditKind, type KeyName } from '../queryKeys';
import { shownWithCopy, useTellFailure } from '../savedCopy';
import { useApp } from '../store';
import type { SituationId } from '../life';
import { wishById } from '../wouldwork';
import { ItemDetail } from './ItemDetail';
import { INSIGHTS_OFFLINE, savedInsights, Usage } from './Insights';
import {
  LifeAbout, LifeBasis, OFFLINE_TITLE, savedLists, savedWishes, Thinking, WishCard, Wishlist, WorthBuying, type Actions, type Lists,
} from './Missing';
import { sharedLink, wishTitle } from '../shop';
import { LinkForm } from './Shop';
import { WouldWork } from './WouldWork';
import { YouMightLike } from './YouMightLike';
import { offersPicks } from '../picks';
import './Missing.css';

// offline is said once, by the banner over the page; the Wardrobe says only what is its own (the review of 24 November)
const OFFLINE_EMPTY = 'Your wardrobe was not saved on this device yet.';
const OFFLINE_WISHES = 'Your wishlist was not saved on this device.';

/** Wish edits that cannot change any wish's finds (a new wish's finds are read when its card shows). */
const NOT_FINDS = ['finds'] as const;
/** A wish made from a link fills no gap (only a wish made from a gap marks one), so the analysis of what is worth
 * buying is not asked for again: the new wish's page opens without waiting for it. */
const FROM_A_LINK = ['finds', 'gaps'] as const;

export function WardrobeScreen({ itemId, check, wishId, wish, link = false, wishlist = false, wide }: {
  itemId: string | null; check: boolean; wishId: string | null; wish: string | null;
  /** The page a shared link opens (`/wardrobe/link?url=…`): the link box, filled in, for the owner to confirm. */
  link?: boolean;
  /** The wishlist's own page (`/wardrobe/wishlist`), which needs only the wishes. */
  wishlist?: boolean;
  wide: boolean;
}) {
  const { profile, offline, toast } = useApp();
  const qc = useQueryClient();
  const items = useItems('active').data;
  const [busy, setBusy] = useState<string | null>(null);
  const [lifeOpen, setLifeOpen] = useState(false);
  const [situation, setSituation] = useState<SituationId | 'all'>('all');
  // a wish removed from its own page: the wishlist it goes back to keeps a line with Undo in its place, until you leave
  // the wishlist (as "Stop watching" and the outfits you keep)
  const [removed, setRemoved] = useState<{ wish: Wish; at: number } | null>(null);
  useEffect(() => {
    if (!wishlist && wish === null) setRemoved(null);
  }, [wishlist, wish]);

  // The three answers are read through the cache, each kept on this device for when Nines cannot be reached.
  // Coming back shows them at once; coming back online asks again for all of them (ClosetProvider).
  const gapsQ = useQuery({
    queryKey: queryKeys.gaps(),
    queryFn: async () => {
      const gaps = await api.gaps();
      saveGaps(profile, { gaps });
      return gaps;
    },
  });
  const wishesQ = useQuery({
    queryKey: queryKeys.wishlist(),
    queryFn: async () => {
      const wishes = await api.wishlist();
      saveGaps(profile, { wishes });
      return wishes;
    },
  });
  const insightsQ = useQuery({
    queryKey: queryKeys.insights(),
    queryFn: async () => {
      const answer = await api.insights();
      saveInsights(profile, answer);
      return answer;
    },
  });
  // a wish's finds, as its page has read them (never asked for here): its heading names the find it was made from in
  // full when its own name is that name cut short
  const wishFinds = useQuery({ queryKey: queryKeys.finds(wish ?? ''), queryFn: () => api.finds(wish ?? ''), enabled: false }).data;
  const lists = useMemo<Lists | undefined>(
    () => (gapsQ.data && wishesQ.data ? { gaps: gapsQ.data, wishes: wishesQ.data } : undefined), [gapsQ.data, wishesQ.data]);
  const failed = gapsQ.error ?? wishesQ.error;
  const phase = shownWithCopy(lists, failed, () => savedLists(profile), OFFLINE_EMPTY);
  const usage = shownWithCopy(insightsQ.data, insightsQ.error, () => savedInsights(profile), INSIGHTS_OFFLINE);
  const wishShown = shownWithCopy(wishesQ.data, wishesQ.error, () => savedWishes(profile), OFFLINE_WISHES);
  const asking = gapsQ.isFetching || wishesQ.isFetching;
  useTellFailure(failed, !!lists, Math.max(gapsQ.errorUpdatedAt, wishesQ.errorUpdatedAt), toast);
  useTellFailure(insightsQ.error, insightsQ.data !== undefined, insightsQ.errorUpdatedAt, toast);
  const retry = () => {
    void gapsQ.refetch();
    void wishesQ.refetch();
    void insightsQ.refetch();
  };

  // back from a check (the wish it was started from may have changed meanwhile): ask for the lists again
  const wasChecking = useRef(check);
  useEffect(() => {
    if (wasChecking.current && !check) {
      void qc.invalidateQueries({ queryKey: queryKeys.gaps() });
      void qc.invalidateQueries({ queryKey: queryKeys.wishlist() });
    }
    wasChecking.current = check;
  }, [check, qc]);

  const byId = useMemo(() => new Map((items ?? []).map((i) => [i.id, i])), [items]);
  const locked = offline || (phase.kind === 'ready' && phase.savedAt !== null) || (wishShown.kind === 'ready' && wishShown.savedAt !== null);

  /** Runs a change on the server, then asks again for what it changed (the analysis is kept on the server, so it is
   * quick) before the buttons are given back. */
  async function change(key: string, kind: EditKind, run: () => Promise<unknown>, done?: string, written: readonly KeyName[] = []): Promise<boolean> {
    setBusy(key);
    try {
      await run();
      if (done) toast(done);
      await touch(qc, kind, written);
      return true;
    } catch (e) {
      toast((e as Error).message, 'error');
      return false;
    } finally {
      setBusy(null);
    }
  }

  const wishChange = (key: string, run: () => Promise<unknown>, done: string) => change(key, 'wish', run, done, NOT_FINDS);
  const actions: Actions = {
    locked,
    busy,
    // the card says it in place ("On your wishlist", with Undo), so no toast says it again
    wish: (g) => change(g.id, 'wish', () => api.addWish({ gap_id: g.id }), undefined, NOT_FINDS),
    unwish: (g) => change(g.id, 'wish', async () => { if (g.wish_id) await api.removeWish(g.wish_id); }, undefined, NOT_FINDS),
    hide: (g, reason) => change(g.id, 'gap', () => api.hideGap(g.id, reason), 'Hidden. You can bring it back below.'),
    unhide: (id) => change(id, 'gap', () => api.unhideGap(id), 'Brought back'),
    undoHolds: (g) => change(g.id, 'gap', async () => {
      for (const id of new Set(g.held_back_by?.map((hold) => hold.gap_id))) await api.unhideGap(id);
    }, 'Brought back'),
    confirmHide: (id) => change(id, 'gap', () => api.hideGap(id, 'never_wear'), 'Applied to similar suggestions'),
    addByHand: (name, note) => wishChange('new-wish', () => api.addWish({ name, note }), 'On your wishlist'),
    addLink: async (url) => {
      setBusy('new-link');
      try {
        const made = await api.addLink(url);
        await touch(qc, 'wish', FROM_A_LINK);
        // its own page says how the reading goes; from a shared link, Back then leaves rather than offering it again
        navigate(wishPath(made.id), { replace: link });
        return null;
      } catch (e) {
        return (e as Error).message;
      } finally {
        setBusy(null);
      }
    },
    saveNote: (w, note) => wishChange(w.id, () => api.changeWish(w.id, { note }), 'Note saved'),
    savePrice: (w, changes) => wishChange(w.id, () => api.changeWish(w.id, changes), 'Saved'),
    bought: async (w) => {
      if (await wishChange(w.id, () => api.wishBought(w.id), `Taken off the list. Add a photo of your new ${w.name.replace(/^(A|An) /, '').toLowerCase()}.`)) navigate('/add');
    },
    // the wishlist says it in the wish's place, with Undo, so no toast says it again
    remove: async (w) => {
      const at = Math.max(0, (wishesQ.data ?? []).findIndex((x) => x.id === w.id));
      const gone = await change(w.id, 'wish', () => api.removeWish(w.id), undefined, NOT_FINDS);
      if (gone) setRemoved({ wish: w, at });
      return gone;
    },
    // put back whole (its finds, price, code and note), so its finds are read again too
    restore: async (w) => {
      if (await change(w.id, 'wish', () => api.restoreWish(w.id))) setRemoved(null);
    },
  };
  /** A wish's note, saved as the box is left: said beside the box (SaveStatus), so it throws when it did not save. */
  const saveNote = async (w: Wish, note: string) => {
    await api.changeWish(w.id, { note });
    await touch(qc, 'wish', NOT_FINDS);
  };

  const wishes = phase.kind === 'ready' ? phase.data.wishes : null;

  // Would this work?: its own page, on a phone and on a computer (what it is on the left, the answer on the right)
  if (check) {
    return (
      <div className="missing-check">
        <WouldWork key={`${profile}-${wishId ?? ''}`} wish={wishById(wishes, wishId)} wishId={wishId} byId={byId} locked={locked}
          busy={busy === 'new-wish' || (wishId !== null && busy === wishId)}
          onWish={(name, note) => actions.addByHand(name, note)} onNote={(w, note) => actions.saveNote(w, note)}
          onBought={(w) => actions.bought(w)} wide={wide} />
      </div>
    );
  }

  if (link) {
    const shared = sharedLink(window.location.search);
    return (
      <section className="wish-page" aria-labelledby="link-title">
        <PageHeader title="Add a link" titleId="link-title" back={{ to: WISHLIST_PATH, label: 'Wishlist' }} />
        {shared.none && <p className="notice">What you shared has no link in it. Paste the address of the product's page here.</p>}
        <LinkForm key={shared.link} initial={shared.link} submit="Add to the list" busy={busy === 'new-link'} locked={locked}
          lockedTitle={OFFLINE_TITLE} autoFocus={!shared.link} onSubmit={actions.addLink} onCancel={() => goBack(WISHLIST_PATH)} />
      </section>
    );
  }

  // the wishlist on its own page: it waits for the wishes only, then shows them and the ways to add one at once
  if (wishlist) {
    return (
      <section className="wish-page" aria-labelledby="wishlist-title" aria-busy={wishesQ.isFetching}>
        <PageHeader title="Wishlist" titleId="wishlist-title" back={{ to: '/wardrobe', label: 'Wardrobe' }} />
        {wishShown.kind === 'ready' && wishShown.savedAt && <SavedEarlier at={wishShown.savedAt} />}
        {wishShown.kind === 'ready' ? <Wishlist wishes={wishShown.data} actions={actions} removed={removed} />
          : wishShown.kind === 'loading' ? <div className="missing-skeleton" aria-hidden="true" />
            : wishShown.offline ? <p className="notice" role="alert">{wishShown.message}</p>
              : <Failed query={wishesQ} what="your wishlist" />}
      </section>
    );
  }

  // a wish on its own page, which needs only the wishes too (not the analysis of what is worth buying)
  if (wish !== null) {
    const shown = wishById(wishShown.kind === 'ready' ? wishShown.data : null, wish);
    return (
      <section className="wish-page" aria-labelledby="wish-title">
        <PageHeader title={shown ? wishTitle(shown, wishFinds?.finds) : 'A wish'} titleId="wish-title" back={{ to: WISHLIST_PATH, label: 'Wishlist' }} />
        {wishShown.kind === 'ready' && wishShown.savedAt && <SavedEarlier at={wishShown.savedAt} />}
        {shown ? <WishCard key={shown.id} wish={shown} actions={actions} onNote={saveNote} onRemoved={() => goBack(WISHLIST_PATH)} />
          : wishShown.kind === 'loading' ? <div className="missing-skeleton" aria-hidden="true" />
            : wishShown.kind === 'error' ? (wishShown.offline ? <p className="notice" role="alert">{wishShown.message}</p>
              : <Failed query={wishesQ} what="this wish" />)
              : <EmptyState title="This wish is not on your list any more" body="It may have been bought or removed on another device." />}
      </section>
    );
  }

  if (itemId && !wide) {
    return (
      <div className="missing-item">
        <div className="detail-top">
          <BackLink to="/wardrobe" className="btn btn-ghost back-link"><ChevronLeftIcon /> Wardrobe</BackLink>
        </div>
        <ItemDetail key={itemId} id={itemId} status="active" inPanel />
      </div>
    );
  }

  const thinking = <Thinking wishes={wishes} locked={locked} />;
  // the page waits for both answers, then shows everything at once (DESIGN, "The page holds still")
  const waiting = phase.kind === 'loading' || (phase.kind === 'ready' && usage.kind === 'loading');

  const main = (
    <div className="missing-main wardrobe" aria-busy={asking || waiting}>
      <PageHeader className="missing-header" title="Wardrobe" titleId="wardrobe-title"
        count={phase.kind === 'ready' && phase.data.gaps.enough && `${phase.data.gaps.checked.items} pieces, ${phase.data.gaps.checked.wears} wears looked at`}
        secondary={asking && phase.kind === 'ready' && <span className="missing-asking muted"><span className="spinner" aria-hidden="true" /> Looking again…</span>} />
      {phase.kind === 'ready' && phase.savedAt && <SavedEarlier at={phase.savedAt} />}
      {waiting && (
        <div className="missing-loading" role="status">
          {Array.from({ length: 3 }, (_, i) => <div key={i} className="missing-skeleton" aria-hidden="true" />)}
          <p className="muted"><span className="spinner" aria-hidden="true" /> Looking at your closet. This can take a few seconds…</p>
        </div>
      )}
      {phase.kind === 'error' && (phase.offline ? <p className="notice" role="alert">{phase.message}</p>
        : <Failed query={{ error: failed, refetch: retry, isFetching: asking }} what="what's worth buying" />)}
      {phase.kind === 'ready' && !waiting && (
        <>
          <WorthBuying gaps={phase.data.gaps} byId={byId} actions={actions} offline={offline}
            situation={situation} onSituation={setSituation} onLife={() => setLifeOpen(true)}
            basis={!lifeOpen && <LifeBasis context={phase.data.gaps.context} locked={locked} busy={busy !== null} invite={phase.data.gaps.enough}
              onOpen={() => setLifeOpen(true)}
              onDismiss={() => void change('life-dismiss', 'settings', () => api.putSettings({ life_prompt_dismissed: true }))} />} />
          {lifeOpen && <LifeQuestions initial={phase.data.gaps.context?.life ?? null} locked={locked}
            about={phase.data.gaps.context && <LifeAbout context={phase.data.gaps.context} />}
            demo={profile === 'demo'} onSaved={async () => { setSituation('all'); await touch(qc, 'settings'); toast('Your answers are saved'); }}
            onClose={() => setLifeOpen(false)} />}
          {offersPicks(phase.data.gaps) && <YouMightLike locked={locked} />}
          {!wide && thinking}
          {usage.kind === 'ready' && <Usage answer={usage.data} byId={byId} locked={offline || usage.savedAt !== null} />}
          {usage.kind === 'error' && (usage.offline ? <p className="notice" role="alert">{usage.message}</p>
            : <Failed query={insightsQ} what="how your closet is used" />)}
        </>
      )}
    </div>
  );

  // the same element around the page on a phone and a computer, so crossing between them (a window resized, a tablet
  // turned) keeps what is open on the page instead of drawing it afresh
  return (
    <div className={wide ? 'master-detail missing' : 'wardrobe-page'}>
      {main}
      {wide && <aside className="detail-panel missing-side" aria-label={itemId ? 'Item details' : 'Thinking of buying something?'}>
        {itemId ? (
          <>
            <div className="missing-panel-top">
              <BackLink to="/wardrobe" className="btn btn-ghost btn-small back-link"><ChevronLeftIcon /> Wardrobe</BackLink>
            </div>
            <ItemDetail key={itemId} id={itemId} status="active" inPanel />
          </>
        ) : thinking}
      </aside>}
    </div>
  );
}

function SavedEarlier({ at }: { at: string }) {
  return (
    <Notice as="p" tone="warning" className="missing-saved" role="status" icon={<WarnIcon />}>
      <span>Saved earlier{savedWhen(at)}.</span>
    </Notice>
  );
}
