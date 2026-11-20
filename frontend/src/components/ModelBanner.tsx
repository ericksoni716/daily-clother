import { useState } from 'react';
import { api } from '../api';
import { CloseIcon } from './Icons';
import { Button, buttonClass, Notice } from './ui';
import { Link } from '../router';
import { useCloset } from '../store';

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
