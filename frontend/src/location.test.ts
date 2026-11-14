import { describe, expect, it, vi } from 'vitest';
import { locate, LOCATION_WORDS, type LocateEnv } from './location';
import type { Place } from './types';

const HOBOKEN: Place = { name: 'Hoboken, New Jersey, United States', latitude: 40.75, longitude: -74.03, timezone: 'auto' };

/** A stand-in for navigator.geolocation that answers with a position or an error, and counts the questions. */
function geolocation(answer: { latitude: number; longitude: number } | { code: number }) {
  return {
    getCurrentPosition: vi.fn((ok: PositionCallback, fail?: PositionErrorCallback | null) => {
      if ('code' in answer) fail?.({ code: answer.code, message: 'no', PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 } as GeolocationPositionError);
      else ok({ coords: { ...answer, accuracy: 20 }, timestamp: 0 } as unknown as GeolocationPosition);
    }),
  };
}

function env(over: Partial<LocateEnv>): LocateEnv & { near: ReturnType<typeof vi.fn> } {
  return { secure: true, geolocation: geolocation({ latitude: 40.745123, longitude: -74.032456 }), near: vi.fn(async () => HOBOKEN), ...over } as never;
}

describe('use my location', () => {
  it('when the browser shares the position, the server names it and the place is given back', async () => {
    const e = env({});
    expect(await locate(e)).toEqual({ kind: 'found', place: HOBOKEN });
    expect(e.geolocation!.getCurrentPosition).toHaveBeenCalledTimes(1);
    expect(e.near).toHaveBeenCalledWith(40.745123, -74.032456);
  });

  it('when the owner or the browser refuses, says so in one sentence and asks the server nothing', async () => {
    const e = env({ geolocation: geolocation({ code: 1 }) });
    expect(await locate(e)).toEqual({ kind: 'refused', message: LOCATION_WORDS.refused });
    expect(e.near).not.toHaveBeenCalled();
    expect(await locate(env({ geolocation: geolocation({ code: 3 }) }))).toEqual({ kind: 'unavailable', message: LOCATION_WORDS.unavailable });
  });

  it('on a page that is not a secure context (a phone over plain http), explains without asking the browser', async () => {
    const e = env({ secure: false });
    expect(await locate(e)).toEqual({ kind: 'insecure', message: LOCATION_WORDS.insecure });
    expect(e.geolocation!.getCurrentPosition).not.toHaveBeenCalled();
    expect(e.near).not.toHaveBeenCalled();
  });

  it('without geolocation in the browser, or when the server cannot name the place, says why', async () => {
    expect(await locate(env({ geolocation: undefined }))).toEqual({ kind: 'unsupported', message: LOCATION_WORDS.unsupported });
    const failing = env({ near: vi.fn(async () => { throw new Error('No town or city was found where you are.'); }) });
    expect(await locate(failing)).toEqual({ kind: 'failed', message: 'No town or city was found where you are.' });
  });

  it('every explanation is one sentence', () => {
    for (const words of Object.values(LOCATION_WORDS)) expect(words.match(/[.!?](\s|$)/g)).toHaveLength(1);
  });
});
