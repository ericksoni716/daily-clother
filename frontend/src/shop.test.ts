import { describe, expect, it } from 'vitest';
import { dropWords, priceWords, rangeWords, typedPrice, webLink } from './shop';

describe('shopping words', () => {
  it('shows prices in their currency', () => {
    expect(priceWords(120, 'USD')).toBe('$120.00');
    expect(priceWords(89.5, 'EUR')).toBe('€89.50');
    expect(priceWords(null, 'USD')).toBe('Price not shown');
    expect(priceWords(10, 'XX')).toBe('10.00 XX');
  });

  it('says how much a price dropped', () => {
    expect(dropWords({ from: 120, to: 96, currency: 'USD', percent: 20 })).toBe('Was $120.00, now $96.00 (20% less)');
  });

  it('puts a price range in words', () => {
    expect(rangeWords({ price_min: null, price_max: null, price_currency: null })).toBe('');
    expect(rangeWords({ price_min: 50, price_max: 150, price_currency: 'USD' })).toBe('$50.00 to $150.00');
    expect(rangeWords({ price_min: null, price_max: 90, price_currency: 'GBP' })).toBe('Up to £90.00');
    expect(rangeWords({ price_min: 40, price_max: null, price_currency: undefined })).toBe('From $40.00');
  });

  it('opens only web addresses', () => {
    expect(webLink('https://shop.example/coat')).toBe('https://shop.example/coat');
    expect(webLink('http://shop.example/')).toBe('http://shop.example/');
    expect(webLink('javascript:alert(1)')).toBeNull();
    expect(webLink('data:image/png;base64,AAAA')).toBeNull();
    expect(webLink('not a link')).toBeNull();
    expect(webLink(null)).toBeNull();
  });

  it('reads a typed price', () => {
    expect(typedPrice('')).toBeNull();
    expect(typedPrice(' 120.50 ')).toBe(120.5);
    expect(typedPrice('$1,200')).toBe(1200);
    expect(typedPrice('-5')).toBeUndefined();
    expect(typedPrice('cheap')).toBeUndefined();
  });
});
