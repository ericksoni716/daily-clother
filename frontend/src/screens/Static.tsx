import { NinesMark, NinesName } from '../components/NinesMark';

export function LoadingScreen() {
  return (
    <main className="center-screen" aria-busy="true">
      <NinesMark className="nines-mark-screen" />
      <p className="muted">Opening your closet…</p>
    </main>
  );
}

export function ClosedScreen() {
  return (
    <main className="center-screen">
      <NinesMark className="nines-mark-screen" />
      <h1><NinesName /> has been closed.</h1>
      <p className="muted">You can close this tab.</p>
    </main>
  );
}

/** The door turned this device away (backend/closet/gate.py): the server's own sentence says why and what to do. */
export function RefusedScreen({ message, onReload }: { message: string; onReload(): void }) {
  return (
    <main className="center-screen">
      <NinesMark className="nines-mark-screen" />
      <h1><NinesName /> didn't let this device in</h1>
      <p className="muted narrow" data-testid="refused">{message}</p>
      <button className="btn btn-primary" onClick={onReload}>Reload</button>
    </main>
  );
}

export function UnreachableScreen({ message, onRetry }: { message: string; onRetry(): void }) {
  return (
    <main className="center-screen">
      <NinesMark className="nines-mark-screen" />
      <h1><NinesName /> isn't answering</h1>
      <p className="muted narrow">{message} If you just started it, give it a few seconds.</p>
      <button className="btn btn-primary" onClick={onRetry}>Try again</button>
    </main>
  );
}
