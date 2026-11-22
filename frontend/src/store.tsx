import { QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, connection } from './api';
import { keepShowDrawings, loadShowDrawings, ShowDrawings } from './drawing';
import { itemsQuery, modelQuery, progressQuery, vocabQuery } from './queries';
import { makeQueryClient } from './queryClient';
import { queryKeys } from './queryKeys';
import { settingsQuery } from './settings';
import type { Profile, ProgressList } from './types';
import { uploads } from './uploads';
import { downloading, DOWNLOAD_MS, movedOn, progressPoll } from './work';

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

function OpenCloset({ profile, onProfile, onLogout, onQuit, toast, children }: Props) {
  const qc = useQueryClient();
  const offline = useOffline();

  // Read at once when the closet opens. The list is followed here so a poll can bring it up to date: a read that
  // brings the same list changes nothing, so neither this nor any screen draws again.
  useQuery(vocabQuery());
  useQuery(itemsQuery('active'));
  useQuery({ ...modelQuery(), refetchInterval: (q) => (downloading(q.state.data) && !offline ? DOWNLOAD_MS : false) });

  // Settings' "Show drawings instead of photos", for every small picture of an item: read with the settings when the
  // closet opens; meanwhile, and while Nines cannot be reached, the last word this device had on it.
  const said = useQuery({ ...settingsQuery(), enabled: !offline, select: (s) => s.show_drawings }).data;
  const [lastSaid] = useState(loadShowDrawings);
  useEffect(() => {
    if (said !== undefined) keepShowDrawings(said);
  }, [said]);
  const showDrawings = said ?? lastSaid;

  // The work under way, polled here for every screen: every 2 s while anything is being done (a cutout, a
  // description, a pattern measured, a shoe traced or drawn), every 10 s while items only wait for something outside,
  // and not at all when nothing is under way (an edit that starts work makes it stale, so it is asked again then).
  const progress = useQuery({
    ...progressQuery(),
    enabled: !offline,
    refetchInterval: (q) => progressPoll(q.state.data, offline) ?? false,
  }).data;

  // When an item's work moves on (a step finishes, it stops waiting, it is done), the closet's lists and that item's
  // page are read again, once: the poll itself never reads the whole list.
  const before = useRef<ProgressList | undefined>(undefined);
  useEffect(() => {
    if (!progress) return;
    const moved = movedOn(before.current, progress);
    before.current = progress;
    if (!moved.length) return;
    void qc.invalidateQueries({ queryKey: queryKeys.items('active'), exact: true });
    void qc.invalidateQueries({ queryKey: queryKeys.items('archived'), exact: true });
    for (const id of moved) void qc.invalidateQueries({ queryKey: queryKeys.item(id), exact: true });
  }, [progress, qc]);

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
      if (now > done) {
        void qc.invalidateQueries({ queryKey: queryKeys.items('active'), exact: true });
        void qc.invalidateQueries({ queryKey: queryKeys.progress(), exact: true });
      }
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

  return (
    <Ctx.Provider value={value}>
      <ShowDrawings.Provider value={showDrawings}>{children}</ShowDrawings.Provider>
    </Ctx.Provider>
  );
}
