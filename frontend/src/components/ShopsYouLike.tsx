import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { api } from '../api';
import { writePart } from '../settings';
import { SHOPS_HINT, shopsLine } from '../picks';
import type { Shops } from '../types';
import { Button, SaveStatus, Sheet, useSaveStatus } from './ui';

/**
 * Shops you like, in Settings under Everyday: one line naming them, and Change, which opens a sheet with a box to add
 * one and Remove beside each, saved as you go. A look for things on sale starts at these (`shops.py`). The card's
 * empty On sale view links here with `?open=shops`, which opens the sheet.
 */
export function ShopsYouLike({ shops, offline }: { shops?: Shops; offline: boolean }) {
  const [open, setOpen] = useState(() => {
    try {
      return new URLSearchParams(window.location.search).get('open') === 'shops';
    } catch {
      return false;
    }
  });
  return (
    <>
      <div className="settings-row">
        <p className="sizes-line" data-testid="shops-line">{shopsLine(shops)}</p>
        <Button small disabled={offline || !shops} aria-expanded={open} aria-label={open ? undefined : 'Change the shops you like'}
          onClick={() => setOpen(!open)}>{open ? 'Done' : 'Change'}</Button>
      </div>
      {open && shops && (
        <Sheet title="Shops you like" onClose={() => setOpen(false)} testId="shops-sheet">
          <ShopsForm shops={shops} offline={offline} />
        </Sheet>
      )}
    </>
  );
}

function ShopsForm({ shops, offline }: { shops: Shops; offline: boolean }) {
  const qc = useQueryClient();
  const status = useSaveStatus();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const full = shops.shops.length >= shops.max_shops;

  /** Saves one change; the server's sentence is shown when it does not take it (a shop kept already, the list full). */
  async function save(run: () => Promise<Shops>): Promise<boolean> {
    setError(null);
    return status.run(async () => {
      try {
        writePart(qc, { shops: await run() });
      } catch (e) {
        setError((e as Error).message);
        throw e;
      }
    });
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    if (await save(() => api.addShop(name.trim()))) setName('');
  }

  return (
    <div className="sizes shops">
      <p className="hint">{SHOPS_HINT}</p>
      {shops.shops.length > 0 && (
        <ul className="shops-list" aria-label="Shops you like">
          {shops.shops.map((s) => (
            <li key={s.id} className="shops-item">
              <span>{s.name}</span>
              <Button variant="link" small disabled={offline} aria-label={`Remove ${s.name}`}
                onClick={() => void save(() => api.removeShop(s.id))}>Remove</Button>
            </li>
          ))}
        </ul>
      )}
      <form className="sizes-box" onSubmit={(e) => void add(e)} data-testid="shops-add">
        <label htmlFor="shop-name" className="visually-hidden">A shop's name or site</label>
        <input id="shop-name" value={name} maxLength={shops.max_name} disabled={offline || full} autoComplete="off"
          placeholder="A shop's name or site" onChange={(e) => setName(e.target.value)} />
        <Button type="submit" small disabled={offline || full || !name.trim()}>Add</Button>
      </form>
      {full && <p className="hint">You have {shops.max_shops} shops already; remove one to add another.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <SaveStatus state={status.state} onRetry={status.retry} />
    </div>
  );
}
