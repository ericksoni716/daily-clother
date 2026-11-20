import { describe, expect, it } from 'vitest';
import { byId, itemIdOf, waitingReason } from './added';
import type { ItemSummary, Progress } from './types';

const item = (over: Partial<ItemSummary> = {}): ItemSummary => ({
  id: 'a', name: null, category: null, color: null, color_hex: null, pattern: null, location: 'closet', rating: null,
  status: 'active', cutout_state: 'ready', tag_state: 'done', tag_error: null, thumb_url: '/media/a/p.cut.t.webp',
  has_illustration: false, has_photo: true, last_worn: null, wear_count: 0, wears_since_wash: 0, laundry: 'clean',
  created_at: '2026-11-16T10:00:00Z', updated_at: '2026-11-16T10:00:00Z', ...over,
});

const spendLimitSentence = "This month's spending limit for the API key has been reached.";

describe('what Add shows about the item a photo became', () => {
  it('knows which rows went in as one item: added, or already in the closet, but not a photo of several pieces', () => {
    const row = { status: 'done' as const, itemId: 'a', sourceId: null };
    expect(itemIdOf(row)).toBe('a');
    expect(itemIdOf({ ...row, status: 'duplicate' })).toBe('a');
    expect(itemIdOf({ ...row, sourceId: 's' })).toBeNull();   // its row links to its boxes instead
    for (const status of ['waiting', 'resizing', 'uploading', 'failed', 'missing'] as const) {
      expect(itemIdOf({ ...row, status })).toBeNull();
    }
    expect(itemIdOf({ ...row, itemId: null })).toBeNull();
  });

  it('says once why the items wait, only when it is something you can see to in Settings', () => {
    const waiting = (waiting_for: Progress['waiting_for'], why: string | null) =>
      ({ stage: 'describing', step: 2, of: 3, state: 'waiting', title: '', words: '', about: '', waiting_for, why,
        error: null, can_retry: false, retry: null }) as Progress;
    expect(waitingReason([null, undefined])).toBeNull();
    // Claude out of reach goes on by itself: nothing to see to
    expect(waitingReason([waiting('claude', 'Claude can\'t be reached right now.')])).toBeNull();
    expect(waitingReason([null, waiting('limit', spendLimitSentence)])).toBe(spendLimitSentence);
    // a failure's reason is the item's own, shown on its page, not a reason to wait
    expect(waitingReason([{ ...waiting(null, null), state: 'failed', error: 'Claude could not describe this item.' }])).toBeNull();
  });

  it('finds an item in the closet’s lists, the later list winning', () => {
    const archived = item({ id: 'x', status: 'archived', name: 'Old' });
    const found = byId([[archived, item({ id: 'b' })], null, [item({ id: 'x', name: 'Fresh' })]]);
    expect(found.get('x')?.name).toBe('Fresh');
    expect(found.get('b')?.id).toBe('b');
    expect(found.has('c')).toBe(false);
  });
});
