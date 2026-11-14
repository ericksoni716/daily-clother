/** Light or dark: the owner's choice in Settings ("Look"), or the device's own setting. Kept on this device only. */

export type Theme = 'light' | 'dark' | 'system';

/** Where this device remembers the choice; nothing is kept for "Same as this device". */
export const THEME_KEY = 'closet.theme';

export const THEME_CHOICES: readonly { value: Theme; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'Same as this device' },
];

export function loadTheme(): Theme {
  try {
    const kept = localStorage.getItem(THEME_KEY);
    return kept === 'light' || kept === 'dark' ? kept : 'system';
  } catch {
    return 'system';
  }
}

export function saveTheme(theme: Theme): void {
  try {
    if (theme === 'system') localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* private browsing: the choice lasts until the page is closed */
  }
}

/** Sets data-theme on <html> (light or dark win over the device), or removes it to follow the device. */
export function applyTheme(theme: Theme, root: { setAttribute(n: string, v: string): void; removeAttribute(n: string): void } = document.documentElement): void {
  if (theme === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
}
