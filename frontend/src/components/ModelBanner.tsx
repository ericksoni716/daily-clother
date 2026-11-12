import { useState } from 'react';
import { api } from '../api';
import { formatBytes } from '../labels';
import { Link } from '../router';
import { useCloset } from '../store';
import type { ModelInfo } from '../types';

export function modelStateText(m: ModelInfo): string {
  switch (m.state) {
    case 'ready': return 'Ready. New photos get their background removed automatically.';
    case 'missing': return "Not downloaded yet. New photos keep their background until it's downloaded.";
    case 'downloading': return 'Downloading…';
    case 'failed': return "The download didn't work.";
  }
}

export function ModelProgress({ model }: { model: ModelInfo }) {
  const total = model.total_bytes ?? 0;
  const pct = total ? Math.min(100, Math.round((model.downloaded_bytes / total) * 100)) : undefined;
  return (
    <div className="progress-wrap">
      <progress className="progress" max={100} value={pct} aria-label="Model download progress" />
      <span className="small muted">
        {total ? `${formatBytes(model.downloaded_bytes)} of ${formatBytes(total)}` : `${formatBytes(model.downloaded_bytes)} so far`}
      </span>
    </div>
  );
}

/** Slim banner above the grid while the background-removal model is not ready. */
export function ModelBanner() {
  const { model, refreshModel, offline, toast } = useCloset();
  const [busy, setBusy] = useState(false);
  if (!model || model.state === 'ready' || offline) return null;

  async function start() {
    setBusy(true);
    try {
      await api.downloadModel();
      await refreshModel();
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`model-banner model-${model.state}`} role="status" data-testid="model-banner">
      <div className="model-banner-text">
        <strong>Background removal: </strong>
        {model.state === 'downloading' && <span>getting the model ready.</span>}
        {model.state === 'missing' && <span>the model isn't downloaded yet, so new photos keep their background for now.</span>}
        {model.state === 'failed' && <span>the model download didn't work.{model.error ? ` ${model.error}` : ''}</span>}
        {model.state === 'downloading' && <ModelProgress model={model} />}
      </div>
      <div className="model-banner-actions">
        {model.state === 'failed' && <button className="btn btn-small btn-primary" disabled={busy} onClick={start}>Try again</button>}
        {model.state === 'missing' && <button className="btn btn-small" disabled={busy} onClick={start}>Download</button>}
        <Link to="/settings" className="btn btn-small btn-link">Settings</Link>
      </div>
    </div>
  );
}
