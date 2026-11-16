import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { api, ApiError } from '../api';
import { dressingSteps, figurePieces, frameOf, placeIn, svgSource, type FigurePieces } from '../figure';
import type { OutfitPieces } from '../today';
import { HangerIcon } from './Icons';

/** One drawing in the figure: the outfit up to one layer, placed in the outfit's own frame (null: it fills it). */
interface Layer { src: string; place: CSSProperties | null }

interface Got { asked: string; version: string; layers: Layer[]; ratio: number | null; error: string | null }

function lessMotion(): boolean {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

/** Ready to show, so a layer never appears late in the middle of the others. */
function decoded(src: string): Promise<void> {
  if (typeof Image === 'undefined') return Promise.resolve();
  const img = new Image();
  img.src = src;
  return typeof img.decode === 'function' ? img.decode().catch(() => undefined) : Promise.resolve();
}

/**
 * The layers under the outfit, each drawn by the server; none when one of them cannot be had (the outfit is then shown
 * at once, as it is without the dressing).
 */
async function under(steps: FigurePieces[], whole: [number, number, number, number], signal: AbortSignal): Promise<Layer[]> {
  const svgs = await Promise.all(steps.map((s) => api.outfitFigure(s, signal).catch(() => null)));
  const layers: Layer[] = [];
  for (const svg of svgs) {
    const frame = svg ? frameOf(svg) : null;
    if (!svg || !frame) return [];
    layers.push({ src: svgSource(svg), place: placeIn(frame, whole) });
  }
  return layers;
}

/**
 * One outfit drawn as worn, front view, from the server. `version` changes when any piece's drawing does. With
 * `dress`, it is dressed a layer at a time once it is in sight (each layer fading in over the last), unless the device
 * asks for less motion: Today keeps its outfits side by side, and one is dressed when it is swiped to.
 */
export function OutfitFigure({ pieces, version, alt, dress = false }: { pieces: OutfitPieces; version: string; alt: string; dress?: boolean }) {
  const asked = JSON.stringify(figurePieces(pieces));
  const [got, setGot] = useState<Got | null>(null);
  const box = useRef<HTMLElement>(null);
  const [inSight, setInSight] = useState(() => typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    const el = box.current;
    if (!dress || inSight || !el) return;
    const watch = new IntersectionObserver((seen) => {
      if (seen.some((e) => e.isIntersecting)) setInSight(true);
    }, { threshold: 0.5 });
    watch.observe(el);
    return () => watch.disconnect();
  }, [dress, inSight]);
  useEffect(() => {
    const stop = new AbortController();
    const outfit: FigurePieces = JSON.parse(asked);
    const steps = dress && !lessMotion() ? dressingSteps(outfit).slice(0, -1) : [];
    api.outfitFigure(outfit, stop.signal)   // the outfit itself first, then the layers under it
      .then(async (svg) => {
        const whole = frameOf(svg);
        const layers = whole && steps.length ? await under(steps, whole, stop.signal) : [];
        const all = [...layers, { src: svgSource(svg), place: null }];
        await Promise.all(all.map((l) => decoded(l.src)));
        if (stop.signal.aborted) return;
        setGot({ asked, version, layers: all, ratio: whole ? whole[2] / whole[3] : null, error: null });
      })
      .catch((e) => {
        if ((e as Error)?.name === 'AbortError') return;
        const message = e instanceof ApiError && e.status === 0
          ? 'The drawing of the outfit needs the closet program running. The pieces are still there.'
          : 'This outfit could not be drawn as worn. The pieces are still there.';
        setGot({ asked, version, layers: [], ratio: null, error: message });
      });
    return () => stop.abort();
  }, [asked, version, dress]);
  const ready = got && got.asked === asked && got.version === version ? got : null;
  const last = ready ? ready.layers.length - 1 : -1;
  return (
    <figure ref={box} className="today-figure" data-testid="outfit-figure" aria-busy={!ready}>
      {ready && last >= 0 && dress && ready.ratio ? (
        <span className={inSight ? 'figure-stack is-in-sight' : 'figure-stack'}
          style={{ aspectRatio: ready.ratio.toFixed(4), width: `min(100%, calc(var(--figure-h) * ${ready.ratio.toFixed(4)}))` }}>
          {ready.layers.map((l, i) => (
            <img key={i} src={l.src} alt={i === last ? alt : ''} aria-hidden={i === last ? undefined : true}
              style={{ ...l.place, animationDelay: `calc(${i} * var(--dur-move))` }} />
          ))}
        </span>
      ) : ready && last >= 0 ? (
        <img src={ready.layers[last].src} alt={alt} />
      ) : ready?.error ? (
        <p className="muted today-figure-note">{ready.error}</p>
      ) : (
        <span className="pic-placeholder" role="img" aria-label="Drawing the outfit"><HangerIcon /></span>
      )}
    </figure>
  );
}
