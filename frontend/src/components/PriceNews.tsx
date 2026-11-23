import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { api } from '../api';
import { queryKeys } from '../queryKeys';
import { navigate, wishPath } from '../router';
import { NEWS_POLL_MS, newsWords } from '../shop';
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
 * you look; for several wishes, how many, with See them and Got it. Asked for when the page opens, every half hour
 * while it is shown, and when it comes back into view; never while it is hidden, offline, or in the demo closet.
 */
export function PriceNewsBanner({ offline, toast }: { offline: boolean; toast: Toast }) {
  const { profile } = useApp();
  const seen = useNewsSeen();
  const [busy, setBusy] = useState(false);
  const news = useQuery({
    queryKey: queryKeys.news(), queryFn: api.wishNews, enabled: !offline && profile !== 'demo', refetchInterval: NEWS_POLL_MS,
  }).data ?? [];
  if (offline || profile === 'demo' || news.length === 0) return null;

  async function gotIt(ids: string[]) {
    setBusy(true);
    try {
      await seen(ids);
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
        {/* opening the wish marks its news seen (its page does) */}
        <Button variant="primary" small disabled={busy} onClick={() => navigate(one ? wishPath(one.wish_id) : '/wardrobe')}>
          {one ? 'See it' : 'See them'}
        </Button>
        <Button variant="ghost" small disabled={busy} onClick={() => void gotIt(news.map((n) => n.wish_id))}>Got it</Button>
      </>}>
      {newsWords(news)}
    </Notice>
  );
}
