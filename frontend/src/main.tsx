import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { listenForLeaving } from './leave';
import './styles.css';
import { applyTheme, loadTheme } from './theme';
import { startHistory } from './router';
import { watchSignIn } from './signin';

applyTheme(loadTheme());

listenForLeaving(window, document);
watchSignIn(window);   // before the router reads the address: it takes `?signin=` out of it
startHistory();

// Safari only shows a press (:active, styles.css "touch") when the page listens for touches.
document.addEventListener('touchstart', () => undefined, { passive: true });

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary whole>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined);
  });
}
