import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type DragEvent } from 'react';
import { api, type ApiError } from '../api';
import { byId, itemIdOf, waitingReason } from '../added';
import { AddedPicture, AddedRow } from '../components/AddedItem';
import { CameraIcon, CheckIcon, CloseIcon, CloudOffIcon, ImagesIcon, WarnIcon } from '../components/Icons';
import { sendShoePhotos } from '../components/ShoePhotos';
import { Card, Notice, PageHeader } from '../components/ui';
import {
  applySort, batches, choicesFor, choose, shoes, SHOE_PHOTOS, SORT_EDGE, SORT_MAX, tooManyForAShoe, trayLine, valueOf,
  type Kind, type TrayPhoto,
} from '../addsort';
import { filesFromDrop, preparePhoto, splitPhotos } from '../resize';
import { Link, navigate, useMediaQuery } from '../router';
import { sourceLine } from '../several';
import { aboutUsd, importLine } from '../spend';
import { useCloset } from '../store';
import { tagNotice } from '../tagging';
import { photoRoom, shoeAddedLine } from '../shoe';
import { countEntries, type QueueEntry, type UploadStatus } from '../uploadQueue';
import { addFiles, cancelImport, clearFinished, previewOf, sha256, uploads } from '../uploads';
import type { Item, ItemSummary, SourcePhoto } from '../types';
import '../components/Shoe.css';
import './Several.css';

const OPEN_POLL_MS = 3000;
const newKey = () => (typeof crypto.randomUUID === 'function' ? crypto.randomUUID()
  : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`);
/** The same file chosen twice. */
const sameFile = (a: File, b: File) => a.name === b.name && a.size === b.size && a.lastModified === b.lastModified;
type Sorting = { at: 'idle' } | { at: 'sorting'; done: number; total: number } | { at: 'sorted'; message: string | null };
/** A shoe sent from the tray: the item it became, or why it could not be. */
type ShoeSent = { item: Item; added: number; total: number; duplicate: boolean; error?: string };

const STATUS_TEXT: Record<UploadStatus, string> = {
  waiting: 'Waiting',
  resizing: 'Resizing',
  uploading: 'Uploading',
  done: 'Added',
  duplicate: 'Already in your closet',
  failed: 'Failed',
  missing: 'Not added yet',
};

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** What happened to the files just chosen or dropped, in plain words. */
function describeAdded(queued: number, alreadyListed: number, skipped: File[]): string {
  const parts: string[] = [];
  if (queued) parts.push(`${plural(queued, 'photo')} added to the import.`);
  if (alreadyListed) parts.push(`${plural(alreadyListed, 'photo was', 'photos were')} already waiting to go in, so ${alreadyListed === 1 ? 'it was' : 'they were'} left out.`);
  if (skipped.length) {
    const names = skipped.slice(0, 3).map((f) => f.name).join(', ');
    const more = skipped.length > 3 ? ` and ${skipped.length - 3} more` : '';
    parts.push(`Skipped ${plural(skipped.length, 'file')} that ${skipped.length === 1 ? 'is not a photo' : 'are not photos'}: ${names}${more}.`);
  }
  return parts.join(' ') || 'There were no photos in what you chose.';
}

/** "3 waiting · 2 uploading · 10 added …", leaving out what is zero. */
function summaryText(c: ReturnType<typeof countEntries>): string {
  const parts: string[] = [];
  if (c.waiting) parts.push(`${c.waiting} waiting`);
  if (c.uploading) parts.push(`${c.uploading} uploading`);
  if (c.done) parts.push(`${c.done} added`);
  if (c.duplicate) parts.push(`${c.duplicate} already in your closet`);
  if (c.failed) parts.push(`${c.failed} didn't work`);
  if (c.missing) parts.push(`${c.missing} not added yet`);
  return parts.join(' · ');
}

function usePaused(): boolean {
  return useSyncExternalStore((l) => uploads.subscribe(l), () => uploads.isPaused);
}

function useQueue(): QueueEntry[] {
  return useSyncExternalStore((l) => uploads.subscribe(l), () => uploads.snapshot);
}

/** Keeps the phone screen on while a long batch uploads, where the browser allows it. */
function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !('wakeLock' in navigator)) return;
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;
    const request = () => {
      navigator.wakeLock.request('screen').then((l) => {
        if (cancelled) void l.release();
        else lock = l;
      }).catch(() => undefined);
    };
    request();
    const onVisible = () => { if (document.visibilityState === 'visible') request(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisible);
      void lock?.release().catch(() => undefined);
    };
  }, [active]);
}

export function AddScreen() {
  const { offline, profile, items, loadItems } = useCloset();
  const queue = useQueue();
  const paused = usePaused();
  const desktop = useMediaQuery('(min-width: 1000px) and (pointer: fine)');
  const phone = !desktop;
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  // React does not know the folder-picking attribute, so it is set by hand
  useEffect(() => {
    folder.current?.setAttribute('webkitdirectory', '');
  }, [offline, desktop]);

  // what the photos could cost to describe with the API key, shown only when the owner allows the key
  const [perPhotoUsd, setPerPhotoUsd] = useState<number | null>(null);
  const [perFindUsd, setPerFindUsd] = useState<number | null>(null);
  useEffect(() => {
    if (offline || profile === 'demo') return;
    let current = true;
    api.tagSpend().then((s) => {
      if (!current) return;
      setPerPhotoUsd(s.allowed ? s.per_photo_usd : null);
      setPerFindUsd(s.allowed ? s.per_find_usd : null);
    }, () => undefined);
    return () => {
      current = false;
    };
  }, [offline, profile]);

  // the tray: photos chosen or taken, sorted by Claude into pieces, photos of several and shoes, checked by the owner
  const [tray, setTray] = useState<TrayPhoto[]>([]);
  const trayRef = useRef<TrayPhoto[]>([]);
  const putTray = (next: TrayPhoto[]) => {
    trayRef.current = next;
    setTray(next);
  };
  const [sorting, setSorting] = useState<Sorting>({ at: 'idle' });
  const sortRun = useRef(0);
  const [sending, setSending] = useState(false);
  const [shoesSent, setShoesSent] = useState<ShoeSent[]>([]);
  const { upsert } = useCloset();
  useEffect(() => () => trayRef.current.forEach((p) => URL.revokeObjectURL(p.url)), []);

  /** Ask Claude what every photo in the tray shows, ten at a time; the owner's own choices are kept. */
  async function sortTray() {
    const run = ++sortRun.current;
    const snapshot = trayRef.current;
    const groups = batches(snapshot);
    const answers: { kind: Kind; shoe: number }[][] = [];
    let message: string | null = null;
    setSorting({ at: 'sorting', done: 0, total: snapshot.length });
    for (const group of groups) {
      try {
        const small = await Promise.all(group.map((p) => preparePhoto(p.file, SORT_EDGE)));
        const answer = await api.sortAdd(small);
        if (!answer.sorted) {
          message = answer.message;
          break;
        }
        answers.push(answer.photos);
      } catch (e) {
        if ((e as ApiError).status === 400) {
          // a file Closet cannot read as a photo: added as one piece, so the import says why it did not go in
          answers.push(group.map(() => ({ kind: 'piece' as Kind, shoe: 0 })));
          continue;
        }
        message = `Closet couldn't sort these (${(e as Error).message}): sort them yourself.`;
        break;
      }
      if (run !== sortRun.current) return;
      setSorting({ at: 'sorting', done: answers.length * group.length, total: snapshot.length });
    }
    if (run !== sortRun.current) return;
    const sorted = new Map(applySort(snapshot, answers).map((p) => [p.key, p]));
    // laid onto the tray as it is now: a photo removed meanwhile stays gone, one chosen by hand keeps the choice
    const next = trayRef.current.map((p) => (p.fixed ? p : sorted.get(p.key) ?? p));
    putTray(next);
    setSorting({ at: 'sorted', message });
    // the everyday case, one piece per photo, goes straight in; anything else waits for the owner to check it
    if (!message && next.length && next.every((p) => p.kind === 'piece' && !p.fixed)) void addTray();
  }

  function remove(key: string) {
    const gone = trayRef.current.find((p) => p.key === key);
    if (gone) URL.revokeObjectURL(gone.url);
    putTray(trayRef.current.filter((p) => p.key !== key));
  }

  function clearTray() {
    sortRun.current++;
    trayRef.current.forEach((p) => URL.revokeObjectURL(p.url));
    putTray([]);
    setSorting({ at: 'idle' });
  }

  /** A shoe and all its photos: the first makes the shoe, the others are added to it (as "A shoe" did). */
  async function sendShoe(photos: TrayPhoto[]): Promise<ShoeSent> {
    const [first, ...rest] = photos;
    const [prepared, hash] = await Promise.all([preparePhoto(first.file), sha256(first.file).catch(() => null)]);
    const item: Item & { duplicate?: boolean } = await api.upload(prepared.blob, prepared.filename, first.key, hash, undefined, true);
    upsert(item);
    if (item.duplicate) return { item, added: 0, total: photos.length, duplicate: true };
    let added = 1;
    try {
      await sendShoePhotos(item.id, rest.map((p) => p.file), photoRoom(item), (got) => {
        added += 1;
        upsert(got);
      });
    } catch (e) {
      return { item, added, total: photos.length, duplicate: false, error: (e as Error).message };
    }
    return { item, added, total: photos.length, duplicate: false };
  }

  /** "Add these": each photo goes the way it always has. */
  async function addTray() {
    const chosen = trayRef.current;
    if (!chosen.length) return;
    sortRun.current++;
    setSending(true);
    const pieces = chosen.filter((p) => p.kind === 'piece').map((p) => p.file);
    const several = chosen.filter((p) => p.kind === 'pieces').map((p) => p.file);
    const said: string[] = [];
    let queued = 0, alreadyListed = 0;
    for (const [files, asSeveral] of [[pieces, false], [several, true]] as const) {
      if (!files.length) continue;
      const { ids, skipped } = addFiles(files, asSeveral);
      queued += files.length - skipped;
      alreadyListed += skipped;
      if (asSeveral && files.length === 1 && ids.length === 1) setFollow(ids[0]);
    }
    if (queued || alreadyListed) said.push(describeAdded(queued, alreadyListed, []));
    const left = tooManyForAShoe(chosen);
    if (left) said.push(`A shoe takes up to ${SHOE_PHOTOS} photos, so ${left === 1 ? 'one photo was' : `${left} photos were`} left out.`);
    const sent: ShoeSent[] = [];
    for (const shoe of shoes(chosen)) {
      try {
        sent.push(await sendShoe(shoe.slice(0, SHOE_PHOTOS)));
      } catch (e) {
        said.push(`A shoe could not be added: ${(e as Error).message}`);
      }
    }
    setShoesSent((before) => [...sent, ...before]);
    setNote(said.join(' ') || null);
    clearTray();
    setSending(false);
  }

  // one photo of several pieces sent on its own: its pieces are checked as soon as it is in
  const [follow, setFollow] = useState<string | null>(null);
  useEffect(() => {
    if (!follow) return;
    const entry = queue.find((e) => e.id === follow);
    if (entry && ['waiting', 'resizing', 'uploading'].includes(entry.status)) return;
    setFollow(null);
    if (entry?.sourceId && (entry.status === 'done' || entry.status === 'duplicate')) {
      navigate(`/add/several/${encodeURIComponent(entry.sourceId)}`);
    }
  }, [follow, queue]);

  // the photos of several pieces whose pieces are not added yet
  const [open, setOpen] = useState<SourcePhoto[]>([]);
  const sentSeveral = queue.filter((e) => e.sourceId).length;
  const looking = open.some((s) => s.state === 'finding' && !s.note);
  useEffect(() => {
    if (offline) return;
    let current = true;
    const look = () => api.sources().then((list) => current && setOpen(list), () => undefined);
    void look();
    const t = looking ? window.setInterval(look, OPEN_POLL_MS) : undefined;
    return () => {
      current = false;
      if (t) window.clearInterval(t);
    };
  }, [offline, profile, sentSeveral, looking]);

  // What each photo became: the closet's own list already follows new items until they are described, so the rows
  // read it and ask for nothing more. A photo already in the closet can be an archived item's: that list is asked
  // for once, when such a row is not in the closet's list.
  const known = useMemo(() => byId([items.archived, items.active]), [items.archived, items.active]);
  const itemOf = (e: QueueEntry): ItemSummary | null => {
    const id = itemIdOf(e);
    return id ? known.get(id) ?? null : null;
  };
  const needArchived = !offline && items.active !== null && items.archived === null
    && queue.some((e) => e.status === 'duplicate' && itemIdOf(e) && !known.has(e.itemId as string));
  useEffect(() => {
    if (needArchived) void loadItems('archived');
  }, [needArchived, loadItems]);
  const waitsBecause = waitingReason(queue.map(itemOf));

  const counts = countEntries(queue);
  const pending = counts.waiting + counts.uploading;
  const longBatch = phone && pending > 5;
  useWakeLock(pending > 0 && longBatch && !paused);

  function take(list: FileList | File[] | null) {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    const { photos, skipped } = splitPhotos(files);
    if (trayRef.current.length + photos.length > SORT_MAX) {
      // a big import (a folder) goes in one piece per photo, as before, without waiting to be sorted
      const { skipped: alreadyListed } = photos.length ? addFiles(photos, false) : { skipped: 0 };
      setNote(`${describeAdded(photos.length - alreadyListed, alreadyListed, skipped)} That is more than Closet sorts at once, so each photo goes in as one piece; add photos of several pieces or of shoes a few at a time.`);
      return;
    }
    const now = trayRef.current;
    const fresh = photos.filter((f, i) => !now.some((p) => sameFile(p.file, f)) && photos.findIndex((g) => sameFile(g, f)) === i);
    const parts: string[] = [];
    if (photos.length > fresh.length) parts.push(`${plural(photos.length - fresh.length, 'photo was', 'photos were')} already in the list.`);
    if (skipped.length) parts.push(describeAdded(0, 0, skipped));
    setNote(parts.join(' ') || null);
    if (!fresh.length) return;
    putTray([...now, ...fresh.map((file) => ({ key: newKey(), file, url: URL.createObjectURL(file), kind: 'piece' as Kind, shoe: 0, fixed: false }))]);
    void sortTray();
  }

  async function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (offline) return;
    take(await filesFromDrop(e.dataTransfer));
  }

  const pickers = (
    <>
      <input ref={camera} className="visually-hidden" type="file" accept="image/*" capture="environment" tabIndex={-1}
        aria-hidden="true" data-testid="camera-input" onChange={(e) => { take(e.target.files); e.target.value = ''; }} />
      <input ref={library} className="visually-hidden" type="file" accept="image/*" multiple tabIndex={-1}
        aria-hidden="true" data-testid="library-input" onChange={(e) => { take(e.target.files); e.target.value = ''; }} />
      <input ref={folder} className="visually-hidden" type="file" multiple tabIndex={-1}
        aria-hidden="true" data-testid="folder-input" onChange={(e) => { take(e.target.files); e.target.value = ''; }} />
    </>
  );

  return (
    <section className="add" aria-labelledby="add-title">
      <PageHeader title="Add clothes" titleId="add-title" />
      {profile === 'demo' && <Notice as="p">You're in the demo closet, so new photos are added to the demo. Use "Back to my closet" above to add to your own.</Notice>}

      {offline ? (
        <div className="notice notice-warn" data-testid="import-offline">
          <CloudOffIcon />
          <div>
            <p>Importing photos is unavailable right now: Closet on your computer can't be reached. Check that the computer is on and Closet is running; this page will work again as soon as it is.</p>
            {pending > 0 && <p>The {plural(pending, 'photo')} still to go will carry on by themselves when it is back.</p>}
          </div>
        </div>
      ) : (
        <>
          <p className="muted add-intro" data-testid="add-intro">Add any photos: one piece of clothing per photo, several pieces laid out together on the bed or the floor, or a shoe from a few sides (all its photos at once). Closet sorts them; one piece per photo goes straight in, anything else waits for you to check it. Photos already in your closet are recognised and not added twice.</p>
          <p className="muted small" data-testid="shoe-tips">For a shoe: one shoe on its own, not the pair, up to {SHOE_PHOTOS} photos (its side, the other side, from above, the front and the back), against a plain floor or wall in even light.</p>
          {profile !== 'demo' && perFindUsd !== null && (
            <p className="muted small" data-testid="several-cost">With the API key, if your plan can't be used: sorting is a fraction of a cent, finding the pieces in a photo of several {aboutUsd(perFindUsd)} at most, and describing each piece{perPhotoUsd !== null ? ` ${aboutUsd(perPhotoUsd)} at most` : ' a little'}.</p>
          )}

          {counts.missing > 0 && (
            <div className="notice notice-warn resume" data-testid="resume">
              <WarnIcon />
              <div>
                <p>Your last import stopped before it finished: {plural(counts.missing, 'photo was', 'photos were')} not added yet.
                  To carry on, choose the same photos{desktop ? ' or folder' : ''} again. Nothing that already went in is added twice.</p>
                <div className="row">
                  <button className="btn btn-primary btn-small" onClick={() => library.current?.click()}>Choose photos</button>
                  {desktop && <button className="btn btn-small" onClick={() => folder.current?.click()}>Choose a folder</button>}
                  <button className="btn btn-ghost btn-small" onClick={cancelImport}>Forget them</button>
                </div>
              </div>
            </div>
          )}

          {!desktop && (
            <div className="add-buttons">
              <button className="big-button" onClick={() => camera.current?.click()}>
                <CameraIcon /><span>Take photo</span>
              </button>
              <button className="big-button" onClick={() => library.current?.click()}>
                <ImagesIcon /><span>Choose from library</span>
              </button>
            </div>
          )}

          {desktop && (
            <div className={`dropzone${dragging ? ' is-over' : ''}`}
              onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
              onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; }}
              onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
              onDrop={onDrop}
              data-testid="dropzone">
              <ImagesIcon />
              <p className="dropzone-title">Drop photos here</p>
              <p className="muted small">Or a whole folder of them, folders inside it included. JPEG, PNG, WebP and HEIC all work; anything else is skipped.</p>
              <div className="row dropzone-buttons">
                <button className="btn btn-primary" onClick={() => library.current?.click()}>Choose photos</button>
                <button className="btn" onClick={() => folder.current?.click()}>Choose a folder</button>
              </div>
            </div>
          )}

          {pickers}

          {tray.length > 0 && (
            <section className="add-tray" aria-labelledby="add-tray-title" data-testid="add-tray">
              <div className="queue-head">
                <h2 id="add-tray-title">Your photos</h2>
                <span className="muted small" aria-live="polite" data-testid="tray-state">
                  {sorting.at === 'sorting' ? <><span className="spinner" aria-hidden="true" /> Sorting {plural(sorting.total, 'photo')}…</>
                    : trayLine(tray)}
                </span>
              </div>
              {sorting.at === 'sorted' && sorting.message && <p className="notice" role="status" data-testid="tray-message">{sorting.message}</p>}
              <ul className="queue-list" aria-label="Your photos, sorted">
                {tray.map((p) => (
                  <li key={p.key} className="queue-row add-tray-row" data-testid="tray-row">
                    <AddedPicture item={null} fallback={p.url} />
                    <label className="add-tray-choice">
                      <span className="visually-hidden">What {p.file.name} shows</span>
                      <select value={valueOf(p)} disabled={sending}
                        onChange={(e) => putTray(trayRef.current.map((q) => (q.key === p.key ? choose(q, e.target.value) : q)))}>
                        {choicesFor(tray).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                      </select>
                    </label>
                    <span className="queue-file muted small">{p.file.name}</span>
                    <button type="button" className="btn btn-icon btn-ghost" aria-label={`Remove ${p.file.name}`} disabled={sending}
                      onClick={() => remove(p.key)}><CloseIcon /></button>
                  </li>
                ))}
              </ul>
              <div className="row">
                <button type="button" className="btn btn-primary" disabled={sending || sorting.at === 'sorting'} onClick={() => void addTray()}>
                  {sending ? 'Adding…' : `Add ${tray.length === 1 ? 'it' : 'these'}`}
                </button>
                <button type="button" className="btn btn-ghost" disabled={sending} onClick={clearTray}>Clear</button>
              </div>
            </section>
          )}
        </>
      )}

      {shoesSent.length > 0 && (
        <section aria-label="Shoes added" data-testid="shoes-sent">
          {shoesSent.map((s) => (
            <div key={s.item.id} className="shoe-add">
              <p className={`notice${s.error ? ' notice-warn' : ''}`} role="status" data-testid="shoe-added">
                {s.duplicate ? (s.total > 1 ? 'The first photo is already in your closet, so nothing was added.' : 'This photo is already in your closet.')
                  : shoeAddedLine(s.added, s.total)}
                {s.error ? ` ${s.error} You can add the others on the shoe's page.` : ''}
              </p>
              <ul className="queue-list" aria-label="The shoe">
                <AddedRow item={known.get(s.item.id) ?? s.item} testId="shoe-added-item" />
              </ul>
              <div className="row">
                <Link to={`/item/${encodeURIComponent(s.item.id)}`} className="btn btn-primary">See the shoe</Link>
              </div>
            </div>
          ))}
        </section>
      )}

      {note && <p className="notice import-note" role="status" data-testid="import-note">{note}</p>}

      {open.length > 0 && !offline && (
        <section className="several-open" aria-labelledby="several-open-title">
          <h2 id="several-open-title">Photos of several pieces to check</h2>
          <Card>
            {open.map((s) => (
              <Link key={s.id} to={`/add/several/${encodeURIComponent(s.id)}`} className="several-open-row" data-testid="several-open">
                <img src={s.thumb_url} alt="" loading="lazy" />
                <span className="several-open-text">
                  <span>{sourceLine(s.state, s.boxes.length, s.note)}</span>
                  <span className="muted small">{s.note && s.state === 'finding' ? s.note : 'Check the boxes, then add the items.'}</span>
                </span>
                <span className="btn btn-small">Check</span>
              </Link>
            ))}
          </Card>
        </section>
      )}

      {longBatch && !paused && !offline && (
        <p className="notice">Keep this screen on until the uploads finish. {pending} photos to go.</p>
      )}

      {queue.length > 0 && (
        <div className="queue">
          <div className="queue-head">
            <h2>Import</h2>
            <span className="muted small" data-testid="queue-summary" aria-live="polite">
              {paused && pending ? 'Paused · ' : ''}{summaryText(counts)}
            </span>
          </div>
          {pending > 1 && perPhotoUsd !== null && profile !== 'demo' && (
            <p className="muted small" data-testid="import-cost">{importLine(pending, perPhotoUsd)}</p>
          )}
          {pending > 0 && (
            <div className="row queue-controls">
              {paused
                ? <button className="btn btn-small btn-primary" onClick={() => uploads.resume()}>Carry on</button>
                : <button className="btn btn-small" onClick={() => uploads.pause()}>Pause</button>}
              <button className="btn btn-small btn-ghost" onClick={cancelImport}>Cancel the rest</button>
              {paused && <span className="muted small">Uploads already going will finish; nothing new starts.</span>}
            </div>
          )}
          {waitsBecause && (
            <p className="notice" role="status" data-testid="import-waiting">
              {tagNotice('waiting', null, waitsBecause)} <Link to="/settings">Open Settings</Link>
            </p>
          )}
          <ul className="queue-list">
            {queue.map((e) => <QueueRow key={e.id} entry={e} item={itemOf(e)} />)}
          </ul>
          {!pending && counts.missing === 0 && (
            <div className="row queue-done">
              {queue.some((e) => e.status === 'done' && !e.sourceId) && <Link to="/" className="btn btn-primary">See them in your closet</Link>}
              {counts.failed > 1 && <button className="btn" onClick={() => uploads.retryFailed()}>Retry all that didn't work</button>}
              <button className="btn btn-ghost" onClick={clearFinished}>Clear list</button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/** One photo of the import. Once Closet knows the item it became (`item`), the row shows that item, what Claude called
 * it or how far it has got, and opens it; the file's name stays, small, beside how the upload went. */
function QueueRow({ entry, item }: { entry: QueueEntry; item: ItemSummary | null }) {
  const preview = previewOf(entry.id);
  const status = (
    <span className="queue-status" data-testid="queue-status">
      {(entry.status === 'done' || entry.status === 'duplicate') && <CheckIcon />}
      {entry.status === 'failed' && <WarnIcon />}
      {(entry.status === 'resizing' || entry.status === 'uploading') && <span className="spinner" aria-hidden="true" />}
      {STATUS_TEXT[entry.status]}
      {entry.status === 'uploading' && entry.attempts > 1 ? ` (try ${entry.attempts})` : ''}
    </span>
  );
  if (item) {
    return (
      <AddedRow item={item} fallback={preview} className={`status-${entry.status}`} testId="queue-row"
        sub={<>{status}<span aria-hidden="true">·</span><span className="queue-file">{entry.name}</span></>} />
    );
  }
  return (
    <li className={`queue-row status-${entry.status}`} data-testid="queue-row">
      <AddedPicture item={null} fallback={preview} />
      <div className="queue-info">
        <span className="queue-name">{entry.name}</span>
        {status}
        {entry.error && <span className={entry.status === 'failed' ? 'queue-error' : 'queue-note'} data-testid="queue-error">{entry.error}</span>}
      </div>
      {entry.status === 'failed' && <button className="btn btn-small" onClick={() => uploads.retry(entry.id)}>Retry</button>}
      {entry.sourceId && (entry.status === 'done' || entry.status === 'duplicate') && (
        <Link to={`/add/several/${encodeURIComponent(entry.sourceId)}`} className="btn btn-small">Check the pieces</Link>
      )}
    </li>
  );
}
