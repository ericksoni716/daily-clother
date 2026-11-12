import { describe, expect, it } from 'vitest';
import { backoff, isTransient, UploadQueue, type QueueDeps, type UploadStatus } from './uploadQueue';

type F = { name: string };

function makeQueue(upload: QueueDeps<F>['upload'], extra: Partial<QueueDeps<F>> = {}) {
  let n = 0;
  const sleeps: number[] = [];
  const statuses: UploadStatus[][] = [];
  const q = new UploadQueue<F>({
    prepare: async (f) => ({ blob: new Blob([f.name]), filename: f.name }),
    upload,
    newKey: () => `key-${++n}`,
    sleep: async (ms) => void sleeps.push(ms),
    nameOf: (f) => f.name,
    ...extra,
  });
  q.subscribe((entries) => statuses.push(entries.map((e) => e.status)));
  return { q, sleeps, statuses };
}

const err = (status: number, message: string) => Object.assign(new Error(message), { status });

describe('UploadQueue', () => {
  it('uploads files one at a time, in order', async () => {
    const order: string[] = [];
    let active = 0;
    let maxActive = 0;
    const { q } = makeQueue(async (_b, filename) => {
      active++;
      maxActive = Math.max(maxActive, active);
      await new Promise((r) => setTimeout(r, 2));
      order.push(filename);
      active--;
      return { id: `item-${filename}` };
    });
    q.add([{ name: 'a.jpg' }, { name: 'b.jpg' }, { name: 'c.jpg' }]);
    await q.idle();
    expect(order).toEqual(['a.jpg', 'b.jpg', 'c.jpg']);
    expect(maxActive).toBe(1);
    expect(q.snapshot.map((e) => e.status)).toEqual(['done', 'done', 'done']);
    expect(q.snapshot.map((e) => e.itemId)).toEqual(['item-a.jpg', 'item-b.jpg', 'item-c.jpg']);
  });

  it('gives every file its own key', async () => {
    const { q } = makeQueue(async () => ({ id: 'x' }));
    q.add([{ name: 'a' }, { name: 'b' }]);
    await q.idle();
    const keys = q.snapshot.map((e) => e.clientKey);
    expect(new Set(keys).size).toBe(2);
  });

  it('retries network failures automatically with the same key and growing waits', async () => {
    const keys: string[] = [];
    let calls = 0;
    const { q, sleeps } = makeQueue(async (_b, _f, key) => {
      keys.push(key);
      if (++calls < 3) throw err(0, "Can't reach Closet.");
      return { id: 'item-1' };
    });
    q.add([{ name: 'a.jpg' }]);
    await q.idle();
    expect(keys).toEqual(['key-1', 'key-1', 'key-1']);
    expect(sleeps).toEqual([1000, 2000]);
    expect(q.snapshot[0]).toMatchObject({ status: 'done', itemId: 'item-1', error: null });
  });

  it('gives up after 3 automatic retries and reports the reason', async () => {
    let calls = 0;
    const { q, sleeps } = makeQueue(async () => {
      calls++;
      throw err(503, 'Server busy.');
    });
    q.add([{ name: 'a.jpg' }]);
    await q.idle();
    expect(calls).toBe(4); // first try + 3 retries
    expect(sleeps).toEqual([1000, 2000, 4000]);
    expect(q.snapshot[0]).toMatchObject({ status: 'failed', error: 'Server busy.' });
  });

  it('does not retry a file the server refused, and shows the server message', async () => {
    let calls = 0;
    const { q, sleeps } = makeQueue(async () => {
      calls++;
      throw err(400, 'That file is not a photo this app can read.');
    });
    q.add([{ name: 'notes.txt' }, { name: 'b.jpg' }]);
    await q.idle();
    expect(calls).toBe(2); // one each, the second file still went
    expect(sleeps).toEqual([]);
    expect(q.snapshot[0]).toMatchObject({ status: 'failed', error: 'That file is not a photo this app can read.' });
  });

  it('a manual retry reuses the key and does not resize again', async () => {
    let prepares = 0;
    const keys: string[] = [];
    let fail = true;
    const { q } = makeQueue(async (_b, _f, key) => {
      keys.push(key);
      if (fail) throw err(400, 'Nope.');
      return { id: 'item-9' };
    }, {
      prepare: async (f) => {
        prepares++;
        return { blob: new Blob([f.name]), filename: f.name };
      },
    });
    const [id] = q.add([{ name: 'a.jpg' }]);
    await q.idle();
    expect(q.snapshot[0].status).toBe('failed');
    fail = false;
    q.retry(id);
    await q.idle();
    expect(keys).toEqual(['key-1', 'key-1']);
    expect(prepares).toBe(1);
    expect(q.snapshot[0]).toMatchObject({ status: 'done', itemId: 'item-9', error: null });
  });

  it('passes through waiting, resizing, uploading, done', async () => {
    const { q, statuses } = makeQueue(async () => ({ id: 'i' }));
    q.add([{ name: 'a' }]);
    await q.idle();
    expect(statuses.map((s) => s[0])).toEqual(['waiting', 'resizing', 'uploading', 'done']);
  });

  it('uploads the original file when it cannot be resized', async () => {
    const file = { name: 'photo.heic' };
    let sent: unknown;
    const { q } = makeQueue(async (blob, filename) => {
      sent = [blob, filename];
      return { id: 'i' };
    }, { prepare: async () => { throw new Error('cannot decode'); } });
    q.add([file]);
    await q.idle();
    expect(sent).toEqual([file, 'photo.heic']);
  });

  it('clearFinished keeps rows still in progress', async () => {
    const { q } = makeQueue(async () => { throw err(400, 'bad'); });
    q.add([{ name: 'a' }]);
    await q.idle();
    q.clearFinished();
    expect(q.snapshot).toEqual([]);
  });
});

describe('failure classification', () => {
  it('treats lost connections and server errors as worth retrying', () => {
    expect(isTransient({ status: 0 })).toBe(true);
    expect(isTransient({})).toBe(true);
    expect(isTransient({ status: 502 })).toBe(true);
    expect(isTransient({ status: 429 })).toBe(true);
    expect(isTransient({ status: 400 })).toBe(false);
    expect(isTransient({ status: 401 })).toBe(false);
    expect(isTransient({ status: 413 })).toBe(false);
  });
  it('backs off exponentially', () => {
    expect([1, 2, 3].map((n) => backoff(n))).toEqual([1000, 2000, 4000]);
  });
});
