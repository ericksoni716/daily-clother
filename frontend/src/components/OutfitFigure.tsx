import { useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import { figurePieces, svgSource } from '../figure';
import type { OutfitPieces } from '../today';
import { HangerIcon } from './Icons';

/** One outfit drawn as worn, front view, from the server. `version` changes when any piece's drawing does. */
export function OutfitFigure({ pieces, version, alt }: { pieces: OutfitPieces; version: string; alt: string }) {
  const asked = JSON.stringify(figurePieces(pieces));
  const [got, setGot] = useState<{ asked: string; version: string; src: string | null; error: string | null } | null>(null);
  useEffect(() => {
    const stop = new AbortController();
    api.outfitFigure(JSON.parse(asked), stop.signal)
      .then((svg) => setGot({ asked, version, src: svgSource(svg), error: null }))
      .catch((e) => {
        if ((e as Error)?.name === 'AbortError') return;
        const message = e instanceof ApiError && e.status === 0
          ? 'The drawing of the outfit needs the closet program running. The pieces are still there.'
          : 'This outfit could not be drawn as worn. The pieces are still there.';
        setGot({ asked, version, src: null, error: message });
      });
    return () => stop.abort();
  }, [asked, version]);
  const ready = got && got.asked === asked && got.version === version ? got : null;
  return (
    <figure className="today-figure" data-testid="outfit-figure" aria-busy={!ready}>
      {ready?.src ? (
        <img src={ready.src} alt={alt} />
      ) : ready?.error ? (
        <p className="muted today-figure-note">{ready.error}</p>
      ) : (
        <span className="pic-placeholder" role="img" aria-label="Drawing the outfit"><HangerIcon /></span>
      )}
    </figure>
  );
}
