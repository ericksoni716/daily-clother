import { describe, expect, it } from 'vitest';
import { activeSituations, FREQUENCIES, frequencyWords, lifeSummary, newLife, situationLabel } from './life';

describe('life answers', () => {
  it('offers the four approximate frequencies without rounding existing numeric answers', () => {
    expect(FREQUENCIES.map((f) => f.value)).toEqual([0, .25, 1, 4]);
    expect(frequencyWords(.25)).toBe('Now and then');
    expect(frequencyWords(3.5)).toBe('3.5 days a week');
    expect(frequencyWords(7)).toBe('7 days a week');
  });

  it('offers filters only for active situations, including occasional days', () => {
    const life = newLife();
    life.situations.work = .25;
    expect(activeSituations(life).map((s) => s.id)).toEqual(['work', 'everyday']);
    expect(activeSituations(null)).toEqual([]);
    expect(activeSituations(undefined)).toEqual([]);
    expect(situationLabel('going_out')).toBe('Going out');
    life.situations.vacation = 1;
    expect(activeSituations(life).map((s) => s.id)).not.toContain('vacation');
    life.vacation_weeks = 2;
    expect(activeSituations(life).map((s) => s.id)).toContain('vacation');
  });

  it('keeps new answers independent, and does not change saved answers when filtering', () => {
    const life = newLife();
    life.situations.everyday = 7;
    activeSituations(life);
    expect(life.situations.everyday).toBe(7);
    expect(newLife().situations.everyday).toBe(4);
  });

  it('summarises the actual active answers, work dress and time away in plain words', () => {
    const life = newLife();
    life.situations.work = 3.5;
    life.work_dress = 'smart_casual';
    life.situations.going_out = .25;
    life.situations.vacation = 1;
    life.vacation_weeks = 2;
    expect(lifeSummary(life)).toEqual([
      'work 3.5 days a week, smart casual', 'everyday 4 days a week', 'going out now and then',
      'vacation 2 weeks a year, warm and cold',
    ]);
    expect(lifeSummary(null)).toEqual([]);
    life.vacation_weeks = 0;
    expect(lifeSummary(life)).not.toContain('vacation 0 weeks a year, warm and cold');
  });
});
