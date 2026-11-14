import { afterEach, describe, expect, it, vi } from 'vitest';
import { applyTheme, loadTheme, saveTheme, THEME_KEY } from './theme';

function fakeStorage() {
  const kept = new Map<string, string>();
  return {
    kept,
    getItem: (k: string) => kept.get(k) ?? null,
    setItem: (k: string, v: string) => void kept.set(k, v),
    removeItem: (k: string) => void kept.delete(k),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('theme', () => {
  it('follows the device until light or dark is chosen, and forgets the choice for "Same as this device"', () => {
    const storage = fakeStorage();
    vi.stubGlobal('localStorage', storage);
    expect(loadTheme()).toBe('system');
    saveTheme('dark');
    expect(storage.kept.get(THEME_KEY)).toBe('dark');
    expect(loadTheme()).toBe('dark');
    saveTheme('system');
    expect(storage.kept.has(THEME_KEY)).toBe(false);
    expect(loadTheme()).toBe('system');
  });

  it('ignores a value it does not know', () => {
    const storage = fakeStorage();
    storage.kept.set(THEME_KEY, 'purple');
    vi.stubGlobal('localStorage', storage);
    expect(loadTheme()).toBe('system');
  });

  it('works without storage (private browsing)', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('denied'); },
      setItem: () => { throw new Error('denied'); },
      removeItem: () => { throw new Error('denied'); },
    });
    expect(loadTheme()).toBe('system');
    expect(() => saveTheme('dark')).not.toThrow();
  });

  it('sets data-theme for light or dark and removes it to follow the device', () => {
    const attrs = new Map<string, string>();
    const root = { setAttribute: (n: string, v: string) => void attrs.set(n, v), removeAttribute: (n: string) => void attrs.delete(n) };
    applyTheme('dark', root);
    expect(attrs.get('data-theme')).toBe('dark');
    applyTheme('light', root);
    expect(attrs.get('data-theme')).toBe('light');
    applyTheme('system', root);
    expect(attrs.has('data-theme')).toBe(false);
  });
});
