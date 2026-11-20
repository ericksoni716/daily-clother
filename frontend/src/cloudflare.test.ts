import { describe, expect, it } from 'vitest';
import { doorChange, doorChanged, doorStatus, doorTitle, doorValues } from './cloudflare';
import type { CloudflareDoor } from './types';

const off: CloudflareDoor = { team: null, aud: null, host: null, on: false };
const on: CloudflareDoor = { team: 'yourteam.cloudflareaccess.com', aud: 'a1b2c3d4e5f6a7b8', host: 'closet.example.com', on: true };

describe('the door through Cloudflare in Settings', () => {
  it('is named for what it is while off, and for where Nines answers once on', () => {
    expect(doorTitle(off)).toBe('Without Tailscale, through Cloudflare');
    expect(doorTitle({ ...on, on: false })).toBe('Without Tailscale, through Cloudflare');
    expect(doorTitle(on)).toBe('Also through Cloudflare, at closet.example.com');
    expect(doorStatus(off)).toBe('This is off until all three are filled in.');
    expect(doorStatus(on)).toBe('Nines answers at https://closet.example.com once Cloudflare has checked who you are.');
  });

  it('offers Save only when a box says something new, and sends every box trimmed', () => {
    expect(doorChanged(on, doorValues(on))).toBe(false);
    expect(doorChanged(on, { ...doorValues(on), cloudflare_host: ' closet.example.com ' })).toBe(false);
    expect(doorChanged(on, { ...doorValues(on), cloudflare_aud: '' })).toBe(true);
    expect(doorChanged(off, { ...doorValues(off), cloudflare_team: 'yourteam' })).toBe(true);
    expect(doorChange({ cloudflare_team: ' yourteam ', cloudflare_aud: '', cloudflare_host: 'closet.example.com' }))
      .toEqual({ cloudflare_team: 'yourteam', cloudflare_aud: '', cloudflare_host: 'closet.example.com' });
  });
});
