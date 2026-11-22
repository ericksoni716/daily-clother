import { useRef, useState } from 'react';
import { Sheet } from './ui';
import { api, ApiError } from '../api';
import { preparePhoto } from '../resize';
import {
  canSayOutside, MAX_EXTRA_PHOTOS, NO_SIDE, noSidePhoto, ONE_SIDE_QUESTION, OUTSIDE_HINT, OUTSIDE_QUESTION, outsideQuestion,
  photoRoom, sortingViews, viewLabel,
} from '../shoe';
import { partWords } from '../progress';
import { useItemProgress } from '../queries';
import type { Item, Photo, ShoeView } from '../types';
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
      if (got.last) onSaved(got.last, sent === 1 ? 'Photo added; Nines sorts out which view it shows' : `${sent} photos added; Nines sorts out which view each shows`);
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

/** Saying which view a photo shows (the outside or the inside), with what the page says once it is kept. */
function useSayView({ item, onSaved, onError }: Props) {
  const [busy, setBusy] = useState(false);
  const say = async (photoId: string, view: ShoeView): Promise<boolean> => {
    setBusy(true);
    try {
      onSaved(await api.setPhotoView(item.id, photoId, view), view === 'outer' ? 'Noted: that is the outside' : 'Noted: that is the inside');
      return true;
    } catch (e) {
      onError((e as ApiError).message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, say };
}

/** The question about the outside, as a choice: one photo (the outside or the inside?), or which of several. */
function OutsideChoices({ photos, disabled, onSay }: {
  photos: { photo: Photo; n: number }[];
  disabled: boolean;
  onSay(photoId: string, view: ShoeView): void;
}) {
  if (photos.length === 1) {
    const { photo, n } = photos[0];
    return (
      <>
        <img className="shoe-ask-photo" src={photo.thumb_url ?? photo.url ?? ''} alt={`Photo ${n}`} />
        <div className="row">
          <button type="button" className="btn" disabled={disabled} onClick={() => onSay(photo.id, 'outer')}>The outside</button>
          <button type="button" className="btn" disabled={disabled} onClick={() => onSay(photo.id, 'inner')}>The inside</button>
        </div>
      </>
    );
  }
  return (
    <div className="shoe-ask-choices">
      {photos.map(({ photo, n }) => (
        <button key={photo.id} type="button" className="shoe-ask-choice" disabled={disabled} aria-pressed={photo.view === 'outer'}
          aria-label={`Photo ${n} shows the outside`} onClick={() => onSay(photo.id, 'outer')}>
          <img src={photo.thumb_url ?? photo.url ?? ''} alt="" />
          <span>Photo {n}</span>
        </button>
      ))}
    </div>
  );
}

/** Once the photos are sorted, the owner can say at any time which photo shows the outside (Claude may have been sure
 * and wrong): a small button in the photos that opens the same choice the page asks when Claude is unsure. */
function SayOutside(props: Props) {
  const { item, disabled } = props;
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const { busy, say } = useSayView(props);
  if (!canSayOutside(item)) return null;
  const photos = item.photos.map((photo, i) => ({ photo, n: i + 1 }));
  const one = photos.length === 1;
  return (
    <span className="shoe-say-outside">
      <button ref={button} type="button" className="btn btn-link" disabled={disabled} aria-expanded={open} aria-haspopup="dialog"
        data-testid="say-outside" onClick={() => setOpen(!open)}>Change which photo shows the outside</button>
      {open && !disabled && (
        <Sheet title={one ? ONE_SIDE_QUESTION : OUTSIDE_QUESTION} popover keep={button} className="shoe-say-sheet"
          testId="say-outside-sheet" onClose={() => setOpen(false)}>
          <div className="shoe-ask-body">
            <p className="muted">{OUTSIDE_HINT}</p>
            <OutsideChoices photos={photos} disabled={busy} onSay={async (id, view) => {
              if (await say(id, view)) setOpen(false);
            }} />
          </div>
        </Sheet>
      )}
    </span>
  );
}

/** While Nines cannot tell the outside of the shoe from the inside (a logo or stripe on one side only), it asks: which
 * photo shows the outside, or, with one photo, whether it is the outside or the inside. */
function OutsideQuestion(props: Props) {
  const { item, disabled } = props;
  const { busy, say } = useSayView(props);
  const asked = outsideQuestion(item);
  if (!asked) return null;
  return (
    <div className="notice shoe-ask" role="group" aria-labelledby={`ask-${item.id}`} data-testid="shoe-ask">
      <div className="shoe-ask-body">
        {asked.one
          ? <p id={`ask-${item.id}`}><strong>{ONE_SIDE_QUESTION}</strong> {OUTSIDE_HINT}</p>
          : <p id={`ask-${item.id}`}><strong>{OUTSIDE_QUESTION}</strong> ({OUTSIDE_HINT})</p>}
        <OutsideChoices photos={asked.photos} disabled={disabled || busy} onSay={(id, view) => void say(id, view)} />
      </div>
    </div>
  );
}

/** A shoe's photos on its page: each with what it shows, the other photos with a way to remove them, "Add photos",
 * the question about the outside when Nines has to ask, and a word when no photo shows the shoe from the side. */
export function ShoePhotos(props: Props) {
  const { item, disabled, onSaved, onError } = props;
  const [busy, setBusy] = useState<string | null>(null);
  const views = item.views;
  const progress = useItemProgress(item);
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
      {(partWords(progress, 'views') ?? views.message) && (
        <p className="muted small" role="status">{partWords(progress, 'views') ?? views.message}</p>
      )}
      {noSidePhoto(item) && <p className="notice" data-testid="shoe-no-side">{NO_SIDE}</p>}
      <SayOutside {...props} />
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
