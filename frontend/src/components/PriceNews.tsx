import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { queryKeys } from '../queryKeys';
import { navigate, WISHLIST_PATH, wishPath } from '../router';
import { keepNews, keptNews, NEWS_POLL_MS, newsWords } from '../shop';
import { useAsOpened } from '../steady';
import { useApp } from '../store';
import { Button, Notice } from './ui';

type Toast = (m: string, k?: 'ok' | 'error') => void;

/** Tells the server you have seen these wishes' price news, and puts the news that is left in the banner's copy. */
export function useNewsSeen() {
  const qc = useQueryClient();
  return useCallback(async (wishIds: string[]) => {
    qc.setQueryData(queryKeys.news(), await api.newsSeen(wishIds));
  }, [qc]);
}

/**
 * "A tan rain coat is down to $150.00 at Example Shop, from $177.00." with See it and Got it, on every screen until
 * you look; for several wishes, how many, with See them (the wishlist) and Got it. Asked for when the page opens,
 * every half hour while it is shown, and when it comes back into view; never while it is hidden, offline, or in the
 * demo closet. It holds still: it shows the news known when the screen opened (the copy kept on this device, before
 * the first answer), and news that arrives while you read waits for the next screen (`useAsOpened`). The wish whose
 * page is open (`wishId`) is left out: its page is the news.
 */
export function PriceNewsBanner({ offline, toast, screen, wishId }: { offline: boolean; toast: Toast; screen: string; wishId: string | null }) {
  const { profile } = useApp();
  const seen = useNewsSeen();
  const [busy, setBusy] = useState(false);
  const asked = !offline && profile !== 'demo';
  const live = useQuery({ queryKey: queryKeys.news(), queryFn: api.wishNews, enabled: asked, refetchInterval: NEWS_POLL_MS }).data;
  const [kept] = useState(() => keptNews(profile));
  useEffect(() => {
    if (live) keepNews(profile, live);
  }, [live, profile]);
  const [opened, take] = useAsOpened(asked ? live ?? kept ?? [] : [], screen);
  const news = opened.filter((n) => n.wish_id !== wishId);
  if (!asked || news.length === 0) return null;

  async function gotIt(ids: string[]) {
    setBusy(true);
    try {
      await seen(ids);
      take();
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  const one = news.length === 1 ? news[0] : null;
  return (
    <Notice role="status" testId="price-news" className="update-notice"
      action={<>
        {/* opening the wish marks its news seen (its page does); the wishlist is not each wish, so it marks nothing */}
        <Button variant="primary" small disabled={busy} onClick={() => navigate(one ? wishPath(one.wish_id) : WISHLIST_PATH)}>
          {one ? 'See it' : 'See them'}
        </Button>
        <Button variant="ghost" small disabled={busy} onClick={() => void gotIt(news.map((n) => n.wish_id))}>Got it</Button>
      </>}>
      {newsWords(news)}
    </Notice>
  );
}
