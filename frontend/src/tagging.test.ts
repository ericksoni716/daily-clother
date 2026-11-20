import { describe, expect, it } from 'vitest';
import { describedBy } from './tagging';

describe('tagging wording', () => {
  it('says who described it', () => {
    expect(describedBy('plan', null)).toBe('Described with your Claude plan.');
    expect(describedBy('api', null)).toBe('Described with your API key.');
    expect(describedBy('plan', '2026-11-12T10:00:00Z')).toMatch(/^Described with your Claude plan on .*2026\.$/);
    expect(describedBy('demo', '2026-11-12T10:00:00Z')).toBe('');
    expect(describedBy(null, null)).toBe('');
  });
});
