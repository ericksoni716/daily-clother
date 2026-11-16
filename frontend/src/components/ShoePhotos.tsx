import { useRef, useState } from 'react';
import { api, ApiError } from '../api';
import { preparePhoto } from '../resize';
import {
  MAX_EXTRA_PHOTOS, NO_SIDE, noSidePhoto, ONE_SIDE_QUESTION, OUTSIDE_HINT, OUTSIDE_QUESTION, outsideQuestion, photoRoom,
  sortingViews, viewLabel,
} from '../shoe';
import type { Item, ShoeView } from '../types';
import { sha256 } from '../uploads';
import { CloseIcon, ImagesIcon } from './Icons';
import './Shoe.css';

interface Props {
  item: Item;
  disabled: boolean;
  onSaved(item: Item, saidAs: string): void;
  onError(message: string): void;
}

/** Sends the chosen photos of a shoe one at a time, in the order chosen, as many as it has room for; `onItem` gets the
 * shoe after each. Returns how many went and how many did not fit. A failure stops it; the photos sent stay. */
export async function sendShoePhotos(itemId: string, files: File[], room: number, onItem: (item: Item) => void):
  Promise<{ sent: number; left: number }> {
  const chosen = files.slice(0, Math.max(0, room));
  let sent = 0;
  for (const file of chosen) {
    const [prepared, hash] = await Promise.all([preparePhoto(file), sha256(file).catch(() => null)]);
    onItem(await api.addShoePhoto(itemId, prepared.blob, prepared.filename, hash));
    sent++;
  }
  return { sent, left: files.length - chosen.length };
}

/** The words for photos chosen that did not fit. */
export const notFitting = (left: number) =>
  `A shoe can have up to ${MAX_EXTRA_PHOTOS} more photos, so ${left === 1 ? 'one photo was' : `${left} photos were`} left out.`;

/** "Add photos": the phone offers its camera or its library; several can be chosen at once. */
export function AddShoePhotos({ item, disabled, onSaved, onError, label = 'Add photos' }: Props & { label?: string }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const room = photoRoom(item);
  const take = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    const got: { last: Item | null } = { last: null };
    try {
      const { sent, left } = await sendShoePhotos(item.id, files, room, (it) => { got.last = it; });
      if (got.last) onSaved(got.last, sent === 1 ? 'Photo added; Closet sorts out which view it shows' : `${sent} photos added; Closet sorts out which view each shows`);
      if (left) onError(notFitting(left));
    } catch (e) {
      if (got.last) onSaved(got.last, 'Some photos were added');
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <input ref={input} className="visually-hidden" type="file" accept="image/*" multiple tabIndex={-1}
        aria-hidden="true" data-testid="shoe-photos-input" onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = '';
          void take(files);
        }} />
      <button type="button" className="btn btn-small" disabled={disabled || busy || room === 0} onClick={() => input.current?.click()}>
        <ImagesIcon />{busy ? 'Sending the photos…' : label}
      </button>
    </>
  );
}

/** While Closet cannot tell the outside of the shoe from the inside (a logo or stripe on one side only), it asks: which
 * photo shows the outside, or, with one photo, whether it is the outside or the inside. */
function OutsideQuestion({ item, disabled, onSaved, onError }: Props) {
  const [busy, setBusy] = useState(false);
  const asked = outsideQuestion(item);
  if (!asked) return null;
  const say = async (photoId: string, view: ShoeView) => {
    setBusy(true);
    try {
      onSaved(await api.setPhotoView(item.id, photoId, view), view === 'outer' ? 'Noted: that is the outside' : 'Noted: that is the inside');
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  const off = disabled || busy;
  if (asked.one) {
    const { photo, n } = asked.photos[0];
    return (
      <div className="notice shoe-ask" role="group" aria-labelledby={`ask-${item.id}`} data-testid="shoe-ask">
        <div className="shoe-ask-body">
          <p id={`ask-${item.id}`}><strong>{ONE_SIDE_QUESTION}</strong> {OUTSIDE_HINT}</p>
          <img className="shoe-ask-photo" src={photo.thumb_url ?? photo.url ?? ''} alt={`Photo ${n}`} />
          <div className="row">
            <button type="button" className="btn" disabled={off} onClick={() => void say(photo.id, 'outer')}>The outside</button>
            <button type="button" className="btn" disabled={off} onClick={() => void say(photo.id, 'inner')}>The inside</button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="notice shoe-ask" role="group" aria-labelledby={`ask-${item.id}`} data-testid="shoe-ask">
      <div className="shoe-ask-body">
        <p id={`ask-${item.id}`}><strong>{OUTSIDE_QUESTION}</strong> ({OUTSIDE_HINT})</p>
        <div className="shoe-ask-choices">
          {asked.photos.map(({ photo, n }) => (
            <button key={photo.id} type="button" className="shoe-ask-choice" disabled={off}
              aria-label={`Photo ${n} shows the outside`} onClick={() => void say(photo.id, 'outer')}>
              <img src={photo.thumb_url ?? photo.url ?? ''} alt="" />
              <span>Photo {n}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/** A shoe's photos on its page: each with what it shows, the other photos with a way to remove them, "Add photos",
 * the question about the outside when Closet has to ask, and a word when no photo shows the shoe from the side. */
export function ShoePhotos(props: Props) {
  const { item, disabled, onSaved, onError } = props;
  const [busy, setBusy] = useState<string | null>(null);
  const views = item.views;
  if (!views || !item.photos.length) return null;
  const remove = async (photoId: string) => {
    setBusy(photoId);
    try {
      onSaved(await api.removeShoePhoto(item.id, photoId), 'Photo removed');
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };
  const room = photoRoom(item);
  return (
    <section className="shoe-photos" aria-labelledby={`photos-${item.id}`} data-testid="shoe-photos">
      <h3 className="chip-group-title" id={`photos-${item.id}`}>Photos of the shoe</h3>
      <OutsideQuestion {...props} />
      <ul className="shoe-photo-row">
        {item.photos.map((p, i) => {
          const said = viewLabel(p, views);
          return (
            <li key={p.id} className="shoe-photo">
              <img src={p.thumb_url ?? p.url ?? ''} alt={`Photo ${i + 1}${said ? `: ${said}` : ''}`} />
              <span className={`shoe-photo-label${sortingViews(views) && p.view_by !== 'owner' ? ' muted' : ''}`} aria-hidden="true">
                {said ?? (p.kind === 'front' ? 'main photo' : '')}
              </span>
              {p.kind !== 'front' && (
                <button type="button" className="btn btn-ghost btn-small shoe-photo-remove" disabled={disabled || busy !== null}
                  aria-label={`Remove photo ${i + 1}`} title="Remove this photo" onClick={() => void remove(p.id)}>
                  <CloseIcon />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {views.message && <p className="muted small" role="status">{views.message}</p>}
      {noSidePhoto(item) && <p className="notice" data-testid="shoe-no-side">{NO_SIDE}</p>}
      <div className="row shoe-fix-actions">
        <AddShoePhotos {...props} />
        <span className="muted small">
          {room === 0 ? `That's the most a shoe can have (${MAX_EXTRA_PHOTOS} besides the main photo).`
            : 'From above, the front, the back and the other side, in any order.'}
        </span>
      </div>
    </section>
  );
}
