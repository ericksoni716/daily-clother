/**
 * One Add for everything (17 November): the photos chosen or taken wait in a tray, Closet asks Claude what each shows
 * (one piece, several pieces, a shoe, and which photos are the same shoe), the owner checks it, and then each photo
 * goes the way it always has. Pure parts here; the screen is `screens/Add.tsx`.
 */

export type Kind = 'piece' | 'pieces' | 'shoe';

export interface TrayPhoto {
  key: string;
  file: File;
  url: string;
  kind: Kind;
  /** For a shoe: which shoe (1, 2, ...); photos with the same number are one shoe with all its photos. 0 otherwise. */
  shoe: number;
  /** The owner chose this one by hand: sorting again leaves it as they said. */
  fixed: boolean;
}

/** Photos sent to Claude in one question, and the most sorted at once (a bigger import goes in one piece per photo). */
export const SORT_AT_ONCE = 10;
export const SORT_MAX = 60;
/** The small copy Claude is shown, longest side in pixels. */
export const SORT_EDGE = 512;
/** The most photos one shoe takes (its main photo and five more). */
export const SHOE_PHOTOS = 6;

/** The batches the tray is sorted in, in order. */
export function batches<T>(list: T[], size = SORT_AT_ONCE): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
  return out;
}

/**
 * Claude's answers for each batch laid onto the tray: a photo the owner chose by hand keeps their choice, and shoe
 * numbers from later batches follow on from the earlier ones (a shoe is only grouped within its own batch).
 */
export function applySort(tray: TrayPhoto[], answers: { kind: Kind; shoe: number }[][]): TrayPhoto[] {
  const out = tray.map((p) => ({ ...p }));
  let offset = Math.max(0, ...out.filter((p) => p.fixed && p.kind === 'shoe').map((p) => p.shoe));
  let i = 0;
  for (const batch of answers) {
    let top = 0;
    for (const a of batch) {
      const p = out[i++];
      if (!p || p.fixed) continue;
      p.kind = a.kind;
      p.shoe = a.kind === 'shoe' ? a.shoe + offset : 0;
      top = Math.max(top, p.shoe);
    }
    offset = Math.max(offset, top);
  }
  return out;
}

/** The shoes in the tray: each shoe's photos in tray order, the first being the photo the shoe is made from. */
export function shoes(tray: TrayPhoto[]): TrayPhoto[][] {
  const by = new Map<number, TrayPhoto[]>();
  for (const p of tray) if (p.kind === 'shoe') by.set(p.shoe, [...(by.get(p.shoe) ?? []), p]);
  return [...by.keys()].sort((a, b) => a - b).map((n) => by.get(n)!);
}

/** The choices for one photo: a piece, several pieces, each shoe already in the tray, or a new shoe. */
export function choicesFor(tray: TrayPhoto[]): { value: string; label: string }[] {
  const numbers = [...new Set(tray.filter((p) => p.kind === 'shoe').map((p) => p.shoe))].sort((a, b) => a - b);
  const next = (numbers.at(-1) ?? 0) + 1;
  return [
    { value: 'piece', label: 'One piece' },
    { value: 'pieces', label: 'Several pieces' },
    ...numbers.map((n, i) => ({ value: `shoe:${n}`, label: `Shoe ${i + 1}` })),
    { value: `shoe:${next}`, label: numbers.length ? 'Another shoe' : 'A shoe' },
  ];
}

/** The tray's value for a photo's choice. */
export const valueOf = (p: TrayPhoto) => (p.kind === 'shoe' ? `shoe:${p.shoe}` : p.kind);

/** A photo set by hand to a choice ('piece', 'pieces' or 'shoe:N'). */
export function choose(p: TrayPhoto, value: string): TrayPhoto {
  if (value.startsWith('shoe:')) return { ...p, kind: 'shoe', shoe: Number(value.slice(5)), fixed: true };
  return { ...p, kind: value as Kind, shoe: 0, fixed: true };
}

/** One line for what the tray will add, as the button's neighbour says it. */
export function trayLine(tray: TrayPhoto[]): string {
  const pieces = tray.filter((p) => p.kind === 'piece').length;
  const several = tray.filter((p) => p.kind === 'pieces').length;
  const pairs = shoes(tray);
  const parts: string[] = [];
  if (pieces) parts.push(`${pieces} ${pieces === 1 ? 'piece' : 'pieces'}`);
  if (several) parts.push(`${several} ${several === 1 ? 'photo' : 'photos'} of several pieces`);
  if (pairs.length) parts.push(`${pairs.length} ${pairs.length === 1 ? 'shoe' : 'shoes'} (${pairs.map((s) => s.length).join(' + ')} photos)`);
  return parts.join(', ');
}

/** Shoes with more photos than a shoe takes: the extra ones are left out, said in plain words. */
export function tooManyForAShoe(tray: TrayPhoto[]): number {
  return shoes(tray).reduce((n, s) => n + Math.max(0, s.length - SHOE_PHOTOS), 0);
}
