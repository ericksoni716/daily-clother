import { useRef, useState } from 'react';
import { api, ApiError } from '../api';
import { preparePhoto } from '../resize';
import type { Item } from '../types';
import { sha256 } from '../uploads';
import { CameraIcon } from './Icons';

/** "Retake the photo": the owner's camera (or library), and the new photo in place of the item's main one. It is
 * shrunk and hashed as on Add (a photo already in the closet as another item is refused). `said` is the line shown
 * once it is in: what happens next (a shoe is traced again; clothes are described and measured again). */
export function RetakeButton({ item, disabled, onSaved, onError, said, primary = false }: {
  item: Item;
  disabled: boolean;
  onSaved(item: Item, saidAs: string): void;
  onError(message: string): void;
  said: string;
  primary?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const take = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      const [prepared, hash] = await Promise.all([preparePhoto(file), sha256(file).catch(() => null)]);
      onSaved(await api.replacePhoto(item.id, prepared.blob, prepared.filename, hash), said);
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <input ref={input} className="visually-hidden" type="file" accept="image/*" capture="environment" tabIndex={-1}
        aria-hidden="true" data-testid="retake-input" onChange={(e) => { void take(e.target.files?.[0]); e.target.value = ''; }} />
      <button type="button" className={`btn btn-small${primary ? ' btn-primary' : ''}`} disabled={disabled || busy}
        onClick={() => input.current?.click()}>
        <CameraIcon />{busy ? 'Sending the photo…' : 'Retake the photo'}
      </button>
    </>
  );
}
