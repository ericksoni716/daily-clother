/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { clock, dayAndTime, fullDate, localDay, longDate, monthYear, shortDate, sinceWash, wearDay, wearSummary, whenAt, whenWorn } from './wears';

// Thursday 12 November 2026
const TODAY = '2026-11-12';

describe('worn N times, last on …', () => {
  it('says when nothing has been worn', () => {
    expect(wearSummary(0, null, TODAY)).toBe('Not worn yet');
    expect(wearSummary(0, undefined, TODAY)).toBe('Not worn yet');
  });

  it('says once, then a count', () => {
    expect(wearSummary(1, '2026-11-12', TODAY)).toBe('Worn once, today');
    expect(wearSummary(1, '2026-11-11', TODAY)).toBe('Worn once, yesterday');
    expect(wearSummary(6, '2026-11-10', TODAY)).toBe('Worn 6 times, last on Tuesday');
    expect(wearSummary(2, '2026-11-12', TODAY)).toBe('Worn 2 times, last today');
  });

  it('names the weekday within the past week, the date before that, and the year only when it differs', () => {
    expect(whenWorn('2026-11-06', TODAY)).toBe('on Friday');
    expect(whenWorn('2026-11-05', TODAY)).toBe('on 5 Nov');
    expect(whenWorn('2025-12-30', TODAY)).toBe('on 30 Dec 2025');
    expect(whenWorn('2027-01-01', '2027-01-04')).toBe('on Friday');
    expect(whenWorn('2026-12-31', '2027-01-01')).toBe('yesterday');
  });

  it('lists days in plain words', () => {
    expect(wearDay('2026-11-12', TODAY)).toBe('Today');
    expect(wearDay('2026-11-11', TODAY)).toBe('Yesterday');
    expect(wearDay('2026-11-10', TODAY)).toBe('Tuesday 10 Nov');
    expect(wearDay('2026-10-01', TODAY)).toBe('1 Oct');
  });

  it('counts wears since the wash', () => {
    expect(sinceWash(0)).toBe('Not worn since it was washed');
    expect(sinceWash(1)).toBe('Worn once since it was washed');
    expect(sinceWash(3)).toBe('Worn 3 times since it was washed');
  });

  it('gives today as a local calendar day', () => {
    expect(localDay(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05');
  });
});

describe('one way to write a date', () => {
  const at = (h: number, m: number, day = 23) => new Date(2026, 10, day, h, m).toISOString();
  it('writes a day, a day and a time, and a month the same everywhere', () => {
    expect(longDate('2026-11-12')).toBe('Thursday 12 Nov');
    expect(shortDate('2026-11-25')).toBe('Wed 25 Nov');
    expect(fullDate('2026-11-03')).toBe('3 Nov 2026');
    expect(monthYear('2026-11')).toBe('November 2026');
    expect(clock(at(4, 49))).toBe('04:49');
    expect(clock(at(14, 5))).toBe('14:05');
    expect(whenAt(at(4, 49), '2026-11-23')).toBe('today at 04:49');
    expect(whenAt(at(21, 0, 22), '2026-11-23')).toBe('yesterday at 21:00');
    expect(whenAt(at(9, 41, 3), '2026-11-23')).toBe('on 3 Nov at 09:41');
    expect(dayAndTime(at(4, 40), '2026-11-23')).toBe('Today, 04:40');
    expect(dayAndTime(at(9, 41, 13), '2026-11-23')).toBe('13 Nov, 09:41');
    expect(whenAt('not a time')).toBe('');
  });

  // Every date the owner reads goes through this file; a screen that formats one by itself (the browser's locale
  // gave "Nov 23, 2026, 05:07 AM" beside "Mon 23 Nov") fails here.
  it('is the only place a date or a time is formatted', () => {
    const src = import.meta.dirname;
    const files = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return files(path);
      return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
    });
    const found = files(src).filter((f) => relative(src, f) !== 'wears.ts').flatMap((f) => {
      const text = readFileSync(f, 'utf8');
      const bad = [
        ...text.matchAll(/toLocale(Date|Time)String\(|Intl\.DateTimeFormat|toLocaleString\((?!'en-US')|\.get(Hours|Minutes)\(\)(?!\))|'Jan', 'Feb'/g),
      ];
      return bad.map((m) => `${relative(src, f)}: ${m[0]}`);
    });
    // the hour of day the morning question is asked at is a number, not words for the owner (worn.ts)
    expect(found.filter((f) => f !== 'worn.ts: .getHours()')).toEqual([]);
  });
});
