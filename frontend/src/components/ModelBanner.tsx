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

const SECOND = 'which fixes cutouts the first one gets wrong (stripes or checks taken for background, or the bed a piece lies on kept with it)';

/** The second model's state, shown under the first once that one is ready. */
export function secondModelText(m: ModelInfo): string {
  switch (m.state) {
    case 'ready': return 'The second model is ready too.';
    case 'downloading': return `Also downloading a second model, ${SECOND}. Photos cut out before it's here are looked at again once it is.`;
    case 'missing': return `The second model, ${SECOND}, isn't downloaded. Photos cut out without it are looked at again once it's here.`;
    case 'failed': return `The second model, ${SECOND}, didn't download. Photos cut out without it are looked at again once it's here.`;
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
 * again; also when the second model's download didn't work. Hidden for this session when the owner closes it; a new
 * problem shows it again.
 */
export function ModelBanner() {
  const { model, refreshModel, offline, toast } = useCloset();
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(hiddenFor);
  if (!model || offline) return null;
  const second = model.second;
  const problem = model.state === 'missing' || model.state === 'failed' ? model.state
    : model.state === 'ready' && second?.state === 'failed' ? 'second-failed' : null;
  if (!problem || hidden === problem) return null;
  const state = problem;

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
    <Notice tone={state === 'missing' ? 'info' : 'error'} role="status" testId="model-banner" className="model-notice"
      action={
        <>
          {state !== 'missing'
            ? <Button variant="primary" small disabled={busy} onClick={start}>Try again</Button>
            : <Button small disabled={busy} onClick={start}>Download</Button>}
          <Link to="/settings" className={buttonClass({ variant: 'link', small: true })} aria-label="Background removal settings">Settings</Link>
          <Button variant="ghost" small className="notice-close" aria-label="Hide this for now" title="Hide this for now" onClick={hide}>
            <CloseIcon />
          </Button>
        </>
      }>
      <strong>Background removal: </strong>
      {state === 'missing' ? 'not set up yet. New photos keep their background for now.'
        : state === 'failed' ? `the model download didn't work.${model.error ? ` ${model.error}` : ''}`
          : `the second model didn't download, so stripes or checks can be taken for background.${second?.error ? ` ${second.error}` : ''}`}
    </Notice>
  );
}
