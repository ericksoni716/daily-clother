import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { useMediaQuery } from '../../router';
import { Button } from './Button';
import { cls } from './cls';
import { trapTab } from './focus';

/** Below this width choices open as a sheet from the bottom of the screen. */
export const PHONE = '(max-width: 699px)';

/** The sheets open now, the latest last: Escape closes the latest only, wherever focus is. */
const open: object[] = [];
/** How many phone sheets hold the page behind them still. */
let held = 0;

/** While a phone sheet is open, the page behind it does not scroll, even when you drag on the dimmed part. */
function holdPage(on: boolean) {
  held += on ? 1 : -1;
  if (typeof document !== 'undefined') document.documentElement.classList.toggle('sheet-open', held > 0);
}

/**
 * Choices that open on demand: a sheet from the bottom on a phone; on a wider screen a popover under the button that
 * opened it (`popover`) or simply in place in the page. Escape closes it from wherever focus is (the latest one open,
 * when one opened from another; something inside that takes Escape for itself, such as a line being changed, calls
 * `preventDefault` and keeps it open), and so do a tap outside a sheet or a popover. A phone sheet holds the page
 * behind it still.
 * While a sheet or a popover is open, Tab stays inside it; once it closes, focus goes back to what opened it.
 * `anchor` (the button that opened it) is for choices opened from inside something that clips or contains what it
 * holds (a carousel's slide, a card): the sheet is put at the end of the page, and on a wider screen it floats beside
 * the anchor as a popover, below it or above it, wherever it fits.
 */
export function Sheet({ title, onClose, popover, keep, anchor, closeLabel = 'Done', className, testId, children }: {
  title: string;
  onClose(): void;
  popover?: boolean;
  anchor?: RefObject<HTMLElement | null>;
  /** The button beside the title that closes it: "Done", or "Cancel" over a form that saves only with its own button. */
  closeLabel?: string;
  /** Pressing inside this (the button that opened the popover) does not count as outside. */
  keep?: RefObject<HTMLElement | null>;
  className?: string;
  testId?: string;
  children: ReactNode;
}) {
  const phone = useMediaQuery(PHONE);
  const floating = phone || !!popover || !!anchor;
  const ref = useRef<HTMLDivElement>(null);
  const place = useAnchored(anchor && !phone ? anchor : null, ref);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });

  // Escape, wherever focus is: the latest sheet open takes it, unless something inside it took it first
  useEffect(() => {
    const me = {};
    open.push(me);
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented || open[open.length - 1] !== me) return;
      e.preventDefault();
      close.current();
    };
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      open.splice(open.indexOf(me), 1);
    };
  }, []);

  useEffect(() => {
    if (!phone) return;
    holdPage(true);
    return () => holdPage(false);
  }, [phone]);

  useEffect(() => {
    if (!floating) return;
    const back = document.activeElement as HTMLElement | null;
    ref.current?.focus({ preventScroll: true });
    const outside = (e: PointerEvent) => {
      const t = e.target as Node;
      if (ref.current?.contains(t) || keep?.current?.contains(t) || anchor?.current?.contains(t)) return;
      close.current();
    };
    // on a phone the scrim takes the tap (see below), so it never reaches what is underneath
    if (!phone) document.addEventListener('pointerdown', outside);
    const target = anchor?.current;
    return () => {
      document.removeEventListener('pointerdown', outside);
      const now = document.activeElement;
      // what opened it, or (when that is gone) the anchor it was opened from
      const to = back?.isConnected ? back : target?.isConnected ? target : null;
      if (to && (!now || now === document.body || !now.isConnected)) to.focus({ preventScroll: true });
    };
  }, [floating, phone, keep, anchor]);

  const sheet = (
    <>
      {phone && <div className="sheet-scrim" aria-hidden="true" onClick={onClose} />}
      <div ref={ref} className={cls('sheet', phone ? 'sheet-phone' : popover || anchor ? 'sheet-popover' : 'sheet-inline', className)}
        role={floating ? 'dialog' : undefined} aria-modal={phone || undefined} aria-label={floating ? title : undefined}
        tabIndex={floating ? -1 : undefined} data-testid={testId} style={place}
        onKeyDown={(e) => {
          if (floating) trapTab(e, ref.current);
        }}>
        {floating && (
          <div className="sheet-head">
            <h2 className="sheet-title">{title}</h2>
            <Button variant="ghost" small onClick={onClose}>{closeLabel}</Button>
          </div>
        )}
        {children}
      </div>
    </>
  );
  return anchor && typeof document !== 'undefined' ? createPortal(sheet, document.body) : sheet;
}

/** Where a popover opened from `anchor` floats: under it (or over it, when there is more room there), kept on screen. */
function useAnchored(anchor: RefObject<HTMLElement | null> | null, sheet: RefObject<HTMLDivElement | null>): CSSProperties | undefined {
  // unseen until it is put in its place, but able to take focus meanwhile (focus goes into it as it opens)
  const [place, setPlace] = useState<CSSProperties | undefined>(anchor ? { position: 'fixed', top: 0, left: 0, opacity: 0 } : undefined);
  useLayoutEffect(() => {
    if (!anchor) return;
    const put = () => {
      const a = anchor.current?.getBoundingClientRect();
      const s = sheet.current;
      if (!a || !s) return;
      const gap = 8;
      const edge = 16;
      const vw = document.documentElement.clientWidth;
      const vh = window.innerHeight;
      const w = s.offsetWidth;
      const h = s.offsetHeight;
      const left = Math.max(edge, Math.min(a.left + w <= vw - edge ? a.left : a.right - w, vw - w - edge));
      const below = vh - a.bottom - gap - edge;
      const top = h <= below || below >= a.top - gap - edge ? a.bottom + gap : Math.max(edge, a.top - gap - h);
      setPlace({ position: 'fixed', top, left });
    };
    put();
    // its height changes as what is inside it arrives (a place's weather, a search's answers)
    const grown = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(put);
    if (sheet.current) grown?.observe(sheet.current);
    window.addEventListener('scroll', put, true);
    window.addEventListener('resize', put);
    return () => {
      grown?.disconnect();
      window.removeEventListener('scroll', put, true);
      window.removeEventListener('resize', put);
    };
  }, [anchor, sheet]);
  return anchor ? place : undefined;
}
