import { QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { api, connection } from './api';
import { itemQuery, itemsQuery, modelQuery, usePoll, vocabQuery } from './queries';
import { makeQueryClient } from './queryClient';
import { queryKeys } from './queryKeys';
import type { Item, ItemSummary, Profile } from './types';
import { uploads } from './uploads';
import { closetPoll, downloading, DOWNLOAD_MS, justFinished, measuring } from './work';

/** The open closet: which one, whether Closet can be reached, and what is done to it as a whole. This changes only
 * when the closet is switched or the connection comes and goes, so reading it never draws a screen again on its own. */
interface AppState {
  profile: Profile;
  offline: boolean;
  switchProfile(profile: Profile): Promise<void>;
  logout(): Promise<void>;
  quit(): Promise<void>;
  toast(message: string, kind?: 'ok' | 'error'): void;
}

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp outside ClosetProvider');
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

interface Props {
  profile: Profile;
  onProfile(profile: Profile): void;
  onLogout(): Promise<void>;
  onQuit(): Promise<void>;
  toast(message: string, kind?: 'ok' | 'error'): void;
  children: ReactNode;
}

/** The open closet, with a query cache of its own (App mounts a new one when the closet is switched). */
export function ClosetProvider(props: Props) {
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <OpenCloset {...props} />
    </QueryClientProvider>
  );
}

/** The ids of items known in full whose pattern is being measured or whose shoe is being traced, as one string. */
function measuringIds(qc: ReturnType<typeof useQueryClient>): string {
  return qc.getQueryCache().findAll({ queryKey: ['item'] })
    .filter((q) => {
      const item = q.state.data as Item | undefined;
      return item && measuring(item);
    })
    .map((q) => (q.state.data as Item).id).sort().join(',');
}

/** "id:cutout:tag" for every item in the list, to see when a step finishes. */
const stepsOf = (list: ItemSummary[]) => list.map((i) => `${i.id}:${i.cutout_state}:${i.tag_state}`).join(',');

function OpenCloset({ profile, onProfile, onLogout, onQuit, toast, children }: Props) {
  const qc = useQueryClient();
  const offline = useOffline();

  // Read at once when the closet opens. The list is followed here for the polling only: a poll that brings the same
  // list changes nothing, so neither this nor any screen draws again.
  useQuery(vocabQuery());
  const items = useQuery(itemsQuery('active')).data;
  const model = useQuery({ ...modelQuery(), refetchInterval: (q) => (downloading(q.state.data) && !offline ? DOWNLOAD_MS : false) }).data;
  const working = useSyncExternalStore(
    useCallback((onChange) => qc.getQueryCache().subscribe(onChange), [qc]),
    () => measuringIds(qc),
  );

  // Poll while items are cut out, described, measured, traced or drawn: every 2 s while the model (or Claude) is
  // working on them; slower while a pattern is measured, and slower still while the model is missing or failed or
  // items wait for a way to reach Claude, since nothing changes until then.
  const plan = closetPoll(items, model, working ? working.split(',').length : 0, offline);
  usePoll(plan.ms, () => {
    void qc.refetchQueries({ queryKey: queryKeys.items('active'), exact: true }, { cancelRefetch: false });
    if (plan.model) void qc.refetchQueries({ queryKey: queryKeys.model(), exact: true }, { cancelRefetch: false });
    // items measured or traced: asked for in full, unless their page is open and asks for them itself
    for (const id of working ? working.split(',') : []) {
      const q = qc.getQueryCache().find({ queryKey: queryKeys.item(id), exact: true });
      if (q && q.getObserversCount() === 0) void qc.refetchQueries({ queryKey: queryKeys.item(id), exact: true }, { cancelRefetch: false });
    }
  });

  // A cutout or description just finished: its item is read in full once, to learn whether a pattern is now
  // measured or a shoe traced, which the list does not say.
  const before = useRef<ItemSummary[] | undefined>(undefined);
  const steps = items ? stepsOf(items) : '';
  useEffect(() => {
    const now = qc.getQueryData<ItemSummary[]>(queryKeys.items('active'));
    if (!now) return;
    for (const id of justFinished(before.current, now)) {
      void qc.fetchQuery(itemQuery(id)).catch(() => undefined);
    }
    before.current = now;
  }, [steps, qc]);

  // Back online: ask again for everything on screen. While offline, check the server every few seconds.
  const wasOffline = useRef(offline);
  useEffect(() => {
    if (wasOffline.current && !offline) void qc.invalidateQueries();
    wasOffline.current = offline;
    if (!offline) return;
    const t = window.setInterval(() => {
      api.session().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(t);
  }, [offline, qc]);

  // A finished upload shows up in the grid straight away.
  useEffect(() => {
    let done = uploads.snapshot.filter((e) => e.status === 'done').length;
    return uploads.subscribe((entries) => {
      const now = entries.filter((e) => e.status === 'done').length;
      if (now > done) void qc.invalidateQueries({ queryKey: queryKeys.items('active'), exact: true });
      done = now;
    });
  }, [qc]);

  const switchProfile = useCallback(async (p: Profile) => {
    await api.setProfile(p);
    onProfile(p);   // App mounts a new provider, with a new cache, for the other closet
  }, [onProfile]);

  const value = useMemo<AppState>(() => ({
    profile, offline, switchProfile, logout: onLogout, quit: onQuit, toast,
  }), [profile, offline, switchProfile, onLogout, onQuit, toast]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
