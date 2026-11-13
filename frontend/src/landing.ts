/** Which screen the app opens on: Today, once the closet has enough clothes to dress from. */
import { useEffect } from 'react';
import { navigate } from './router';
import { canDress } from './today';
import type { ItemSummary } from './types';

const KEY = 'closet-landed';

function session(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Forget that this tab already opened, so the next screen after logging in is chosen again. */
export function forgetLanding() {
  try {
    session()?.removeItem(KEY);
  } catch {
    /* nothing kept */
  }
}

/**
 * The first time a tab (or the home-screen app) opens the closet's front page, it moves to Today when the closet
 * can dress the owner. Only once per tab, so tapping Closet, reloading or switching closets stays where it was.
 */
export function useLanding(path: string, items: ItemSummary[] | null) {
  useEffect(() => {
    const kv = session();
    if (!kv || kv.getItem(KEY)) return;
    if (path !== '/') {
      kv.setItem(KEY, '1');
      return;
    }
    if (items === null) return;
    kv.setItem(KEY, '1');
    if (canDress(items)) navigate('/today', { replace: true });
  }, [path, items]);
}
