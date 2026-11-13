/** Which navigation link is lit for a route, in the sidebar and in the phone's tab bar. */
import type { Route } from './router';

/**
 * The part of the app a route belongs to: Archived, an item and Insights are part of the closet, Worn is part of
 * Today, Would this work? is part of What's missing. Review and Trips are their own sidebar links.
 */
export function navSection(route: Route): string {
  if (route.name === 'insights') return 'closet';
  if (route.name === 'worn') return 'today';
  return route.name;
}

/** The phone tab for a section: the tab bar has no Trips or Review, so Trips lights Today and Review lights Closet. */
export function tabFor(section: string): string {
  if (section === 'trips') return 'today';
  if (section === 'review') return 'closet';
  return section;
}
