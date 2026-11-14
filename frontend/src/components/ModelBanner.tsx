import { useState } from 'react';
import { api } from '../api';
import { formatBytes } from '../labels';
import { CloseIcon } from './Icons';
import { Button, buttonClass, Notice } from './ui';
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

const HIDDEN_KEY = 'closet.modelNotice.hidden';

function hiddenFor(): string | null {
  try {
    return sessionStorage.getItem(HIDDEN_KEY);
  } catch {
    return null;
  }
}

/**
 * A notice above the closet grid while the background-removal model needs something done: download it, or try
 * again. Hidden for this session when the owner closes it; a new problem shows it again.
 */
export function ModelBanner() {
  const { model, refreshModel, offline, toast } = useCloset();
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(hiddenFor);
  if (!model || offline || (model.state !== 'missing' && model.state !== 'failed') || hidden === model.state) return null;
  const state = model.state;

  async function start() {
    setBusy(true);
    try {
      await api.downloadModel();
      await refreshModel();
      toast('Downloading the background-removal model');
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  function hide() {
    try {
      sessionStorage.setItem(HIDDEN_KEY, state);
    } catch {
      /* hidden until the page is reloaded */
    }
    setHidden(state);
  }

  return (
    <Notice tone={state === 'failed' ? 'error' : 'info'} role="status" testId="model-banner" className="model-notice"
      action={
        <>
          {state === 'failed'
            ? <Button variant="primary" small disabled={busy} onClick={start}>Try again</Button>
            : <Button small disabled={busy} onClick={start}>Download</Button>}
          <Link to="/settings" className={buttonClass({ variant: 'link', small: true })} aria-label="Background removal settings">Settings</Link>
          <Button variant="ghost" small className="notice-close" aria-label="Hide this for now" title="Hide this for now" onClick={hide}>
            <CloseIcon />
          </Button>
        </>
      }>
      <strong>Background removal: </strong>
      {state === 'missing' ? 'not set up yet. New photos keep their background for now.' : `the model download didn't work.${model.error ? ` ${model.error}` : ''}`}
    </Notice>
  );
}
