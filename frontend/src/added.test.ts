import { describe, expect, it } from 'vitest';
import { addedLine, addedState, byId, calledIt, itemIdOf, waitingReason } from './added';
import type { ItemSummary } from './types';

const item = (over: Partial<ItemSummary> = {}): ItemSummary => ({
  id: 'a', name: null, category: null, color: null, color_hex: null, pattern: null, location: 'closet', rating: null,
  status: 'active', cutout_state: 'ready', tag_state: 'done', tag_error: null, thumb_url: '/media/a/p.cut.t.webp',
  has_illustration: false, has_photo: true, last_worn: null, wear_count: 0, wears_since_wash: 0, laundry: 'clean',
  created_at: '2026-11-16T10:00:00Z', updated_at: '2026-11-16T10:00:00Z', ...over,
});

const REMOVING = 'Removing background…';
const spendLimitSentence = "This month's spending limit for the API key has been reached.";

describe('what Add shows about the item a photo became', () => {
  it('follows the item from its background being removed to described, in the item page’s words', () => {
    expect(addedLine(item({ cutout_state: 'pending', tag_state: 'none' }), REMOVING)).toBe(REMOVING);
    expect(addedLine(item({ cutout_state: 'processing', tag_state: 'none' }), 'Waiting for the model')).toBe('Waiting for the model');
    expect(addedLine(item({ tag_state: 'waiting' }), REMOVING)).toBe('Waiting to be described by Claude');
    expect(addedLine(item({ tag_state: 'working' }), REMOVING)).toBe('Claude is describing it…');
    expect(addedLine(item({ tag_state: 'done', name: 'Navy polo', category: 'polo', color: 'navy' }), REMOVING)).toBe('Navy polo');
  });

  it('says when describing or the cutout failed', () => {
    expect(addedState(item({ tag_state: 'failed' }))).toBe('failed');
    expect(addedLine(item({ tag_state: 'failed' }), REMOVING)).toBe("Claude couldn't describe this item");
    expect(addedState(item({ cutout_state: 'failed', tag_state: 'none' }))).toBe('cutout-failed');
    expect(addedLine(item({ cutout_state: 'failed', tag_state: 'none' }), REMOVING)).toBe("The background couldn't be removed");
  });

  it('names an item never to be described by what is known of it (the demo closet’s own photos, older items)', () => {
    expect(addedState(item({ tag_state: 'none' }))).toBe('described');
    expect(addedLine(item({ tag_state: 'none', name: 'Old jacket' }), REMOVING)).toBe('Old jacket');
    expect(addedLine(item({ tag_state: 'none' }), REMOVING)).toBe('New item');
  });

  it('calls it by its name, else its category and colour', () => {
    expect(calledIt({ name: 'Navy polo', category: 'polo', color: 'navy' })).toBe('Navy polo');
    expect(calledIt({ name: null, category: 'polo', color: 'navy' })).toBe('Polo · Navy');
    expect(calledIt({ name: null, category: 'jeans', color: null })).toBe('Jeans');
    expect(calledIt({ name: '', category: null, color: null })).toBe('New item');
  });

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

  it('says once why the items wait, only when Closet knows', () => {
    expect(waitingReason([item({ tag_state: 'waiting' }), null, undefined])).toBeNull();   // just waiting its turn
    expect(waitingReason([item(), item({ tag_state: 'waiting', tag_error: spendLimitSentence })])).toBe(spendLimitSentence);
    // a failure's reason is the item's own, shown on its page, not a reason to wait
    expect(waitingReason([item({ tag_state: 'failed', tag_error: 'Claude could not describe this item.' })])).toBeNull();
  });

  it('finds an item in the closet’s lists, the later list winning', () => {
    const archived = item({ id: 'x', status: 'archived', name: 'Old' });
    const found = byId([[archived, item({ id: 'b' })], null, [item({ id: 'x', name: 'Fresh' })]]);
    expect(found.get('x')?.name).toBe('Fresh');
    expect(found.get('b')?.id).toBe('b');
    expect(found.has('c')).toBe(false);
  });
});
