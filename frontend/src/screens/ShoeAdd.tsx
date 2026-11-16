import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import { CameraIcon, CloseIcon, ImagesIcon } from '../components/Icons';
import { sendShoePhotos } from '../components/ShoePhotos';
import { Link } from '../router';
import { preparePhoto, splitPhotos } from '../resize';
import { MAX_PHOTOS, photoRoom, shoeAddedLine, tooManyPhotos } from '../shoe';
import type { Item } from '../types';
import { sha256 } from '../uploads';
import '../components/Shoe.css';

/** One photo taken or chosen, waiting in the row until "Add this shoe". Its key is also the upload's key when it is
 * the first photo, so the same shoe sent again after a dropped connection is not made twice. */
interface Shot { key: string; file: File; url: string }

type Step =
  | { at: 'choose' }
  | { at: 'sending'; sent: number; total: number }
  | { at: 'done'; itemId: string; added: number; total: number; duplicate: boolean; error?: string };

const newKey = () => (typeof crypto.randomUUID === 'function' ? crypto.randomUUID()
  : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`);

/** Can this browser show the camera on the page (a secure address, and a camera to ask for)? */
const liveCamera = () => typeof window !== 'undefined' && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;

/** The same file chosen twice. */
const sameFile = (a: File, b: File) => a.name === b.name && a.size === b.size && a.lastModified === b.lastModified;

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** A photo in the row; a photo this browser cannot show (HEIC on a Windows browser) is still added. */
function Thumb({ url, alt }: { url: string; alt: string }) {
  const [broken, setBroken] = useState(false);
  return broken
    ? <span className="shoe-photo-none" role="img" aria-label={alt}><ImagesIcon /></span>
    : <img src={url} alt={alt} onError={() => setBroken(true)} />;
}

/** Add a shoe in one step: the owner takes or chooses all of its photos (1 to 6, in any order), which wait in a row
 * (each can be removed), and "Add this shoe" sends them: the first makes the shoe, the others are added to it.
 * Closet then sorts them into views itself and uses the outer side as the closet picture. */
export function ShoeAdd() {
  const [step, setStep] = useState<Step>({ at: 'choose' });
  const [shots, setShots] = useState<Shot[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const row = useRef<Shot[]>([]);             // the row as the handlers see it: a photo from the camera comes later
  const urls = useRef(new Set<string>());     // the thumbnails' addresses, let go when a photo leaves or the page closes
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);

  const stopCamera = () => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  };
  useEffect(() => stopCamera, []);
  useEffect(() => {
    const kept = urls.current;
    return () => {
      kept.forEach((u) => URL.revokeObjectURL(u));
      kept.clear();
    };
  }, []);
  useEffect(() => {
    if (live && video.current && stream.current) {
      video.current.srcObject = stream.current;
      void video.current.play().catch(() => undefined);
    }
  }, [live]);

  const put = (next: Shot[]) => {
    row.current = next;
    setShots(next);
  };

  function addShots(files: File[]) {
    if (!files.length) return;
    setError(null);
    const { photos, skipped } = splitPhotos(files);
    const now = row.current;
    const fresh = photos.filter((f, i) => !now.some((s) => sameFile(s.file, f)) && photos.findIndex((g) => sameFile(g, f)) === i);
    const taken = fresh.slice(0, Math.max(0, MAX_PHOTOS - now.length));
    const said: string[] = [];
    if (fresh.length > taken.length) said.push(tooManyPhotos(fresh.length - taken.length));
    if (photos.length > fresh.length) said.push(`${plural(photos.length - fresh.length, 'photo was', 'photos were')} already in the row.`);
    if (skipped.length) said.push(`Skipped ${plural(skipped.length, 'file')} that ${skipped.length === 1 ? 'is not a photo' : 'are not photos'}.`);
    setNote(said.join(' ') || null);
    if (!taken.length) return;
    put([...now, ...taken.map((file) => {
      const url = URL.createObjectURL(file);
      urls.current.add(url);
      return { key: newKey(), file, url };
    })]);
  }

  function letGo(gone: Shot[]) {
    for (const s of gone) {
      URL.revokeObjectURL(s.url);
      urls.current.delete(s.url);
    }
  }

  function remove(key: string) {
    letGo(row.current.filter((s) => s.key === key));
    put(row.current.filter((s) => s.key !== key));
    setNote(null);
  }

  async function openCamera() {
    setCameraError(null);
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      setLive(true);
    } catch {
      setCameraError("The camera couldn't be opened here, so take the photos with your phone's camera instead.");
    }
  }

  const closeCamera = () => {
    stopCamera();
    setLive(false);
  };

  /** The camera on the page where the browser allows it (it stays open for the next photo), else the phone's camera
   * app, one photo each time. */
  const takePhoto = () => {
    if (liveCamera() && !cameraError) void openCamera();
    else camera.current?.click();
  };

  function snap() {
    const v = video.current;
    if (!v || !v.videoWidth || row.current.length >= MAX_PHOTOS) return;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d')?.drawImage(v, 0, 0);
    canvas.toBlob((blob) => {
      const at = Date.now();
      if (blob) addShots([new File([blob], `shoe-${at}.jpg`, { type: 'image/jpeg', lastModified: at })]);
    }, 'image/jpeg', 0.92);
  }

  function finish(done: Step) {
    letGo(row.current);
    put([]);
    setStep(done);
  }

  async function send() {
    const chosen = row.current;
    if (!chosen.length) return;
    closeCamera();
    setError(null);
    setNote(null);
    const total = chosen.length;
    setStep({ at: 'sending', sent: 0, total });
    let item: Item & { duplicate?: boolean };
    try {
      const first = chosen[0].file;
      const [prepared, hash] = await Promise.all([preparePhoto(first), sha256(first).catch(() => null)]);
      item = await api.upload(prepared.blob, prepared.filename, chosen[0].key, hash, undefined, true);
    } catch (e) {
      setStep({ at: 'choose' });
      setError((e as ApiError).message);
      return;
    }
    if (item.duplicate) {
      finish({ at: 'done', itemId: item.id, added: 0, total, duplicate: true });
      return;
    }
    let added = 1;
    setStep({ at: 'sending', sent: added, total });
    let failed: string | undefined;
    try {
      await sendShoePhotos(item.id, chosen.slice(1).map((s) => s.file), photoRoom(item), () => {
        added += 1;
        setStep({ at: 'sending', sent: added, total });
      });
    } catch (e) {
      failed = (e as ApiError).message;
    }
    finish({ at: 'done', itemId: item.id, added, total, duplicate: false, error: failed });
  }

  if (step.at === 'done') {
    const said = step.duplicate
      ? (step.total > 1 ? 'The first photo is already in your closet, so nothing was added.' : 'This photo is already in your closet.')
      : shoeAddedLine(step.added, step.total);
    return (
      <div className="shoe-add" data-testid="shoe-add">
        <p className={`notice${step.error ? ' notice-warn' : ''}`} role="status" data-testid="shoe-added">
          {said}{step.error ? ` ${step.error} You can add the others on the shoe's page.` : ''}
        </p>
        <div className="row">
          <Link to={`/item/${encodeURIComponent(step.itemId)}`} className="btn btn-primary">See the shoe</Link>
          <button type="button" className="btn" onClick={() => setStep({ at: 'choose' })}>Add another shoe</button>
        </div>
      </div>
    );
  }

  const sending = step.at === 'sending';
  const full = shots.length >= MAX_PHOTOS;
  const some = shots.length > 0;
  return (
    <div className="shoe-add" data-testid="shoe-add">
      <p className="muted add-intro">Take or choose up to {MAX_PHOTOS} photos of one shoe, in any order. Closet works out
        which photo is which. What helps:</p>
      <ul className="shoe-tips">
        <li>One shoe on its own, not the pair.</li>
        <li>Its side, the other side, from above, the front and the back.</li>
        <li>A plain floor or wall behind it, and even light.</li>
      </ul>
      {live && (
        <div className="shoe-frame">
          <video ref={video} playsInline muted aria-label="The camera" />
        </div>
      )}
      {some && (
        <ul className="shoe-photo-row" aria-label="Photos of the shoe">
          {shots.map((s, i) => (
            <li key={s.key} className="shoe-photo">
              <Thumb url={s.url} alt={`Photo ${i + 1}`} />
              <button type="button" className="btn btn-ghost btn-small shoe-photo-remove" disabled={sending}
                aria-label={`Remove photo ${i + 1}`} title="Remove this photo" onClick={() => remove(s.key)}>
                <CloseIcon />
              </button>
            </li>
          ))}
        </ul>
      )}
      {some && (
        <p className="muted small" data-testid="shoe-count">
          {full ? `That's ${MAX_PHOTOS} photos, the most for one shoe.` : `${plural(shots.length, 'photo')} so far, up to ${MAX_PHOTOS}.`}
          {live ? ' Close the camera when you have them all.' : ''}
        </p>
      )}
      {cameraError && <p className="notice" role="status">{cameraError}</p>}
      {note && <p className="notice" role="status" data-testid="shoe-note">{note}</p>}
      {error && <p className="notice notice-warn" role="alert">{error}</p>}
      {sending && (
        <p className="notice" role="status">Adding the shoe: photo {Math.min(step.sent + 1, step.total)} of {step.total}…</p>
      )}
      <div className="row">
        {live ? (
          <>
            <button type="button" className={`btn${some ? '' : ' btn-primary'}`} disabled={full || sending} onClick={snap}>
              <CameraIcon />Take the photo
            </button>
            <button type="button" className="btn" disabled={sending} onClick={closeCamera}>Close the camera</button>
          </>
        ) : (
          <>
            <button type="button" className={`btn${some ? '' : ' btn-primary'}`} disabled={full || sending} onClick={takePhoto}>
              <CameraIcon />Take a photo
            </button>
            <button type="button" className="btn" disabled={full || sending} onClick={() => library.current?.click()}>
              <ImagesIcon />Choose photos
            </button>
          </>
        )}
      </div>
      <div className="row">
        <button type="button" className={`btn${some ? ' btn-primary' : ''}`} disabled={!some || sending} onClick={() => void send()}>
          Add this shoe
        </button>
      </div>
      <input ref={camera} className="visually-hidden" type="file" accept="image/*" capture="environment" tabIndex={-1}
        aria-hidden="true" data-testid="shoe-camera-input" onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = '';
          addShots(files);
        }} />
      <input ref={library} className="visually-hidden" type="file" accept="image/*" multiple tabIndex={-1}
        aria-hidden="true" data-testid="shoe-library-input" onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = '';
          addShots(files);
        }} />
    </div>
  );
}
