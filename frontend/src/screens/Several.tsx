import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { api, ApiError } from '../api';
import { CheckIcon, ImagesIcon } from '../components/Icons';
import { Button, Card, Failed, ItemThumb, Notice, PageHeader } from '../components/ui';
import { Link, navigate } from '../router';
import {
  addLabel, boxStyle, CORNERS, cropStyle, differsFromFound, foundVersion, moveBox, moveCorner, newBox, pieceName, pointAt, putBack,
  remember, removedFound, sameBox, sourcePoll, type Corner, type Undo,
} from '../several';
import { touch } from '../queries';
import { queryKeys } from '../queryKeys';
import { useApp } from '../store';
import type { BoxEdges, PlainBox, SourceBox, SourcePhoto } from '../types';
import './Several.css';

const NUDGE = 0.01;   // an arrow key moves the chosen box this much of the photo

type Drag = { id: string; mode: Corner | 'move'; start: BoxEdges; from: { x: number; y: number }; pointerId: number };

const edges = (b: BoxEdges): BoxEdges => ({ x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1 });

/** Checking the boxes around the pieces in a photo of several, then adding each piece as an item. */
export function SeveralScreen({ id }: { id: string }) {
  const { toast, offline } = useApp();
  const qc = useQueryClient();
  const key = queryKeys.source(id);
  // Asked again every few seconds while Claude looks for the pieces, never while the page is hidden.
  const query = useQuery({ queryKey: key, queryFn: () => api.source(id), refetchInterval: (q) => sourcePoll(q.state.data) });
  const src = query.data ?? null;
  const error = query.error ? query.error.message : null;
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ id: string; box: BoxEdges } | null>(null);
  const [busy, setBusy] = useState(false);
  // the changes made on this page, newest last, each with the boxes as they were before it (kept until the pieces
  // are added or the page is left)
  const [undos, setUndos] = useState<Undo[]>([]);
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const finding = src?.state === 'finding';

  /** The photo as a change to its boxes left it: put in as it came back, and Add's list of photos (not on screen, so
   * not asked for now) made stale. The boxes change nothing else, so nothing else is asked for again. */
  const boxesSaved = (next: SourcePhoto) => {
    void qc.cancelQueries({ queryKey: key, exact: true });   // a poll from before the change must not undo it
    qc.setQueryData(key, next);
    void qc.invalidateQueries({ queryKey: queryKeys.sources(), exact: true });
  };

  /** Runs a change to the boxes; the photo as it is afterwards comes back. `words` say what it was, for Undo; an undo
   * itself passes none. */
  async function change(run: () => Promise<SourcePhoto>, words: string | null): Promise<boolean> {
    const before = src?.boxes ?? [];
    setBusy(true);
    try {
      boxesSaved(await run());
      if (words) setUndos((stack) => remember(stack, before, words));
      return true;
    } catch (e) {
      toast((e as ApiError).message, 'error');
      void query.refetch();
      return false;
    } finally {
      setBusy(false);
    }
  }

  function begin(e: PointerEvent<HTMLElement>, b: SourceBox, mode: Corner | 'move') {
    if (!stage.current || busy || src?.state === 'added') return;
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    drag.current = { id: b.id, mode, start: edges(b), from: pointAt(e.clientX, e.clientY, stage.current.getBoundingClientRect()), pointerId: e.pointerId };
    setDraft({ id: b.id, box: edges(b) });
  }

  function onMove(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || d.pointerId !== e.pointerId || !stage.current) return;
    const p = pointAt(e.clientX, e.clientY, stage.current.getBoundingClientRect());
    const box = d.mode === 'move' ? moveBox(d.start, p.x - d.from.x, p.y - d.from.y) : moveCorner(d.start, d.mode, p.x, p.y);
    setDraft({ id: d.id, box });
  }

  function onUp(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || d.pointerId !== e.pointerId) return;
    drag.current = null;
    const box = draft?.id === d.id ? draft.box : d.start;
    if (sameBox(box, d.start)) {
      setDraft(null);
      return;
    }
    const moved = src?.boxes.find((b) => b.id === d.id);
    const words = `${d.mode === 'move' ? 'Moved' : 'Changed the shape of'} ${moved ? pieceName(moved) : 'the box'}.`;
    void change(() => api.moveBox(id, d.id, box), words).finally(() => setDraft(null));
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>, b: SourceBox) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setSelected(b.id);
      return;
    }
    const step = { ArrowLeft: [-NUDGE, 0], ArrowRight: [NUDGE, 0], ArrowUp: [0, -NUDGE], ArrowDown: [0, NUDGE] }[e.key];
    if (!step || selected !== b.id || busy) return;
    e.preventDefault();
    // Shift and an arrow makes the box bigger or smaller from its lower right corner; an arrow alone moves it
    const box = e.shiftKey ? moveCorner(b, 'se', b.x1 + step[0], b.y1 + step[1]) : moveBox(b, step[0], step[1]);
    if (!sameBox(box, b)) void change(() => api.moveBox(id, b.id, box), `${e.shiftKey ? 'Changed the shape of' : 'Moved'} ${pieceName(b)}.`);
  }

  /** The last change taken back: the boxes as they were before it are sent whole. */
  function undo() {
    const last = undos[undos.length - 1];
    if (!last) return;
    void change(() => api.setBoxes(id, last.before), null).then((done) => done && setUndos((stack) => stack.slice(0, -1)));
  }

  function putBackOne(box: PlainBox & { n?: number }) {
    if (!src) return;
    void change(() => api.setBoxes(id, putBack(src.boxes, src.found_boxes, box.id)), `Put ${pieceName(box)} back as Claude found it.`);
  }

  function backToFound() {
    if (!src) return;
    void change(() => api.setBoxes(id, src.found_boxes), 'Went back to the boxes Claude found.');
  }

  async function addAll() {
    if (!src) return;
    setBusy(true);
    try {
      const done = await api.addSourceItems(id);
      void qc.cancelQueries({ queryKey: key, exact: true });
      qc.setQueryData(key, done);
      await touch(qc, 'source', ['source']);   // the new items are in the closet's list before it opens
      const n = done.items.length;
      toast(`${n === 1 ? 'The item was' : `${n} items were`} added. Nines cuts ${n === 1 ? 'it' : 'each'} out and describes ${n === 1 ? 'it' : 'them'} next.`);
      navigate('/');
    } catch (e) {
      toast((e as ApiError).message, 'error');
      void query.refetch();
      setBusy(false);
    }
  }

  async function forget() {
    if (!window.confirm('Forget this photo? Nothing is added from it.')) return;
    setBusy(true);
    try {
      await api.forgetSource(id);
      // forgotten: not asked for again, and Add's list of photos is stale
      qc.removeQueries({ queryKey: key, exact: true });
      void touch(qc, 'source', ['source']);
      navigate('/add');
    } catch (e) {
      toast((e as ApiError).message, 'error');
      setBusy(false);
    }
  }

  const header = <PageHeader title="Check the pieces" titleId="several-title" back={{ to: '/add', label: 'Add clothes' }} />;
  if (error && !src) {
    return (
      <section className="several" aria-labelledby="several-title">
        {header}
        <Failed query={query} what="this photo's pieces" testId="several-error" />
      </section>
    );
  }
  if (!src) {
    return (
      <section className="several" aria-labelledby="several-title">
        {header}
        <p className="muted"><span className="spinner" aria-hidden="true" /> Opening the photo…</p>
      </section>
    );
  }

  const added = src.state === 'added';
  const boxes = src.boxes.map((b) => (draft?.id === b.id ? { ...b, ...draft.box } : b));
  const editable = !added && !(finding && !src.note);
  const count = src.boxes.length;
  const removed = editable ? removedFound(src.boxes, src.found_boxes) : [];
  const lastChange = editable ? undos[undos.length - 1] : undefined;

  return (
    <section className="several" aria-labelledby="several-title">
      {header}

      {finding && !src.note && (
        <Notice testId="several-finding" role="status">
          <span className="spinner" aria-hidden="true" /> Claude is looking for each piece in this photo. This takes a few seconds.
        </Notice>
      )}
      {finding && src.note && (
        <Notice tone="warning" testId="several-note"
          action={<Button small onClick={() => void change(() => api.addBox(id, newBox()), 'Added a box.')} disabled={busy}>Draw them myself</Button>}>
          {src.note}
        </Notice>
      )}
      {!finding && !added && src.note && <Notice testId="several-note">{src.note}</Notice>}
      {added && (
        <Notice testId="several-added" icon={<CheckIcon />}
          action={<Link to="/" className="btn btn-small btn-primary">See them in your closet</Link>}>
          These pieces are in your closet.
        </Notice>
      )}
      {!finding && !added && count > 0 && (
        <p className="muted several-intro">
          Each numbered box becomes one item. Remove a box that isn't a piece of clothing, join two boxes that are one
          piece, and drag a box's corners to fit it. A suit's jacket and trousers stay two items.
        </p>
      )}

      <div className="several-layout">
        <div className="several-photo">
          <div ref={stage} className="several-stage" style={{ aspectRatio: `${src.width} / ${src.height}` }}
            onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
            onPointerDown={() => setSelected(null)} data-testid="several-stage">
            <img src={src.photo_url} alt="The photo of several pieces" draggable={false} />
            {boxes.map((b) => {
              const on = selected === b.id && editable;
              return (
                <div key={b.id} className={`several-box${on ? ' is-on' : ''}`} style={boxStyle(b)}
                  role="button" tabIndex={editable ? 0 : -1} aria-pressed={on}
                  aria-label={`Box ${b.n}${b.label ? `: ${b.label}` : ''}`} data-testid="several-box"
                  onPointerDown={(e) => {
                    if (!editable) return;
                    if (on) begin(e, b, 'move');
                    else {
                      e.stopPropagation();
                      setSelected(b.id);
                    }
                  }}
                  onKeyDown={(e) => editable && onKey(e, b)}>
                  <span className="several-num" aria-hidden="true">{b.n}</span>
                  {on && CORNERS.map((c) => (
                    <span key={c} className={`several-handle several-handle-${c}`} data-testid={`handle-${c}`}
                      aria-hidden="true" onPointerDown={(e) => begin(e, b, c)} />
                  ))}
                </div>
              );
            })}
          </div>
          {editable && count > 0 && (
            <p className="muted small several-hint">Tap a box to choose it, then drag it or its corners. With a keyboard, the arrow keys move the chosen box and Shift with an arrow changes its size.</p>
          )}
        </div>

        <div className="several-side">
          {added ? (
            <ul className="several-items" aria-label="Items added from this photo">
              {src.items.map((it) => <li key={it.id}><ItemThumb item={it} to={`/item/${encodeURIComponent(it.id)}`} title={it.name ?? 'New item'} /></li>)}
            </ul>
          ) : (
            <ol className="several-list" aria-label="The pieces">
              {boxes.map((b) => (
                <Piece key={b.id} box={b} src={src} chosen={selected === b.id} editable={editable} busy={busy}
                  others={boxes.filter((o) => o.id !== b.id)}
                  changed={editable && foundVersion(b, src.found_boxes) !== null}
                  onChoose={() => setSelected(b.id)}
                  onRemove={() => void change(() => api.removeBox(id, b.id), `Removed ${pieceName(b)}.`)}
                  onJoin={(other) => {
                    const partner = boxes.find((o) => o.id === other);
                    void change(() => api.mergeBoxes(id, [b.id, other]), `Joined ${pieceName(b)} and ${partner ? pieceName(partner) : 'another box'}.`);
                  }}
                  onPutBack={() => putBackOne(b)} />
              ))}
            </ol>
          )}

          {removed.length > 0 && (
            <div className="several-removed" data-testid="several-removed">
              <p className="muted small">Claude also found {removed.length === 1 ? 'this piece, which you removed' : 'these pieces, which you removed'}:</p>
              <ul>
                {removed.map((r) => (
                  <li key={r.id}>
                    <span>{r.label ?? 'A piece'}</span>{' '}
                    <Button small variant="link" disabled={busy} onClick={() => putBackOne(r)}
                      aria-label={`Put back ${r.label ?? 'the piece'} as Claude found it`}>Put back</Button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {lastChange && (
            <p className="several-undo" role="status" data-testid="several-undo">
              <span>{lastChange.words}</span>{' '}
              <Button small onClick={undo} disabled={busy}>Undo</Button>
            </p>
          )}

          {!added && (
            <div className="several-actions">
              {editable && (
                <Button onClick={() => void change(async () => {
                  const next = await api.addBox(id, newBox());
                  setSelected(next.boxes[next.boxes.length - 1]?.id ?? null);
                  return next;
                }, 'Added a box.')} disabled={busy || offline || count >= 20}>Add a box</Button>
              )}
              {editable && differsFromFound(src.boxes, src.found_boxes) && (
                <Button onClick={backToFound} disabled={busy || offline}>Back to what Claude found</Button>
              )}
              <Button variant="primary" onClick={() => void addAll()} disabled={busy || offline || !count || finding}
                data-testid="several-add">{count ? addLabel(count) : 'Add the items'}</Button>
              <Button variant="danger-quiet" onClick={() => void forget()} disabled={busy}>Forget this photo</Button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Piece({ box, src, chosen, editable, busy, others, changed, onChoose, onRemove, onJoin, onPutBack }: {
  box: SourceBox; src: SourcePhoto; chosen: boolean; editable: boolean; busy: boolean; others: SourceBox[];
  /** Claude found this box, and it has been moved, reshaped or joined since. */
  changed: boolean;
  onChoose(): void; onRemove(): void; onJoin(other: string): void; onPutBack(): void;
}) {
  return (
    <Card as="li" className={`several-piece${chosen ? ' is-on' : ''}`} data-testid="several-piece">
      <button type="button" className="several-pic" onClick={onChoose} aria-label={`Choose box ${box.n}`}>
        <Cutout box={box} src={src} />
      </button>
      <div className="several-piece-info">
        <p className="several-piece-name"><span className="several-badge">{box.n}</span> {box.label ?? 'A piece you marked'}</p>
        {editable && (
          <div className="row several-piece-actions">
            <Button small variant="danger-quiet" onClick={onRemove} disabled={busy} aria-label={`Remove box ${box.n}`}>Remove</Button>
            {changed && (
              <Button small variant="link" onClick={onPutBack} disabled={busy}
                aria-label={`Put box ${box.n} back as Claude found it`}>As Claude found it</Button>
            )}
            {others.length > 0 && (
              <select className="several-join" aria-label={`Join box ${box.n} with another`} value="" disabled={busy}
                onChange={(e) => e.target.value && onJoin(e.target.value)}>
                <option value="">Join with…</option>
                {others.map((o) => <option key={o.id} value={o.id}>Box {o.n}{o.label ? ` (${o.label})` : ''}</option>)}
              </select>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

/** The piece cut out of its background; while that can't be made (the model is still being set up), the box's part
 * of the photo. */
function Cutout({ box, src }: { box: SourceBox; src: SourcePhoto }) {
  const [broken, setBroken] = useState<string | null>(null);
  if (broken !== box.cutout_url) {
    return <img className="several-cut" src={box.cutout_url} alt="" loading="lazy" onError={() => setBroken(box.cutout_url)} />;
  }
  const crop = cropStyle(box, src.width, src.height);
  return (
    <span className="several-crop" style={crop.frame}>
      {src.photo_url ? <img src={src.photo_url} alt="" style={crop.img} /> : <ImagesIcon />}
    </span>
  );
}
