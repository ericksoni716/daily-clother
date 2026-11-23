import { describe, expect, it } from 'vitest';
import { goneLine, keptToast, keptWhen, keptWith, type KeptOutfit } from './kept';

function kept(id: string, base: string, gone: string[] = []): KeptOutfit {
  return { id, name: null, pieces: { base, mid: null, outer: null, bottom: 'j', shoes: 's', accessories: [] }, gone,
    created_at: '2026-11-23T12:00:00Z', updated_at: '' };
}

describe('outfits you keep', () => {
  it('finds a kept outfit by its pieces, in any order', () => {
    expect(keptWith([kept('a', 't1'), kept('b', 't2')], ['s', 'j', 't2'])?.id).toBe('b');
    expect(keptWith([kept('a', 't1')], ['t1', 'j'])).toBeNull();
    expect(keptWith(null, ['t1'])).toBeNull();
  });

  it('says when it was kept already, when it was kept, and a piece gone', () => {
    expect(keptToast({ already: false })).toBe('Kept. You will find it under Worn.');
    expect(keptToast({ already: true })).toBe('You keep this outfit already. It is under Worn.');
    expect(keptWhen(kept('a', 't'), '2026-11-23')).toBe('Kept today');
    expect(keptWhen({ created_at: 'nonsense' })).toBe('Kept');
    expect(goneLine(kept('a', 't'))).toBeNull();
    expect(goneLine(kept('a', 't', ['t']))).toBe('One piece is no longer in your closet. Wearing this fills its place.');
    expect(goneLine(kept('a', 't', ['t', 's']))).toBe('2 pieces are no longer in your closet. Wearing this fills their places.');
  });
});
