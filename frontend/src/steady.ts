/**
 * Holding still what arrives late (DESIGN, "The page holds still"). Something shown above a screen (the price news,
 * an update ready to install, what a restore did) takes what is known when the screen opens, and keeps it while you
 * read: an answer that arrives later waits for the next screen you open. Only your own tap (Got it, OK) changes it in
 * between. Why: docs/DECISIONS.md, "Banners wait for the next screen".
 */
import { useCallback, useState } from 'react';

/** `value` as it was when `screen` (the page's address) opened. `take()` takes the value as it is now, after your own
 * tap changed it. */
export function useAsOpened<T>(value: T, screen: string): [T, () => void] {
  const [taken, setTaken] = useState(0);
  const [held, setHeld] = useState({ screen, taken, value });
  let shown = held.value;
  if (held.screen !== screen || held.taken !== taken) {
    // a new screen (or your tap): what is known now is what it shows (React's way of keeping state from props)
    setHeld({ screen, taken, value });
    shown = value;
  }
  const take = useCallback(() => setTaken((n) => n + 1), []);
  return [shown, take];
}
