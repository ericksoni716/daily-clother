/** "Use my location": the browser's position, asked only when the owner taps, named as a place by the server. */
import type { Place } from './types';

export type Located =
  | { kind: 'found'; place: Place }
  | { kind: 'insecure' | 'unsupported' | 'refused' | 'unavailable' | 'failed'; message: string };

/** What locating needs from the browser and the server; tests give stand-ins. */
export interface LocateEnv {
  /** Whether the page is a secure context (https or this computer); browsers only share a position with those. */
  secure: boolean;
  geolocation: Pick<Geolocation, 'getCurrentPosition'> | undefined;
  /** The place at a position (the server asks OpenStreetMap, sending only the coordinates, rounded). */
  near(latitude: number, longitude: number): Promise<Place>;
}

/** One sentence each; the search by name stays beside them. */
export const LOCATION_WORDS = {
  insecure: "Your browser only shares your location over a secure connection, which this page doesn't have, so search for your place by name instead.",
  unsupported: "This browser can't share your location, so search for your place by name instead.",
  refused: "Your browser didn't share your location, so search for your place by name instead (or allow it for this page in the browser's settings).",
  unavailable: "Your browser couldn't find your location just now, so try again or search for your place by name.",
} as const;

const PERMISSION_DENIED = 1;

/** Where the owner is, from the browser: never called except from the owner's tap. */
export async function locate(env: LocateEnv): Promise<Located> {
  if (!env.secure) return { kind: 'insecure', message: LOCATION_WORDS.insecure };
  const geo = env.geolocation;
  if (!geo) return { kind: 'unsupported', message: LOCATION_WORDS.unsupported };
  let coords: GeolocationCoordinates;
  try {
    coords = await new Promise<GeolocationCoordinates>((resolve, reject) => {
      // a town is all that is needed: no high accuracy, and a position from the last ten minutes will do
      geo.getCurrentPosition((p) => resolve(p.coords), reject, { enableHighAccuracy: false, timeout: 15_000, maximumAge: 600_000 });
    });
  } catch (e) {
    const refused = (e as GeolocationPositionError | undefined)?.code === PERMISSION_DENIED;
    return refused ? { kind: 'refused', message: LOCATION_WORDS.refused } : { kind: 'unavailable', message: LOCATION_WORDS.unavailable };
  }
  try {
    return { kind: 'found', place: await env.near(coords.latitude, coords.longitude) };
  } catch (e) {
    return { kind: 'failed', message: (e as Error).message };
  }
}
