import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement>;
const base = { width: 24, height: 24, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8,
  strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true };

export const HangerIcon = (p: P) => (
  <svg {...base} {...p}><path d="M10 6.2a2 2 0 1 1 2.6 1.9c-.4.1-.6.5-.6.9v1L3.4 15.6c-.8.6-.4 1.9.6 1.9h16c1 0 1.4-1.3.6-1.9L12 10" /></svg>
);
export const PlusIcon = (p: P) => (
  <svg {...base} {...p}><rect x="3.5" y="3.5" width="17" height="17" rx="4" /><path d="M12 8v8M8 12h8" /></svg>
);
export const GearIcon = (p: P) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
);
export const ArchiveIcon = (p: P) => (
  <svg {...base} {...p}><rect x="3" y="4" width="18" height="4.5" rx="1" /><path d="M5 8.5V19a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8.5M10 12.5h4" /></svg>
);
export const CameraIcon = (p: P) => (
  <svg {...base} {...p}><path d="M4 8a2 2 0 0 1 2-2h1.6l1.4-2h6l1.4 2H18a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" /><circle cx="12" cy="12.5" r="3.5" /></svg>
);
export const ImagesIcon = (p: P) => (
  <svg {...base} {...p}><rect x="3" y="5" width="15" height="14" rx="2" /><path d="M7 3h12a2 2 0 0 1 2 2v12" /><circle cx="8" cy="10" r="1.5" /><path d="m3 17 4.5-4.5 3 3 2-2 5.5 5.5" /></svg>
);
export const BackIcon = (p: P) => (
  <svg {...base} {...p}><path d="M15 5l-7 7 7 7" /></svg>
);
export const SearchIcon = (p: P) => (
  <svg {...base} {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>
);
export const WarnIcon = (p: P) => (
  <svg {...base} {...p}><path d="M12 4 2.8 19.5h18.4z" /><path d="M12 10v4.2M12 17.2v.1" /></svg>
);
export const CloudOffIcon = (p: P) => (
  <svg {...base} {...p}><path d="M3 3l18 18M8 7.5A5 5 0 0 1 17 10a4 4 0 0 1 3 6.5M17 18H7a4 4 0 0 1-1.4-7.8" /></svg>
);
export const CheckIcon = (p: P) => (
  <svg {...base} {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
);
export const ChevronIcon = (p: P) => (
  <svg {...base} {...p}><path d="m9 5 7 7-7 7" /></svg>
);
