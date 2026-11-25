import { QueryClientProvider, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { api, connection } from './api';
import { keepShowDrawings, loadShowDrawings, ShowDrawings } from './drawing';
import { outboxFor, refusedLine, type KeptAction, type Outbox, type OutboxEvent } from './outbox';
import { itemsQuery, modelQuery, progressQuery, stale, touch, vocabQuery, writeItem } from './queries';
import { makeQueryClient } from './queryClient';
import { queryKeys } from './queryKeys';
import { picturesQuery } from './settings';
import { keptFor, type WearManyAnswer } from './today';
import type { Profile, ProgressList } from './types';
import { uploads } from './uploads';
import { downloading, DOWNLOAD_MS, movedOn, progressPoll } from './work';

/** The open closet: which one, whether Nines can be reached, and what is done to it as a whole. This changes only
 * when the closet is switched or the connection comes and goes, so reading it never draws a screen again on its own. */
interface AppState {
  profile: Profile;
  offline: boolean;
  switchProfile(profile: Profile): Promise<void>;
  quit(): Promise<void>;
  toast(message: string, kind?: 'ok' | 'error'): void;
}

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp outside ClosetProvider');
  return v;
}

/** What is kept on this phone for the open closet, to be sent when Nines answers (`outbox.ts`); drawn again as it changes. */
export function useKept(box: Outbox): KeptAction[] {
  return useSyncExternalStore(useCallback((changed: () => void) => box.subscribe(changed), [box]), () => box.list);
}

/**
 * After an action kept on this phone reached Nines, or Nines refused it: Today's memory of what is worn takes what Nines
 * recorded (or forgets the outfit Nines refused), and what it touches is read again, so every screen shows what Nines
 * says is true.
 */
function afterKept(qc: QueryClient, profile: string, e: OutboxEvent): void {
  const a = e.action;
  if (a.kind === 'wear') {
    const kept = keptFor(profile);
    const record = kept.worn(a.day);
    if (record?.kept === a.id) {
      if (e.type === 'sent') {
        const r = e.answer as WearManyAnswer;
        kept.setWorn({ ...record, worn_on: r.worn_on, recorded: r.recorded ?? [], outfit_id: r.outfit?.id, at: Date.now(), kept: undefined });
      } else kept.setWorn(null);
    }
    if (e.type === 'sent') (e.answer as WearManyAnswer).items.forEach((i) => writeItem(qc, i));
    void touch(qc, 'wear');
  } else if (a.kind === 'rate') void touch(qc, 'outfit');
  else void touch(qc, 'trip');
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

function OpenCloset({ profile, onProfile, onQuit, toast, children }: Props) {
  const qc = useQueryClient();
  const offline = useOffline();

  // Read at once when the closet opens. The list is followed here so a poll can bring it up to date: a read that
  // brings the same list changes nothing, so neither this nor any screen draws again.
  useQuery(vocabQuery());
  useQuery(itemsQuery('active'));
  useQuery({ ...modelQuery(), refetchInterval: (q) => (downloading(q.state.data) && !offline ? DOWNLOAD_MS : false) });

  // Settings' "Show drawings instead of photos", for every small picture of an item: read on its own when the closet
  // opens (`GET /api/settings/pictures`), so the settings' own read, freshness and parts stay as each screen has them;
  // meanwhile, and while Nines cannot be reached, the last word this device had on it.
  const said = useQuery({ ...picturesQuery(), enabled: !offline, select: (p) => p.show_drawings }).data;
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
    void stale(qc, queryKeys.items('active'), { exact: true });
    void stale(qc, queryKeys.items('archived'), { exact: true });
    for (const id of moved) void stale(qc, queryKeys.item(id), { exact: true });
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

  // What was kept on this phone while Nines could not be reached is sent when it answers again: when the app opens,
  // when the browser says it is back online, when the page comes back into view, and after any call Nines answers.
  // Never by the service worker or in the background: iOS Safari has neither for a page like this.
  useEffect(() => {
    const box = outboxFor(profile);
    const send = () => {
      if (box.list.length) void box.flush();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') send();
    };
    send();
    window.addEventListener('online', send);
    document.addEventListener('visibilitychange', onVisible);
    const stopAnswers = connection.onAnswer(send);
    const stopEvents = box.onEvent((e) => {
      if (e.type === 'refused') toast(refusedLine(e.action, e.message), 'error');
      afterKept(qc, profile, e);
    });
    return () => {
      window.removeEventListener('online', send);
      document.removeEventListener('visibilitychange', onVisible);
      stopAnswers();
      stopEvents();
    };
  }, [profile, qc, toast]);

  // A finished upload shows up in the grid straight away.
  useEffect(() => {
    let done = uploads.snapshot.filter((e) => e.status === 'done').length;
    return uploads.subscribe((entries) => {
      const now = entries.filter((e) => e.status === 'done').length;
      if (now > done) {
        void stale(qc, queryKeys.items('active'), { exact: true });
        void stale(qc, queryKeys.progress(), { exact: true });
      }
      done = now;
    });
  }, [qc]);

  const switchProfile = useCallback(async (p: Profile) => {
    await api.setProfile(p);
    onProfile(p);   // App mounts a new provider, with a new cache, for the other closet
  }, [onProfile]);

  const value = useMemo<AppState>(() => ({
    profile, offline, switchProfile, quit: onQuit, toast,
  }), [profile, offline, switchProfile, onQuit, toast]);

  return (
    <Ctx.Provider value={value}>
      <ShowDrawings.Provider value={showDrawings}>{children}</ShowDrawings.Provider>
    </Ctx.Provider>
  );
}
