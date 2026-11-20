import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { listenForLeaving } from './leave';
import './styles.css';
import { applyTheme, loadTheme } from './theme';
import { startHistory } from './router';

applyTheme(loadTheme());

listenForLeaving(window, document);
startHistory();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined);
  });
}
