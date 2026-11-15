import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import { CameraIcon, ImagesIcon, WarnIcon } from '../components/Icons';
import { ShoeGuide } from '../components/ShoeGuide';
import { Link } from '../router';
import { preparePhoto } from '../resize';
import { checkHeadline } from '../shoe';
import type { ShoeCheck } from '../types';
import { sha256 } from '../uploads';
import '../components/Shoe.css';

type Step =
  | { at: 'start' }
  | { at: 'camera' }
  | { at: 'checking'; file: File; preview: string }
  | { at: 'checked'; file: File; preview: string; check: ShoeCheck | null; error?: string }
  | { at: 'adding'; file: File; preview: string }
  | { at: 'second'; itemId: string; error?: string; sending?: boolean }
  | { at: 'done'; itemId: string; second: boolean; duplicate: boolean };

const newKey = () => (typeof crypto.randomUUID === 'function' ? crypto.randomUUID()
  : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`);

/** Can this browser show the camera on the page (a secure address, and a camera to ask for)? */
const liveCamera = () => typeof window !== 'undefined' && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;

/** Add a shoe: one shoe, side-on, toe to the left, with the outline to place it in; Closet checks the photo at once
 * and says if it will not trace well, and why; then an optional second photo from the front or from above. */
export function ShoeAdd() {
  const [step, setStep] = useState<Step>({ at: 'start' });
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const second = useRef<HTMLInputElement>(null);
  const [view, setView] = useState<'front' | 'top'>('front');
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const preview = 'preview' in step ? step.preview : null;

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const stopCamera = () => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  };
  useEffect(() => stopCamera, []);

  async function openCamera() {
    setCameraError(null);
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      setStep({ at: 'camera' });
    } catch {
      setCameraError("The camera couldn't be opened here, so take the photo with your phone's camera instead.");
    }
  }
  useEffect(() => {
    if (step.at === 'camera' && video.current && stream.current) {
      video.current.srcObject = stream.current;
      void video.current.play().catch(() => undefined);
    }
  }, [step.at]);

  function snap() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d')?.drawImage(v, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      stopCamera();
      void check(new File([blob], 'shoe.jpg', { type: 'image/jpeg', lastModified: Date.now() }));
    }, 'image/jpeg', 0.92);
  }

  async function check(file: File) {
    const shown = URL.createObjectURL(file);
    setStep({ at: 'checking', file, preview: shown });
    try {
      const prepared = await preparePhoto(file);
      const answer = await api.checkShoe(prepared.blob, prepared.filename);
      setStep({ at: 'checked', file, preview: shown, check: answer });
    } catch (e) {
      setStep({ at: 'checked', file, preview: shown, check: null, error: (e as ApiError).message });
    }
  }

  async function add(file: File, shown: string) {
    setStep({ at: 'adding', file, preview: shown });
    try {
      const [prepared, hash] = await Promise.all([preparePhoto(file), sha256(file).catch(() => null)]);
      const item = await api.upload(prepared.blob, prepared.filename, newKey(), hash);
      if (item.duplicate) setStep({ at: 'done', itemId: item.id, second: false, duplicate: true });
      else setStep({ at: 'second', itemId: item.id });
    } catch (e) {
      setStep({ at: 'checked', file, preview: shown, check: null, error: (e as ApiError).message });
    }
  }

  async function addSecond(itemId: string, file: File | undefined) {
    if (!file) return;
    setStep({ at: 'second', itemId, sending: true });
    try {
      const [prepared, hash] = await Promise.all([preparePhoto(file), sha256(file).catch(() => null)]);
      await api.addShoeView(itemId, prepared.blob, prepared.filename, view, hash);
      setStep({ at: 'done', itemId, second: true, duplicate: false });
    } catch (e) {
      setStep({ at: 'second', itemId, error: (e as ApiError).message });
    }
  }

  const retake = () => {
    stopCamera();
    setStep({ at: 'start' });
  };

  const pickers = (
    <>
      <input ref={camera} className="visually-hidden" type="file" accept="image/*" capture="environment" tabIndex={-1}
        aria-hidden="true" data-testid="shoe-camera-input" onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = '';
          if (f) void check(f);
        }} />
      <input ref={library} className="visually-hidden" type="file" accept="image/*" tabIndex={-1}
        aria-hidden="true" data-testid="shoe-library-input" onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = '';
          if (f) void check(f);
        }} />
    </>
  );

  if (step.at === 'start' || step.at === 'camera') {
    const live = step.at === 'camera';
    return (
      <div className="shoe-add" data-testid="shoe-add">
        <p className="muted add-intro">Closet draws a shoe from a photo of its side. For the closest drawing:</p>
        <ol className="shoe-steps">
          <li>One shoe on its own, not the pair.</li>
          <li>From the side, toe to the left, filling the outline.</li>
          <li>On a plain floor or against a plain wall, in even light.</li>
        </ol>
        <div className="shoe-frame">
          {live && <video ref={video} playsInline muted aria-label="The camera" />}
          <ShoeGuide />
          <p className="shoe-frame-words">{live ? 'Line the shoe up with the outline' : 'Place the shoe like this: toe to the left'}</p>
        </div>
        {cameraError && <p className="notice" role="status">{cameraError}</p>}
        <div className="row">
          {live ? (
            <>
              <button type="button" className="btn btn-primary" onClick={snap}><CameraIcon />Take the photo</button>
              <button type="button" className="btn btn-ghost" onClick={retake}>Close the camera</button>
            </>
          ) : (
            <>
              {liveCamera() && !cameraError && (
                <button type="button" className="btn btn-primary" onClick={() => void openCamera()}><CameraIcon />Open the camera</button>
              )}
              <button type="button" className={`btn${liveCamera() && !cameraError ? '' : ' btn-primary'}`} onClick={() => camera.current?.click()}>
                <CameraIcon />Take photo
              </button>
              <button type="button" className="btn" onClick={() => library.current?.click()}><ImagesIcon />Choose from library</button>
            </>
          )}
        </div>
        {pickers}
      </div>
    );
  }

  if (step.at === 'checking' || step.at === 'checked' || step.at === 'adding') {
    const result = step.at === 'checked' ? step : null;
    return (
      <div className="shoe-add" data-testid="shoe-add">
        <div className="shoe-frame">
          <img src={step.preview} alt="The photo just taken" />
          <ShoeGuide />
        </div>
        {step.at === 'checking' && <p className="notice" role="status">Checking the photo…</p>}
        {step.at === 'adding' && <p className="notice" role="status">Adding the shoe…</p>}
        {result?.error && <p className="notice notice-warn" role="alert">{result.error}</p>}
        {result?.check && result.check.ok && (
          <p className="notice" role="status" data-testid="shoe-check">{checkHeadline(result.check)} Closet draws it from this photo once it's added.</p>
        )}
        {result?.check && !result.check.ok && (
          <div className="notice notice-warn" role="alert" data-testid="shoe-check">
            <WarnIcon />
            <div>
              <p><strong>{checkHeadline(result.check)}</strong> If you add it anyway, the shoe is drawn from its details instead.</p>
              <ul className="shoe-reasons">{result.check.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          </div>
        )}
        {result && (
          <div className="row">
            {result.check?.ok !== false && (
              <button type="button" className="btn btn-primary" onClick={() => void add(result.file, result.preview)}>Add this shoe</button>
            )}
            <button type="button" className={`btn${result.check?.ok === false ? ' btn-primary' : ''}`} onClick={retake}>
              <CameraIcon />Retake
            </button>
            {result.check?.ok === false && (
              <button type="button" className="btn btn-ghost" onClick={() => void add(result.file, result.preview)}>Add it anyway</button>
            )}
          </div>
        )}
      </div>
    );
  }

  if (step.at === 'second') {
    return (
      <div className="shoe-add" data-testid="shoe-add">
        <p className="notice" role="status">The shoe is added. Its background is removed and it's drawn from its photo in a moment.</p>
        <p>A second photo, from the front or from above, helps draw the shoe from the front later. You can skip it.</p>
        <fieldset className="row" disabled={step.sending}>
          <legend className="visually-hidden">Where the second photo is taken from</legend>
          {(['front', 'top'] as const).map((v) => (
            <label key={v} className="chip-label">
              <input type="radio" name="shoe-view" value={v} checked={view === v} onChange={() => setView(v)} />
              {v === 'front' ? ' From the front' : ' From above'}
            </label>
          ))}
        </fieldset>
        {step.error && <p className="notice notice-warn" role="alert">{step.error}</p>}
        <div className="row">
          <button type="button" className="btn btn-primary" disabled={step.sending} onClick={() => second.current?.click()}>
            <CameraIcon />{step.sending ? 'Sending the photo…' : 'Take the second photo'}
          </button>
          <button type="button" className="btn btn-ghost" disabled={step.sending}
            onClick={() => setStep({ at: 'done', itemId: step.itemId, second: false, duplicate: false })}>Skip</button>
        </div>
        <input ref={second} className="visually-hidden" type="file" accept="image/*" capture="environment" tabIndex={-1}
          aria-hidden="true" data-testid="shoe-second-input" onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = '';
            void addSecond(step.itemId, f);
          }} />
      </div>
    );
  }

  return (
    <div className="shoe-add" data-testid="shoe-add">
      <p className="notice" role="status">
        {step.duplicate ? 'This photo is already in your closet.'
          : step.second ? 'The shoe and its second photo are added.' : 'The shoe is added.'}
      </p>
      <div className="row">
        <Link to={`/item/${encodeURIComponent(step.itemId)}`} className="btn btn-primary">See the shoe</Link>
        <button type="button" className="btn" onClick={() => setStep({ at: 'start' })}>Add another shoe</button>
      </div>
    </div>
  );
}
