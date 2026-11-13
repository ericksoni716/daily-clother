import { describe, expect, it } from 'vitest';
import type { Weather } from './types';
import { weatherLine } from './weather';

const day: Weather = { date: '2026-11-12', low_c: 3.2, high_c: 9.8, rain_chance: 70, rain: true, summary: 'rain', fetched_at: '2026-11-12T17:00:00Z' };

describe('the weather in one line', () => {
  it('gives the low, the high, the summary and the chance of rain', () => {
    expect(weatherLine(day)).toBe('3°C to 10°C, rain (70% chance of rain)');
  });

  it('says "about" when the low and high round the same, and leaves out an unknown chance', () => {
    expect(weatherLine({ ...day, low_c: 21.6, high_c: 22.4, rain_chance: null, summary: 'clear' })).toBe('About 22°C, clear');
  });
});
