import { describe, expect, it } from 'vitest';
import { aboutUsd, dayName, formatUsd, importLine, monthName, spentLine, suggestionLine, turnedOffLine, waitingLine } from './spend';

describe('money wording', () => {
  it('shows dollars and cents, and never a fraction of a cent', () => {
    expect(formatUsd(0)).toBe('$0.00');
    expect(formatUsd(null)).toBe('$0.00');
    expect(formatUsd(0.0024)).toBe('under 1¢');
    expect(formatUsd(0.006)).toBe('$0.01');
    expect(formatUsd(1.2)).toBe('$1.20');
    expect(formatUsd(1000)).toBe('$1,000.00');
    expect(aboutUsd(0.003)).toBe('under 1¢');
    expect(aboutUsd(0.03)).toBe('about $0.03');
  });

  it('names months and days', () => {
    expect(monthName('2026-11')).toBe('November 2026');
    expect(monthName('2027-01')).toBe('January 2027');
    expect(dayName('2026-11-03')).toBe('3 Nov 2026');
  });

  it('says what this month has cost', () => {
    expect(spentLine({ spent_usd: 0.42, cap_usd: 5, api_calls: 12, plan_calls: 0 }))
      .toBe('$0.42 of your $5.00 limit spent; 12 requests to Claude with the API key.');
    expect(spentLine({ spent_usd: 0, cap_usd: null, api_calls: 0, plan_calls: 1 }))
      .toBe('$0.00 spent; nothing sent with the API key. 1 request went through your Claude plan, at no extra cost.');
  });

  it('estimates waiting items and an import, and explains the suggested limit', () => {
    expect(waitingLine({ items: 0, photos: 0, at_most_usd: 0 })).toBe('');
    expect(waitingLine({ items: 1, photos: 1, at_most_usd: 0.003 }))
      .toBe("If your plan can't be used, describing the item waiting with the API key would cost under 1¢ at most.");
    expect(waitingLine({ items: 40, photos: 40, at_most_usd: 0.12 }))
      .toBe("If your plan can't be used, describing the 40 items waiting with the API key would cost about $0.12 at most.");
    expect(importLine(10, 0.003)).toBe("About $0.03 for these 10 photos with the API key, if your plan can't be used.");
    expect(importLine(1, 0.003)).toBe("Under 1¢ for this photo with the API key, if your plan can't be used.");
    expect(suggestionLine(5, 0.00296, '2026-11-03')).toMatch(/^We suggest \$5\.00 a month\. At the prices written down on 3 Nov 2026, that pays for at least 1,689 photos/);
  });

  it('says why the key was switched off', () => {
    expect(turnedOffLine(null)).toBe('');
    expect(turnedOffLine({ at: '2026-11-12T10:00:00Z', reason: 'credit' })).toMatch(/on 12 Nov 2026 because Anthropic said your account has no credit left/);
    expect(turnedOffLine({ at: '2026-11-12T10:00:00Z', reason: 'key' })).toMatch(/didn't accept the key/);
  });
});
