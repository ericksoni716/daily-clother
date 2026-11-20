import type { AnchorHTMLAttributes, MouseEvent } from 'react';
import { goBack, Link } from '../../router';

/**
 * Every "‹ Somewhere" link. It goes Back when the page before is the one it names, so that page returns where you
 * left it and history does not grow; opened straight from an address, the named page takes this one's place.
 * A click with a modifier key (a new tab, say) still follows the address.
 */
export function BackLink({ to, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  return (
    <Link
      to={to}
      {...rest}
      onClick={(e: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(e);
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        goBack(to);
      }}
    />
  );
}
