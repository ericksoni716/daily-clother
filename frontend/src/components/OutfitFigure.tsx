import { keepPreviousData, queryOptions, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { api, ApiError } from '../api';
import { dressingSteps, figurePieces, frameOf, placeIn, svgSource, type FigurePieces } from '../figure';
import { queryKeys } from '../queryKeys';
import type { OutfitPieces } from '../today';
import { HangerIcon } from './Icons';

/** One drawing in the figure: the outfit up to one layer, placed in the outfit's own frame (null: it fills it). */
interface Layer { src: string; place: CSSProperties | null }

/** The figure as drawn: its layers, the outfit itself last, and its shape (width over height, when known). */
interface Drawn { layers: Layer[]; ratio: number | null }

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
async function under(steps: FigurePieces[], whole: [number, number, number, number]): Promise<Layer[]> {
  const svgs = await Promise.all(steps.map((s) => api.outfitFigure(s).catch(() => null)));
  const layers: Layer[] = [];
  for (const svg of svgs) {
    const frame = svg ? frameOf(svg) : null;
    if (!svg || !frame) return [];
    layers.push({ src: svgSource(svg), place: placeIn(frame, whole) });
  }
  return layers;
}

/** The outfit itself first, then (`layered`) the layers under it; each decoded, so a layer never appears late. */
async function draw(outfit: FigurePieces, layered: boolean): Promise<Drawn> {
  const svg = await api.outfitFigure(outfit);
  const whole = frameOf(svg);
  const steps = layered ? dressingSteps(outfit).slice(0, -1) : [];
  const layers = whole && steps.length ? await under(steps, whole) : [];
  const all = [...layers, { src: svgSource(svg), place: null }];
  await Promise.all(all.map((l) => decoded(l.src)));
  return { layers: all, ratio: whole ? whole[2] / whole[3] : null };
}

/**
 * A figure is the same for as long as its pieces' drawings are (`version` is in its key), so once drawn it is kept and
 * never asked for again: switching to As worn and back, or coming back to the screen, shows it at once. A request on
 * its way is not called off when the figure leaves the screen, so its answer is kept for next time.
 */
export const figureQuery = (outfit: FigurePieces, version: string, layered: boolean) => queryOptions({
  queryKey: queryKeys.figure(outfit, version, layered),
  queryFn: () => draw(outfit, layered),
  staleTime: Infinity,
});

/** What is said in place of the figure when it cannot be drawn. */
export function figureError(e: unknown): string {
  return e instanceof ApiError && e.status === 0
    ? 'The drawing of the outfit needs the closet program running. The pieces are still there.'
    : 'This outfit could not be drawn as worn. The pieces are still there.';
}

/**
 * One outfit drawn as worn, front view, from the server. `version` changes when any piece's drawing does; the figure
 * drawn before stays on screen while the new one is drawn. With `dress`, it is dressed a layer at a time once it is in
 * sight (each layer fading in over the last), unless the device asks for less motion: Today keeps its outfits side by
 * side, and one is dressed when it is swiped to.
 */
export function OutfitFigure({ pieces, version, alt, dress = false }: { pieces: OutfitPieces; version: string; alt: string; dress?: boolean }) {
  const outfit = useMemo(() => figurePieces(pieces), [pieces]);
  const layered = dress && !lessMotion();
  const figure = useQuery({ ...figureQuery(outfit, version, layered), placeholderData: keepPreviousData });
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
  const ready = figure.data ?? null;
  const last = ready ? ready.layers.length - 1 : -1;
  return (
    <figure ref={box} className="today-figure" data-testid="outfit-figure" aria-busy={!ready || figure.isPlaceholderData}>
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
      ) : figure.error ? (
        <p className="muted today-figure-note">{figureError(figure.error)}</p>
      ) : (
        <span className="pic-placeholder" role="img" aria-label="Drawing the outfit"><HangerIcon /></span>
      )}
    </figure>
  );
}
