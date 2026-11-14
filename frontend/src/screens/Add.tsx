import { useEffect, useRef, useState, useSyncExternalStore, type DragEvent } from 'react';
import { api } from '../api';
import { CameraIcon, CheckIcon, CloudOffIcon, ImagesIcon, WarnIcon } from '../components/Icons';
import { Notice, PageHeader } from '../components/ui';
import { filesFromDrop, splitPhotos } from '../resize';
import { Link, useMediaQuery } from '../router';
import { importLine } from '../spend';
import { useCloset } from '../store';
import { countEntries, type QueueEntry, type UploadStatus } from '../uploadQueue';
import { addFiles, cancelImport, clearFinished, previewOf, uploads } from '../uploads';

const STATUS_TEXT: Record<UploadStatus, string> = {
  waiting: 'Waiting',
  resizing: 'Resizing',
  uploading: 'Uploading',
  done: 'Done',
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
  const { offline, profile } = useCloset();
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
  useEffect(() => {
    if (offline || profile === 'demo') return;
    let current = true;
    api.tagSpend().then((s) => current && setPerPhotoUsd(s.allowed ? s.per_photo_usd : null), () => undefined);
    return () => {
      current = false;
    };
  }, [offline, profile]);

  const counts = countEntries(queue);
  const pending = counts.waiting + counts.uploading;
  const longBatch = phone && pending > 5;
  useWakeLock(pending > 0 && longBatch && !paused);

  function take(list: FileList | File[] | null) {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    const { photos, skipped } = splitPhotos(files);
    const alreadyListed = photos.length ? addFiles(photos) : 0;
    setNote(describeAdded(photos.length - alreadyListed, alreadyListed, skipped));
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
          <p className="muted add-intro">One piece of clothing per photo works best: lay it flat or hang it against a plain wall. Closet removes the background for you. Photos already in your closet are recognised and not added twice.</p>

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
        </>
      )}

      {note && <p className="notice import-note" role="status" data-testid="import-note">{note}</p>}

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
          <ul className="queue-list">
            {queue.map((e) => <QueueRow key={e.id} entry={e} />)}
          </ul>
          {!pending && counts.missing === 0 && (
            <div className="row queue-done">
              {counts.done > 0 && <Link to="/" className="btn btn-primary">See them in your closet</Link>}
              {counts.failed > 1 && <button className="btn" onClick={() => uploads.retryFailed()}>Retry all that didn't work</button>}
              <button className="btn btn-ghost" onClick={clearFinished}>Clear list</button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function QueueRow({ entry }: { entry: QueueEntry }) {
  const preview = previewOf(entry.id);
  const [broken, setBroken] = useState(false);
  return (
    <li className={`queue-row status-${entry.status}`} data-testid="queue-row">
      <div className="queue-thumb">
        {preview && !broken ? <img src={preview} alt="" loading="lazy" onError={() => setBroken(true)} /> : <ImagesIcon />}
      </div>
      <div className="queue-info">
        <span className="queue-name">{entry.name}</span>
        <span className="queue-status" data-testid="queue-status">
          {(entry.status === 'done' || entry.status === 'duplicate') && <CheckIcon />}
          {entry.status === 'failed' && <WarnIcon />}
          {(entry.status === 'resizing' || entry.status === 'uploading') && <span className="spinner" aria-hidden="true" />}
          {STATUS_TEXT[entry.status]}
          {entry.status === 'uploading' && entry.attempts > 1 ? ` (try ${entry.attempts})` : ''}
        </span>
        {entry.error && <span className={entry.status === 'failed' ? 'queue-error' : 'queue-note'} data-testid="queue-error">{entry.error}</span>}
      </div>
      {entry.status === 'failed' && <button className="btn btn-small" onClick={() => uploads.retry(entry.id)}>Retry</button>}
    </li>
  );
}
