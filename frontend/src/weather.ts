import type { Weather } from './types';

/** "3°C to 10°C, rain (70% chance of rain)": a day's forecast in one line. */
export function weatherLine(w: Weather): string {
  const deg = (n: number) => `${Math.round(n)}°C`;
  const temps = Math.round(w.low_c) === Math.round(w.high_c) ? `About ${deg(w.high_c)}` : `${deg(w.low_c)} to ${deg(w.high_c)}`;
  const chance = w.rain_chance === null ? '' : ` (${w.rain_chance}% chance of rain)`;
  return `${temps}, ${w.summary}${chance}`;
}
