import { HangerIcon } from '../components/Icons';

export function LoadingScreen() {
  return (
    <main className="center-screen" aria-busy="true">
      <div className="brand-mark"><HangerIcon /></div>
      <p className="muted">Opening your closet…</p>
    </main>
  );
}

export function ClosedScreen() {
  return (
    <main className="center-screen">
      <div className="brand-mark"><HangerIcon /></div>
      <h1>Closet has been closed.</h1>
      <p className="muted">You can close this tab.</p>
    </main>
  );
}

export function UnreachableScreen({ message, onRetry }: { message: string; onRetry(): void }) {
  return (
    <main className="center-screen">
      <div className="brand-mark"><HangerIcon /></div>
      <h1>Closet isn't answering</h1>
      <p className="muted narrow">{message} If you just started it, give it a few seconds.</p>
      <button className="btn btn-primary" onClick={onRetry}>Try again</button>
    </main>
  );
}
