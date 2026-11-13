import { describe, expect, it } from 'vitest';
import { backoff, countEntries, isTransient, UploadQueue, type QueueDeps, type SavedEntry, type UploadStatus } from './uploadQueue';

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
  it('uploads at most two files at a time, starting them in order', async () => {
    const started: string[] = [];
    let active = 0;
    let maxActive = 0;
    const { q } = makeQueue(async (_b, filename) => {
      started.push(filename);
      active++;
      maxActive = Math.max(maxActive, active);
      await new Promise((r) => setTimeout(r, 2));
      active--;
      return { id: `item-${filename}` };
    });
    q.add(['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg', 'e.jpg'].map((name) => ({ name })));
    await q.idle();
    expect(started).toEqual(['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg', 'e.jpg']);
    expect(maxActive).toBe(2);
    expect(q.snapshot.map((e) => e.status)).toEqual(['done', 'done', 'done', 'done', 'done']);
    expect(q.snapshot.map((e) => e.itemId)).toEqual(['item-a.jpg', 'item-b.jpg', 'item-c.jpg', 'item-d.jpg', 'item-e.jpg']);
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
    const [id] = q.add([{ name: 'a.jpg' }]).ids;
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
  it('marks a photo the server already had as already in the closet', async () => {
    const { q } = makeQueue(async (_b, filename) => ({ id: 'old-item', duplicate: filename === 'b.jpg' }));
    q.add([{ name: 'a.jpg' }, { name: 'b.jpg' }]);
    await q.idle();
    expect(q.snapshot.map((e) => e.status)).toEqual(['done', 'duplicate']);
    expect(q.snapshot[1].itemId).toBe('old-item');
    expect(countEntries(q.snapshot)).toMatchObject({ done: 1, duplicate: 1, failed: 0, waiting: 0, uploading: 0 });
  });

  it('sends the hash of the file as chosen', async () => {
    const hashes: (string | null)[] = [];
    const { q } = makeQueue(async (_b, _f, _k, sha) => {
      hashes.push(sha);
      return { id: 'i' };
    }, { hash: async (f) => (f.name === 'a' ? 'h-a' : Promise.reject(new Error('cannot read'))) });
    q.add([{ name: 'a' }, { name: 'b' }]);
    await q.idle();
    expect(hashes.sort()).toEqual(['h-a', null].sort());
  });

  it('leaves out a file already waiting, and sends a finished one again with its first key', async () => {
    const keys: string[] = [];
    const { q } = makeQueue(async (_b, filename, key) => {
      keys.push(`${filename}:${key}`);
      return { id: `item-${filename}` };
    });
    expect(q.add([{ name: 'a' }, { name: 'a' }]).skipped).toBe(1);
    await q.idle();
    const again = q.add([{ name: 'a' }, { name: 'b' }]);
    expect(again.skipped).toBe(0);
    await q.idle();
    expect(q.snapshot.map((e) => [e.name, e.status])).toEqual([['a', 'done'], ['b', 'done']]);
    expect(keys).toEqual(['a:key-1', 'a:key-1', 'b:key-2']);
  });

  it('pause stops new uploads starting; carrying on finishes the rest', async () => {
    const started: string[] = [];
    const { q } = makeQueue(async (_b, filename) => {
      started.push(filename);
      await new Promise((r) => setTimeout(r, 2));
      return { id: filename };
    });
    q.pause();
    q.add([{ name: 'a' }, { name: 'b' }, { name: 'c' }]);
    await q.idle();
    expect(started).toEqual([]);
    expect(q.isPaused).toBe(true);
    expect(countEntries(q.snapshot).waiting).toBe(3);
    q.resume();
    // pausing again while two are going lets those two finish and holds the third
    q.pause();
    await q.idle();
    expect(started).toEqual(['a', 'b']);
    expect(q.snapshot.map((e) => e.status)).toEqual(['done', 'done', 'waiting']);
    q.resume();
    await q.idle();
    expect(q.snapshot.map((e) => e.status)).toEqual(['done', 'done', 'done']);
  });

  it('cancel drops what has not started and lets the uploads already going finish', async () => {
    const { q } = makeQueue(async (_b, filename) => {
      await new Promise((r) => setTimeout(r, 2));
      return { id: filename };
    });
    q.add([{ name: 'a' }, { name: 'b' }, { name: 'c' }, { name: 'd' }]);
    q.cancel();
    await q.idle();
    expect(q.snapshot.map((e) => [e.name, e.status])).toEqual([['a', 'done'], ['b', 'done']]);
  });

  it('retries every failed upload at once', async () => {
    let fail = true;
    const { q } = makeQueue(async (_b, filename) => {
      if (fail) throw err(400, 'Nope.');
      return { id: filename };
    });
    q.add([{ name: 'a' }, { name: 'b' }]);
    await q.idle();
    expect(countEntries(q.snapshot).failed).toBe(2);
    fail = false;
    q.retryFailed();
    await q.idle();
    expect(q.snapshot.map((e) => e.status)).toEqual(['done', 'done']);
  });

  it('while offline nothing starts; back online the queue carries on', async () => {
    let calls = 0;
    const { q } = makeQueue(async () => {
      calls++;
      return { id: 'i' };
    });
    q.setOnline(false);
    q.add([{ name: 'a' }]);
    await q.idle();
    expect(calls).toBe(0);
    expect(q.snapshot[0].status).toBe('waiting');
    q.setOnline(true);
    await q.idle();
    expect(calls).toBe(1);
    expect(q.snapshot[0].status).toBe('done');
  });

  it('an upload that fails because the page went offline goes back to waiting', async () => {
    const box: { q?: UploadQueue<F> } = {};
    let reachable = false;
    const { q, sleeps } = makeQueue(async () => {
      if (!reachable) {
        box.q!.setOnline(false);
        throw err(0, "Can't reach Closet.");
      }
      return { id: 'i' };
    });
    box.q = q;
    q.add([{ name: 'a' }]);
    await q.idle();
    expect(q.snapshot[0]).toMatchObject({ status: 'waiting', error: null });
    expect(sleeps).toEqual([]);
    reachable = true;
    q.setOnline(true);
    await q.idle();
    expect(q.snapshot[0]).toMatchObject({ status: 'done', itemId: 'i' });
  });
});

describe('carrying on after the tab was closed', () => {
  function memoryStore(initial: SavedEntry[] | null = null) {
    const box = { saved: initial };
    return { box, store: { load: () => box.saved, save: (e: SavedEntry[]) => void (box.saved = e) } };
  }

  it('saves the list, then offers what was left once the files are chosen again', async () => {
    const { box, store } = memoryStore();
    const sent: string[] = [];
    let block = true;
    const first = makeQueue(async (_b, filename, key) => {
      if (block && filename === 'c') await new Promise(() => undefined); // the tab closes during this upload
      sent.push(`${filename}:${key}`);
      return { id: `item-${filename}` };
    }, { store, concurrency: 1 });
    first.q.add([{ name: 'a' }, { name: 'b' }, { name: 'c' }, { name: 'd' }]);
    await new Promise((r) => setTimeout(r, 5));
    expect(box.saved!.map((e) => e.status)).toEqual(['done', 'done', 'uploading', 'waiting']);
    const keyOfC = box.saved![2].clientKey;

    // a new page: the list comes back, but the files are gone
    block = false;
    const second = makeQueue(async (_b, filename, key) => {
      sent.push(`${filename}:${key}`);
      return { id: `item-${filename}` };
    }, { store, newKey: () => 'fresh-key' });
    expect(second.q.snapshot.map((e) => e.status)).toEqual(['done', 'done', 'missing', 'missing']);
    expect(countEntries(second.q.snapshot).missing).toBe(2);

    // choosing the same four again: every row keeps its first key, so the server can tell
    // the two that went in already and none of them is added twice
    const keysBefore = box.saved!.map((e) => e.clientKey);
    second.q.add([{ name: 'a' }, { name: 'b' }, { name: 'c' }, { name: 'd' }]);
    await second.q.idle();
    expect(second.q.snapshot.map((e) => e.status)).toEqual(['done', 'done', 'done', 'done']);
    expect(second.q.snapshot.map((e) => e.clientKey)).toEqual(keysBefore);
    expect(sent).toContain(`c:${keyOfC}`);
    expect(sent.some((s) => s.endsWith('fresh-key'))).toBe(false);
  });

  it('forgetting what was left clears it, and an empty list is not kept', async () => {
    const { box, store } = memoryStore([
      { name: 'a', fileKey: 'a', clientKey: 'k1', status: 'uploading', error: null, itemId: null },
    ]);
    const { q } = makeQueue(async () => ({ id: 'i' }), { store });
    expect(q.snapshot[0].status).toBe('missing');
    q.retry(q.snapshot[0].id); // no file to retry with
    expect(q.snapshot[0].status).toBe('missing');
    q.cancel();
    expect(q.snapshot).toEqual([]);
    expect(box.saved).toEqual([]);
  });

  it('a broken saved list is ignored', () => {
    const { q } = makeQueue(async () => ({ id: 'i' }), { store: { load: () => { throw new Error('bad json'); }, save: () => undefined } });
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
