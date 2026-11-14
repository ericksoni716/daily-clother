import { useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { useMediaQuery } from '../../router';
import { Button } from './Button';
import { cls } from './cls';
import { trapTab } from './focus';

/** Below this width choices open as a sheet from the bottom of the screen. */
export const PHONE = '(max-width: 699px)';

/**
 * Choices that open on demand: a sheet from the bottom on a phone; on a wider screen a popover under the button that
 * opened it (`popover`) or simply in place in the page. Escape closes it, and so do a tap outside a sheet or a popover.
 * While a sheet or a popover is open, Tab stays inside it; once it closes, focus goes back to what opened it.
 */
export function Sheet({ title, onClose, popover, keep, className, testId, children }: {
  title: string;
  onClose(): void;
  popover?: boolean;
  /** Pressing inside this (the button that opened the popover) does not count as outside. */
  keep?: RefObject<HTMLElement | null>;
  className?: string;
  testId?: string;
  children: ReactNode;
}) {
  const phone = useMediaQuery(PHONE);
  const floating = phone || !!popover;
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });

  useEffect(() => {
    if (!floating) return;
    const back = document.activeElement as HTMLElement | null;
    ref.current?.focus({ preventScroll: true });
    const outside = (e: PointerEvent) => {
      const t = e.target as Node;
      if (ref.current?.contains(t) || keep?.current?.contains(t)) return;
      close.current();
    };
    // on a phone the scrim takes the tap (see below), so it never reaches what is underneath
    if (!phone) document.addEventListener('pointerdown', outside);
    return () => {
      document.removeEventListener('pointerdown', outside);
      const now = document.activeElement;
      if (back?.isConnected && (!now || now === document.body)) back.focus({ preventScroll: true });
    };
  }, [floating, phone, keep]);

  return (
    <>
      {phone && <div className="sheet-scrim" aria-hidden="true" onClick={onClose} />}
      <div ref={ref} className={cls('sheet', phone ? 'sheet-phone' : popover ? 'sheet-popover' : 'sheet-inline', className)}
        role={floating ? 'dialog' : undefined} aria-modal={phone || undefined} aria-label={floating ? title : undefined}
        tabIndex={floating ? -1 : undefined} data-testid={testId}
        onKeyDown={(e) => {
          if (floating) trapTab(e, ref.current);
          if (e.key !== 'Escape') return;
          e.stopPropagation();
          onClose();
        }}>
        {floating && (
          <div className="sheet-head">
            <h2 className="sheet-title">{title}</h2>
            <Button variant="ghost" small onClick={onClose}>Done</Button>
          </div>
        )}
        {children}
      </div>
    </>
  );
}
