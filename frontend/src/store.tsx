import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, connection } from './api';
import type { ItemSummary, ModelInfo, Profile, Vocab } from './types';
import { uploads } from './uploads';

type Status = 'active' | 'archived';

interface ClosetState {
  profile: Profile;
  offline: boolean;
  vocab: Vocab | null;
  model: ModelInfo | null;
  items: Record<Status, ItemSummary[] | null>;
  loadError: string | null;
  loadItems(status: Status): Promise<void>;
  refreshModel(): Promise<void>;
  /** Put a changed item into the lists (moving it if its status changed). */
  upsert(item: ItemSummary): void;
  drop(id: string): void;
  switchProfile(profile: Profile): Promise<void>;
  logout(): Promise<void>;
  quit(): Promise<void>;
  toast(message: string, kind?: 'ok' | 'error'): void;
}

const Ctx = createContext<ClosetState | null>(null);

export function useCloset(): ClosetState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useCloset outside ClosetProvider');
  return v;
}

export function useOffline(): boolean {
  const [off, setOff] = useState(connection.offline);
  useEffect(() => {
    setOff(connection.offline);
    const unsub = connection.subscribe(setOff);
    return () => {
      unsub();
    };
  }, []);
  return off;
}

const busy = (i: ItemSummary) => i.cutout_state === 'pending' || i.cutout_state === 'processing';

interface Props {
  profile: Profile;
  onProfile(profile: Profile): void;
  onLogout(): Promise<void>;
  onQuit(): Promise<void>;
  toast(message: string, kind?: 'ok' | 'error'): void;
  children: ReactNode;
}

export function ClosetProvider({ profile, onProfile, onLogout, onQuit, toast, children }: Props) {
  const offline = useOffline();
  const [vocab, setVocab] = useState<Vocab | null>(null);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [items, setItems] = useState<Record<Status, ItemSummary[] | null>>({ active: null, archived: null });
  const [loadError, setLoadError] = useState<string | null>(null);
  const generation = useRef(0);

  const loadItems = useCallback(async (status: Status) => {
    const gen = generation.current;
    try {
      const list = await api.items(status);
      if (gen !== generation.current) return;
      setItems((prev) => ({ ...prev, [status]: list }));
      setLoadError(null);
    } catch (e) {
      if (gen !== generation.current) return;
      setLoadError((e as Error).message);
    }
  }, []);

  const refreshModel = useCallback(async () => {
    try {
      setModel(await api.model());
    } catch {
      /* not saved offline; keep what we had */
    }
  }, []);

  const loadAll = useCallback(() => {
    api.vocab().then(setVocab).catch(() => undefined);
    void loadItems('active');
    void refreshModel();
  }, [loadItems, refreshModel]);

  useEffect(() => {
    loadAll();
  }, [loadAll, profile]);

  // Back online: fetch fresh data. While offline, check the server every few seconds.
  const wasOffline = useRef(offline);
  useEffect(() => {
    if (wasOffline.current && !offline) loadAll();
    wasOffline.current = offline;
    if (!offline) return;
    const t = window.setInterval(() => {
      api.session().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(t);
  }, [offline, loadAll]);

  // Poll while cutouts are being made.
  // Every 2 s while the model can work on them; slower while it is missing or failed,
  // since nothing changes until it is downloaded (the model state is still followed).
  const anyBusy = (items.active ?? []).some(busy) || (items.archived ?? []).some(busy);
  const modelStuck = model?.state === 'missing' || model?.state === 'failed';
  useEffect(() => {
    if (!anyBusy || offline) return;
    const t = window.setInterval(() => {
      void loadItems('active');
      void refreshModel();
    }, modelStuck ? 10_000 : 2000);
    return () => window.clearInterval(t);
  }, [anyBusy, offline, modelStuck, loadItems, refreshModel]);

  // Poll the model while it downloads.
  useEffect(() => {
    if (model?.state !== 'downloading' || offline) return;
    const t = window.setInterval(() => void refreshModel(), 1500);
    return () => window.clearInterval(t);
  }, [model?.state, offline, refreshModel]);

  // A finished upload shows up in the grid straight away.
  useEffect(() => {
    let done = uploads.snapshot.filter((e) => e.status === 'done').length;
    return uploads.subscribe((entries) => {
      const now = entries.filter((e) => e.status === 'done').length;
      if (now > done) void loadItems('active');
      done = now;
    });
  }, [loadItems]);

  const upsert = useCallback((item: ItemSummary) => {
    setItems((prev) => {
      const next = { ...prev };
      for (const s of ['active', 'archived'] as Status[]) {
        const list = prev[s];
        if (!list) continue;
        const has = list.some((x) => x.id === item.id);
        if (item.status === s) {
          next[s] = has ? list.map((x) => (x.id === item.id ? { ...x, ...pickSummary(item) } : x)) : [pickSummary(item), ...list];
        } else if (has) {
          next[s] = list.filter((x) => x.id !== item.id);
        }
      }
      return next;
    });
  }, []);

  const drop = useCallback((id: string) => {
    setItems((prev) => ({
      active: prev.active?.filter((x) => x.id !== id) ?? null,
      archived: prev.archived?.filter((x) => x.id !== id) ?? null,
    }));
  }, []);

  const switchProfile = useCallback(async (p: Profile) => {
    await api.setProfile(p);
    generation.current++;
    setItems({ active: null, archived: null });
    onProfile(p);
  }, [onProfile]);

  const value = useMemo<ClosetState>(() => ({
    profile, offline, vocab, model, items, loadError, loadItems, refreshModel, upsert, drop, switchProfile,
    logout: onLogout, quit: onQuit, toast,
  }), [profile, offline, vocab, model, items, loadError, loadItems, refreshModel, upsert, drop, switchProfile, onLogout, onQuit, toast]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

const SUMMARY_KEYS: (keyof ItemSummary)[] = ['id', 'name', 'category', 'color', 'color_hex', 'pattern', 'location', 'rating',
  'status', 'cutout_state', 'thumb_url', 'has_illustration', 'illustration_url', 'has_photo', 'created_at', 'updated_at'];

function pickSummary(item: ItemSummary): ItemSummary {
  const out = {} as Record<string, unknown>;
  for (const k of SUMMARY_KEYS) out[k] = item[k];
  return out as unknown as ItemSummary;
}
