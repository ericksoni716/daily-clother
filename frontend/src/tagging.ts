/** Plain words for who described an item. */

/** "Described with your Claude plan on 12 Nov 2026." and the like; empty when it has not been described (or was
 * described in advance, for the demo closet). Shown once, on the details one by one in "Fix the details". */
export function describedBy(route: string | null, at: string | null): string {
  if (!route || route === 'demo') return '';
  const how = route === 'api' ? 'with your API key' : route === 'plan' ? 'with your Claude plan' : '';
  const when = at ? new Date(at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  return ['Described', how, when && `on ${when}`].filter(Boolean).join(' ') + '.';
}
