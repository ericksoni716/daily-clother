/** Plain words for who described an item. */
import { dayOf, fullDate } from './wears';

/** "Described with your Claude plan on 12 Nov 2026." and the like; empty when it has not been described (or was
 * described in advance, for the demo closet). Shown once, on the details one by one in "Fix the details". */
export function describedBy(route: string | null, at: string | null): string {
  if (!route || route === 'demo') return '';
  const how = route === 'api' ? 'with your API key' : route === 'plan' ? 'with your Claude plan' : '';
  const day = at ? dayOf(at) : null;
  const when = day ? fullDate(day) : '';
  return ['Described', how, when && `on ${when}`].filter(Boolean).join(' ') + '.';
}
