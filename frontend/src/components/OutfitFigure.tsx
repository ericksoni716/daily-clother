import { useEffect, useState } from 'react';
import { loadOutfitFigure } from '../outfitFigure';
import { figurePieces, type OutfitPieces } from '../today';

export function OutfitFigure({ pieces, offline }: { pieces: OutfitPieces; offline: boolean }) {
  const [attempt, setAttempt] = useState(0);
  return (
    <div className="today-figure">
      {offline
        ? <p role="status">As worn needs Closet on your computer to be reachable. Switch to Pieces to see the saved outfit.</p>
        : <FigureImage key={`${attempt}:${JSON.stringify(figurePieces(pieces))}`} pieces={pieces} onRetry={() => setAttempt((n) => n + 1)} />}
      <p className="hint">A drawing of the layers, not a fit preview. Extras are shown in Pieces.</p>
    </div>
  );
}

function FigureImage({ pieces, onRetry }: { pieces: OutfitPieces; onRetry(): void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { base, mid, outer, bottom, shoes } = pieces;
  useEffect(() => loadOutfitFigure({ base, mid, outer, bottom, shoes }, setUrl, setError), [base, mid, outer, bottom, shoes]);
  if (error) return (
    <div className="today-figure-message" role="alert">
      <p>Couldn't show this outfit as worn. {error} You can still use Pieces.</p>
      <button className="btn btn-small" onClick={onRetry}>Try drawing again</button>
    </div>
  );
  if (!url) return <p className="today-figure-message" role="status"><span className="spinner" aria-hidden="true" /> Drawing the outfit…</p>;
  return <img src={url} alt="Outfit as worn" onError={() => setError("The drawing couldn't be opened.")} />;
}
