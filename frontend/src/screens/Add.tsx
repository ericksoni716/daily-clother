import { useEffect, useRef, useState, useSyncExternalStore, type DragEvent } from 'react';
import { CameraIcon, CheckIcon, CloudOffIcon, ImagesIcon, WarnIcon } from '../components/Icons';
import { filesFromDrop } from '../resize';
import { Link, useMediaQuery } from '../router';
import { useCloset } from '../store';
import type { QueueEntry, UploadStatus } from '../uploadQueue';
import { addFiles, clearFinished, previewOf, uploads } from '../uploads';

const STATUS_TEXT: Record<UploadStatus, string> = {
  waiting: 'Waiting',
  resizing: 'Resizing',
  uploading: 'Uploading',
  done: 'Done',
  failed: 'Failed',
};

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
  const desktop = useMediaQuery('(min-width: 1000px) and (pointer: fine)');
  const phone = !desktop;
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const pending = queue.filter((e) => e.status === 'waiting' || e.status === 'resizing' || e.status === 'uploading').length;
  const done = queue.filter((e) => e.status === 'done').length;
  const failed = queue.filter((e) => e.status === 'failed').length;
  const longBatch = phone && pending > 5;
  useWakeLock(pending > 0 && longBatch);

  function take(list: FileList | File[] | null) {
    const files = Array.from(list ?? []);
    if (files.length) addFiles(files);
  }

  async function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (offline) return;
    take(await filesFromDrop(e.dataTransfer));
  }

  return (
    <section className="add" aria-labelledby="add-title">
      <header className="page-header">
        <h1 id="add-title">Add clothes</h1>
      </header>
      {profile === 'demo' && <p className="notice">You're in the demo closet, so new photos are added to the demo. Use "Back to my closet" above to add to your own.</p>}

      {offline ? (
        <div className="notice notice-warn">
          <CloudOffIcon />
          <p>Adding photos needs Closet on your computer to be reachable. Check that the computer is on and Closet is running; this page will work again as soon as it is.</p>
        </div>
      ) : (
        <>
          <p className="muted add-intro">One piece of clothing per photo works best: lay it flat or hang it against a plain wall. Closet removes the background for you.</p>

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
              <p className="muted small">Or a whole folder of them. JPEG, PNG, WebP and HEIC all work.</p>
              <button className="btn btn-primary" onClick={() => library.current?.click()}>Choose photos</button>
            </div>
          )}

          <input ref={camera} className="visually-hidden" type="file" accept="image/*" capture="environment" tabIndex={-1}
            aria-hidden="true" data-testid="camera-input" onChange={(e) => { take(e.target.files); e.target.value = ''; }} />
          <input ref={library} className="visually-hidden" type="file" accept="image/*" multiple tabIndex={-1}
            aria-hidden="true" data-testid="library-input" onChange={(e) => { take(e.target.files); e.target.value = ''; }} />
        </>
      )}

      {longBatch && (
        <p className="notice">Keep this screen on until the uploads finish. {pending} photos to go.</p>
      )}

      {queue.length > 0 && (
        <div className="queue">
          <div className="queue-head">
            <h2>Uploads</h2>
            <span className="muted small">
              {pending ? `${pending} to go` : `${done} added${failed ? `, ${failed} didn't work` : ''}`}
            </span>
          </div>
          <ul className="queue-list">
            {queue.map((e) => <QueueRow key={e.id} entry={e} />)}
          </ul>
          {!pending && (
            <div className="row queue-done">
              {done > 0 && <Link to="/" className="btn btn-primary">See them in your closet</Link>}
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
        {preview && !broken ? <img src={preview} alt="" onError={() => setBroken(true)} /> : <ImagesIcon />}
      </div>
      <div className="queue-info">
        <span className="queue-name">{entry.name}</span>
        <span className="queue-status" data-testid="queue-status">
          {entry.status === 'done' && <CheckIcon />}
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
