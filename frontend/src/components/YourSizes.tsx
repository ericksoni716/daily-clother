import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { api } from '../api';
import { writePart } from '../settings';
import { brandLine, sizesLine, suggestionLine } from '../sizes';
import type { SizeEntry, SizeKind, Sizes } from '../types';
import { Button, SaveStatus, Sheet, useSaveStatus } from './ui';

/**
 * Your sizes, in Settings under Everyday: one line saying the sizes saved, and Change, which opens a sheet with a short
 * box for each kind of piece, each saved as you leave it. A brand that fits differently is added behind one button.
 * "Find some" tells Claude the size for the wish's kind (`aboutyou.py`).
 */
export function YourSizes({ sizes, offline }: { sizes?: Sizes; offline: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className="settings-row">
        <p className="sizes-line" data-testid="sizes-line">{sizesLine(sizes)}</p>
        <Button small disabled={offline || !sizes} aria-expanded={open} aria-label={open ? undefined : 'Change your sizes'}
          onClick={() => setOpen(!open)}>{open ? 'Done' : 'Change'}</Button>
      </div>
      {open && sizes && (
        <Sheet title="Your sizes" onClose={() => setOpen(false)} testId="sizes-sheet">
          <SizesForm sizes={sizes} offline={offline} />
        </Sheet>
      )}
    </>
  );
}

function SizesForm({ sizes, offline }: { sizes: Sizes; offline: boolean }) {
  const [adding, setAdding] = useState(false);
  return (
    <div className="sizes">
      <p className="hint">Claude looks for these when it searches shops for a wish.</p>
      {sizes.kinds.map((entry) => <SizeBox key={entry.kind} entry={entry} max={sizes.max_size} offline={offline} />)}
      {adding
        ? <BrandForm sizes={sizes} offline={offline} onDone={() => setAdding(false)} />
        : <Button variant="ghost" small className="sizes-add" disabled={offline} onClick={() => setAdding(true)}>A brand that fits differently</Button>}
    </div>
  );
}

/** One kind: its box, saved when you leave it; the size most of your pieces carry, to use with a tap; its brands. */
function SizeBox({ entry, max, offline }: { entry: SizeEntry; max: number; offline: boolean }) {
  const qc = useQueryClient();
  const status = useSaveStatus();
  const [value, setValue] = useState(entry.size ?? '');
  const suggestion = suggestionLine(entry);
  const save = (run: () => Promise<Sizes>) => status.run(async () => writePart(qc, { sizes: await run() }));
  const keep = (size: string) => save(() => api.putSize(entry.kind, size.trim()));
  const id = `size-${entry.kind}`;
  return (
    <div className="sizes-kind" data-testid={id}>
      <div className="sizes-box">
        <div className="sizes-name">
          <label htmlFor={id}>{entry.label}</label>
          <SaveStatus state={status.state} onRetry={status.retry} />
        </div>
        <input id={id} value={value} maxLength={max} disabled={offline} autoComplete="off"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
          onBlur={() => { if (value.trim() !== (entry.size ?? '')) void keep(value); }} />
      </div>
      {suggestion && (
        <p className="hint">
          {suggestion}{' '}
          <Button variant="link" small disabled={offline} onClick={() => { setValue(entry.suggested!); void keep(entry.suggested!); }}>Use it</Button>
        </p>
      )}
      {entry.brands.map((b) => (
        <p key={b.brand} className="sizes-brand">
          {brandLine(b)}{' '}
          <Button variant="link" small disabled={offline} aria-label={`Remove ${b.brand}`}
            onClick={() => void save(() => api.putBrandSize(entry.kind, b.brand, ''))}>Remove</Button>
        </p>
      ))}
    </div>
  );
}

/** A brand whose size differs from your usual one for a kind: the kind, the brand and its size, with Save. */
function BrandForm({ sizes, offline, onDone }: { sizes: Sizes; offline: boolean; onDone(): void }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<SizeKind>(sizes.kinds[0].kind);
  const [brand, setBrand] = useState('');
  const [size, setSize] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // a kind with as many brands as are kept takes a new one only once one is removed (a brand already kept can change)
  const kept = sizes.kinds.find((k) => k.kind === kind)?.brands ?? [];
  const full = kept.length >= sizes.max_brands && !kept.some((b) => b.brand.toLowerCase() === brand.trim().toLowerCase());

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      writePart(qc, { sizes: await api.putBrandSize(kind, brand.trim(), size.trim()) });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="sizes-brand-form" onSubmit={(e) => void submit(e)} data-testid="brand-size-form">
      <label className="field">
        <span>Kind</span>
        <select value={kind} disabled={offline || busy} onChange={(e) => setKind(e.target.value as SizeKind)}>
          {sizes.kinds.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
        </select>
      </label>
      <label className="field">
        <span>Brand</span>
        <input value={brand} maxLength={sizes.max_brand} disabled={offline || busy} autoComplete="off" onChange={(e) => setBrand(e.target.value)} />
      </label>
      <label className="field">
        <span>Your size in it</span>
        <input value={size} maxLength={sizes.max_size} disabled={offline || busy} autoComplete="off" onChange={(e) => setSize(e.target.value)} />
      </label>
      {full && <p className="hint">You have {sizes.max_brands} brands for this kind already; remove one first.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="row">
        <Button type="submit" variant="primary" small disabled={offline || busy || !brand.trim() || !size.trim() || full}>Save</Button>
        <Button variant="ghost" small disabled={busy} onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}
