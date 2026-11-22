/**
 * The door through Cloudflare, as Settings shows it on the computer (under Other devices): an address of Nines' own on a
 * domain the owner has on Cloudflare, behind Cloudflare's sign-in, for a browser that cannot use Tailscale. The server
 * checks Cloudflare's signed sign-in on every request there (backend/closet/access.py). Words and decisions only.
 */
import type { CloudflareDoor } from './types';

export const README_CLOUDFLARE = 'https://github.com/ericksoni716/daily-clother#use-it-without-tailscale-through-cloudflare';

/** The fold's title: what it is while it is off, and where Nines answers once it is on. */
export function doorTitle(door: CloudflareDoor): string {
  return door.on && door.host ? `Also through Cloudflare, at ${door.host}` : 'Without Tailscale, through Cloudflare';
}

export const DOOR_ABOUT =
  'With a domain of your own on Cloudflare, Nines can have its own address there, for a browser that cannot use ' +
  'Tailscale. Cloudflare asks for a code sent to your email before Nines opens, and it can read what passes through.';

export function doorStatus(door: CloudflareDoor): string {
  if (door.on && door.host) return `Nines answers at https://${door.host} once Cloudflare has checked who you are.`;
  return 'This is off until all three are filled in.';
}

export type DoorField = 'cloudflare_team' | 'cloudflare_aud' | 'cloudflare_host';

export const DOOR_FIELDS: { key: DoorField; label: string; placeholder: string }[] = [
  { key: 'cloudflare_team', label: 'Your Cloudflare team', placeholder: 'yourteam.cloudflareaccess.com' },
  { key: 'cloudflare_aud', label: "The Access application's audience tag", placeholder: 'A long run of letters and numbers' },
  { key: 'cloudflare_host', label: "Nines' address on Cloudflare", placeholder: 'nines.example.com' },
];

/** What the boxes show to begin with: what is saved. */
export function doorValues(door: CloudflareDoor): Record<DoorField, string> {
  return { cloudflare_team: door.team ?? '', cloudflare_aud: door.aud ?? '', cloudflare_host: door.host ?? '' };
}

/** Whether the boxes say something other than what is saved (Save is offered only then). */
export function doorChanged(door: CloudflareDoor, typed: Record<DoorField, string>): boolean {
  const saved = doorValues(door);
  return DOOR_FIELDS.some(({ key }) => typed[key].trim() !== saved[key]);
}

/** The change to send: every box, trimmed; an empty one clears that setting (and so turns the door off). */
export function doorChange(typed: Record<DoorField, string>): Record<DoorField, string> {
  return { cloudflare_team: typed.cloudflare_team.trim(), cloudflare_aud: typed.cloudflare_aud.trim(), cloudflare_host: typed.cloudflare_host.trim() };
}
