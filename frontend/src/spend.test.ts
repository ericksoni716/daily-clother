import { describe, expect, it } from 'vitest';
import { aboutUsd, amount, apiKeyLine, apiKeySavedLine, dayName, earlierMonths, monthSpentLine, requestsLine, firstRouteLine, formatUsd, importLine, monthName, PRICE_HINT, readAmount, readCents, ROUTE_ORDERS, spentLine, suggestionLine, turnedOffLine, waitingLine } from './spend';

describe('reading a price you typed', () => {
  // one reader for every box a price is typed in: an item's price, the review card, a wish's most you'd pay, a code's
  // amount off and the monthly limit. A phone set to a region that writes 45,50 has a comma on its decimal keypad.
  it.each([
    ['45', 45],
    ['45.50', 45.5],
    ['45,50', 45.5],
    ['45,5', 45.5],
    ['0,99', 0.99],
    ['99,50', 99.5],
    ['1,234.50', 1234.5],
    ['1.234,50', 1234.5],
    ['1,234', 1234],
    ['1,234,567.89', 1234567.89],
    ['1.234.567,89', 1234567.89],
    ['1 234,50', 1234.5],
    ['$45', 45],
    ['$ 45.50', 45.5],
    ['45 $', 45],
    ['€45,50', 45.5],
    ['£12', 12],
    [' 120.50 ', 120.5],
    ['.5', 0.5],
    ['45.', 45],
    ['0', 0],
  ])('reads %j as %d', (typed, amount) => {
    expect(readAmount(typed)).toBe(amount);
  });

  it.each(['', '   ', '$'])('reads %j as no price', (typed) => {
    expect(readAmount(typed)).toBeNull();
  });

  it.each(['forty', '-5', '45.505', '45,505,5', '1.234', '1,23,456', '1.234.56', '45..5', '4 5', '1e3', '12abc', '1,234.567', '1.2,3', '$$45'])(
    'refuses %j rather than guess', (typed) => {
      expect(readAmount(typed)).toBeUndefined();
    });

  it('gives cents for what is stored in cents, and a sentence for what it cannot read', () => {
    expect(readCents('45,50')).toBe(4550);
    expect(readCents('99,50')).toBe(9950);
    expect(readCents('0.29')).toBe(29);
    expect(readCents('')).toBeNull();
    expect(readCents('abc')).toBeUndefined();
    expect(PRICE_HINT).toBe('Type the price as a number, like 45 or 45.50.');
  });
});

describe('money wording', () => {
  it('says what something cost, whole amounts without cents, in its own currency, never converted', () => {
    expect(amount(124000)).toBe('$1,240');
    expect(amount(4550)).toBe('$45.50');
    expect(amount(300, '$', true)).toBe('$3.00');
    expect(amount(8000, 'EUR')).toBe('€80');
    expect(amount(1999, 'GBP')).toBe('£19.99');
    expect(amount(8000, 'ZZZ')).toMatch(/^(ZZZ\s?80|80 ZZZ)$/);
  });

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

describe('the API key box', () => {
  const none = { set: false, source: null, can_save: true, where: "this Mac's keychain" } as const;
  it('says where the key comes from, never the key', () => {
    expect(apiKeyLine(none)).toBe('No API key yet.');
    expect(apiKeyLine({ ...none, set: true, source: 'keychain' })).toBe("Your API key is saved in this Mac's keychain.");
    expect(apiKeyLine({ ...none, set: true, source: 'keychain', where: 'Windows Credential Manager' }))
      .toBe('Your API key is saved in Windows Credential Manager.');
    expect(apiKeyLine({ ...none, set: true, source: 'environment' })).toBe('Your API key comes from ANTHROPIC_API_KEY, set on this computer.');
    // read on the phone, "this Mac" would be the phone
    expect(apiKeyLine({ ...none, set: true, source: 'keychain' }, false)).toBe("Your API key is saved in your Mac's keychain.");
    expect(apiKeyLine({ ...none, set: true, source: 'environment' }, false)).toBe('Your API key comes from ANTHROPIC_API_KEY, set on your computer.');
  });
  it('says whether Anthropic checked it, and what to do next', () => {
    const saved = { ...none, set: true, source: 'keychain' as const };
    expect(apiKeySavedLine({ ...saved, checked: true }, false)).toBe('Key saved. Anthropic accepted it. Turn on Allow the API key below to use it.');
    expect(apiKeySavedLine({ ...saved, checked: true }, true)).toBe('Key saved. Anthropic accepted it.');
    expect(apiKeySavedLine({ ...saved, checked: false }, true)).toMatch(/^Key saved\. Nines couldn't reach Anthropic/);
  });
});

describe('which route is tried first', () => {
  const plan = { id: 'plan' as const, available: true, detail: '' };
  const api = { id: 'api' as const, available: true, detail: '' };

  it('offers the four orders in plain words, the plan first by default, and marks the ones that need a key', () => {
    expect(ROUTE_ORDERS.map((o) => o.value)).toEqual(['auto', 'api-first', 'plan', 'api']);
    expect(ROUTE_ORDERS.map((o) => o.label)).toEqual(['Your plan first, then the key', 'The key first, then your plan', 'Only your plan', 'Only the key']);
    expect(ROUTE_ORDERS.filter((o) => o.needsKey).map((o) => o.value)).toEqual(['api-first', 'api']);
  });

  it('names the first route in the order that is ready, the key only once it is allowed', () => {
    expect(firstRouteLine(['plan', 'api'], [plan, api], true)).toBe('Nines will try your Claude plan first.');
    expect(firstRouteLine(['api', 'plan'], [api, plan], true)).toBe('Nines will try your API key first.');
    expect(firstRouteLine(['api', 'plan'], [api, plan], false)).toBe('Nines will try your Claude plan first.');
    expect(firstRouteLine(['plan', 'api'], [{ ...plan, available: false }, api], true)).toBe('Nines will try your API key first.');
    expect(firstRouteLine(['api'], [api], false)).toBe('');
    expect(firstRouteLine(['plan'], [{ ...plan, available: false }], true)).toBe('');
  });
});

describe('the months folded under the limit', () => {
  it('lists the months before this one, leaving this month to its own sentence', () => {
    const m = (month: string, spent_usd: number) => ({ month, api_calls: 1, plan_calls: 0, spent_usd, input_tokens: 0, output_tokens: 0 });
    expect(earlierMonths({ month: '2026-11', history: [m('2026-11', 0.16), m('2026-10', 1.2), m('2026-08', 0.4)] }).map((x) => x.month))
      .toEqual(['2026-10', '2026-08']);
    expect(earlierMonths({ month: '2026-11', history: [m('2026-11', 0.16)] })).toEqual([]);
  });
});

describe('the month in a few words, and its requests', () => {
  it('says the month, what is spent and the limit', () => {
    expect(monthSpentLine({ month: '2026-11', spent_usd: 0.42, cap_usd: 5 })).toBe('November: $0.42 of $5.00 spent.');
    expect(monthSpentLine({ month: '2026-11', spent_usd: 0, cap_usd: 5 })).toBe('November: nothing spent yet of $5.00.');
    expect(monthSpentLine({ month: '2026-11', spent_usd: 0.42, cap_usd: null })).toBe('November: $0.42 spent, with no limit set yet.');
    expect(monthSpentLine({ month: '2026-01', spent_usd: 0, cap_usd: null })).toBe('January: nothing spent yet, and no limit set.');
  });

  it('counts the requests with the key and through the plan', () => {
    expect(requestsLine({ api_calls: 12, plan_calls: 3 })).toBe('This month 12 requests went to Claude with the API key. 3 requests went through your Claude plan, at no extra cost.');
    expect(requestsLine({ api_calls: 1, plan_calls: 0 })).toBe('This month 1 request went to Claude with the API key.');
    expect(requestsLine({ api_calls: 0, plan_calls: 0 })).toBe('Nothing was sent with the API key this month.');
  });
});
