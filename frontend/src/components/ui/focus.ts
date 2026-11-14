import type { KeyboardEvent } from 'react';

const FOCUSABLE = 'a[href], button:not(:disabled), input:not(:disabled):not([type="hidden"]), select:not(:disabled), '
  + 'textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])';

/** What Tab can reach inside `root`, in order, leaving out what is hidden. */
export function focusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.getClientRects().length > 0 && !el.closest('[inert]'));
}

/**
 * Keeps Tab and Shift+Tab inside `root` (a sheet, a dialog or a menu): from the last control Tab goes back to the
 * first, and Shift+Tab from the first goes to the last. Call it from the root's onKeyDown.
 */
export function trapTab(e: KeyboardEvent, root: HTMLElement | null) {
  if (e.key !== 'Tab' || !root) return;
  const all = focusables(root);
  if (!all.length) {
    e.preventDefault();
    root.focus();
    return;
  }
  const at = all.indexOf(document.activeElement as HTMLElement);
  if (e.shiftKey && at <= 0) {
    e.preventDefault();
    all[all.length - 1].focus();
  } else if (!e.shiftKey && (at === -1 || at === all.length - 1)) {
    e.preventDefault();
    all[0].focus();
  }
}

/**
 * For a question asked in place of a button ("Delete this item for good?"): Escape answers no and Tab stays on its
 * buttons. Use as the question's onKeyDown.
 */
export function confirmKeys(cancel: () => void) {
  return (e: KeyboardEvent<HTMLElement>) => {
    trapTab(e, e.currentTarget);
    if (e.key !== 'Escape') return;
    e.preventDefault();
    e.stopPropagation();
    cancel();
  };
}
