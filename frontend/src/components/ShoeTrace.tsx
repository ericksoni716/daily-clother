import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import { preparePhoto } from '../resize';
import { NUDGES, nudgeLabel, traceNotice } from '../shoe';
import type { Item, TraceFix } from '../types';
import { sha256 } from '../uploads';
import { CameraIcon, WarnIcon } from './Icons';
import './Shoe.css';

interface Props {
  item: Item;
  disabled: boolean;
  onSaved(item: Item, saidAs: string): void;
  onError(message: string): void;
}

/** A new photo of the shoe in place of its photo: the owner's camera (or library), then cut out, described and
 * traced again. */
export function RetakeButton({ item, disabled, onSaved, onError, primary = false }: Props & { primary?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const take = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      const [prepared, hash] = await Promise.all([preparePhoto(file), sha256(file).catch(() => null)]);
      onSaved(await api.replacePhoto(item.id, prepared.blob, prepared.filename, hash), 'New photo added; the shoe is traced again from it');
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

/** The item page's line about a shoe's trace: while it is traced, or why it is drawn from its details, with a
 * chance to retake the photo. */
export function TraceNotice(props: Props) {
  const said = traceNotice(props.item.trace);
  if (!said) return null;
  if (said.tone === 'info') return <p className="notice" role="status" data-testid="shoe-tracing">{said.text}</p>;
  return (
    <div className="notice notice-warn" data-testid="shoe-fallback">
      <WarnIcon />
      <div>
        <p>{said.text}</p>
        <div className="row">
          <RetakeButton {...props} primary />
        </div>
      </div>
    </div>
  );
}

/** One colour of the traced shoe: a colour picker, saved once the owner stops moving it. */
function PartColour({ title, color, own, busy, onPick, onReset }: {
  title: string; color: string; own: boolean; busy: boolean; onPick(color: string): void; onReset(): void;
}) {
  const [value, setValue] = useState(color);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => setValue(color), [color]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <li className="shoe-part">
      <label className="shoe-part-label">
        <input type="color" value={value} disabled={busy} aria-label={title === 'main colour' ? 'Main colour' : `Colour of the ${title}`} onChange={(e) => {
          const next = e.target.value;
          setValue(next);
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => onPick(next), 400);
        }} />
        <span>{title.charAt(0).toUpperCase() + title.slice(1)}{own && <span className="fix-own"> · set by you</span>}</span>
      </label>
      {own && <button type="button" className="btn btn-ghost btn-small" disabled={busy} onClick={onReset}>As traced</button>}
    </li>
  );
}

/** "Fix the details" for a shoe drawn from its photo: its colours, its marks, tracing it again, or the plain drawing. */
export function ShoeDrawingFix({ item, disabled, onSaved, onError }: Props) {
  const trace = item.trace;
  const [busy, setBusy] = useState(false);
  if (!trace) return null;
  const run = async (call: () => Promise<Item>, saidAs: string) => {
    setBusy(true);
    try {
      onSaved(await call(), saidAs);
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  const fix = (f: TraceFix, saidAs: string) => run(() => api.fixTrace(item.id, f), saidAs);
  const off = disabled || busy;
  const traced = trace.state === 'done';
  const working = trace.state === 'waiting' || trace.state === 'working';
  return (
    <section className="fix-group shoe-fix" aria-label="The shoe's drawing" data-testid="shoe-fix">
      <h3 className="chip-group-title">The shoe's drawing</h3>
      {traced && !trace.plain && <p className="muted small">Drawn from the side-on photo. Change a colour, remove or move a mark; your fixes stay when the shoe is traced again.</p>}
      {traced && trace.plain && <p className="muted small">You chose the plain drawing for this shoe, drawn from its details.</p>}
      {!traced && trace.message && <p className="muted small">{trace.message}</p>}
      {traced && !trace.plain && (
        <>
          {trace.parts.length > 0 && (
            <ul className="shoe-parts" aria-label="Colours">
              {trace.parts.map((p) => (
                <PartColour key={p.name} title={p.title} color={p.color} own={p.own} busy={off}
                  onPick={(c) => void fix({ part: p.name, color: c }, `Colour of the ${p.title} changed`)}
                  onReset={() => void fix({ part: p.name, color: null }, `The ${p.title} is back to its traced colour`)} />
              ))}
            </ul>
          )}
          {trace.marks.length > 0 && (
            <ul className="shoe-marks" aria-label="Marks">
              {trace.marks.map((m) => (
                <li key={m.index} className={`shoe-mark${m.hidden ? ' is-hidden' : ''}`}>
                  <span className="shoe-mark-swatch" style={{ background: m.color }} aria-hidden="true" />
                  <span className="shoe-mark-title">{m.title.charAt(0).toUpperCase() + m.title.slice(1)}{m.hidden ? ' (removed)' : ''}</span>
                  {!m.hidden && (
                    <span className="shoe-nudges" role="group" aria-label={`Move the ${m.title}`}>
                      {NUDGES.map((n) => (
                        <button key={n.dir} type="button" className="btn btn-small shoe-nudge" disabled={off}
                          aria-label={nudgeLabel(m.title, n.dir)} title={nudgeLabel(m.title, n.dir)}
                          onClick={() => void fix({ mark: m.index, nudge: n.step }, `Moved the ${m.title}`)}>{n.arrow}</button>
                      ))}
                    </span>
                  )}
                  <button type="button" className="btn btn-small" disabled={off}
                    onClick={() => void fix({ mark: m.index, hide: !m.hidden }, m.hidden ? `The ${m.title} is back` : `Removed the ${m.title}`)}>
                    {m.hidden ? 'Bring it back' : 'Remove'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <div className="row shoe-fix-actions">
        {!working && item.has_photo && (
          <button type="button" className="btn btn-small" disabled={off}
            onClick={() => void run(() => api.retrace(item.id), 'Tracing the shoe again')}>Re-trace</button>
        )}
        {traced && (
          <button type="button" className="btn btn-small" disabled={off}
            onClick={() => void run(() => api.setTracePlain(item.id, !trace.plain),
              trace.plain ? 'Drawn from its photo again' : 'Drawn plain, from its details')}>
            {trace.plain ? 'Use the traced drawing' : 'Use the plain drawing'}
          </button>
        )}
        {trace.fixed && traced && !trace.plain && (
          <button type="button" className="btn btn-ghost btn-small" disabled={off}
            onClick={() => void fix({ reset: true }, 'Your fixes to the drawing are undone')}>Undo my fixes</button>
        )}
        {(trace.state === 'refused' || trace.state === 'failed') && <RetakeButton item={item} disabled={disabled} onSaved={onSaved} onError={onError} />}
      </div>
    </section>
  );
}
