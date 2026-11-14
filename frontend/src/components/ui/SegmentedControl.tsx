import type { ReactNode } from 'react';
import { Link } from '../../router';
import { cls } from './cls';

export interface Segment<T extends string> {
  value: T;
  label: ReactNode;
  /** Makes the segment a link to this path (marked aria-current="page" when on) instead of a button (aria-pressed). */
  to?: string;
}

/** A row of two to four choices of which one is on. */
export function SegmentedControl<T extends string>({ label, options, value, onChange, small, className, disabled }: {
  /** The group's accessible name. */
  label: string;
  options: readonly Segment<T>[];
  /** The one that is on; null when none is. */
  value: T | null;
  onChange?: (value: T) => void;
  small?: boolean;
  className?: string;
  /** Buttons cannot be pressed (offline, or while something is being worked out). */
  disabled?: boolean;
}) {
  return (
    <div className={cls('segmented', small && 'segmented-small', className)} role="group" aria-label={label}>
      {options.map((o) => {
        const on = o.value === value;
        return o.to !== undefined ? (
          <Link key={o.value} to={o.to} className={on ? 'is-on' : ''} aria-current={on ? 'page' : undefined}>{o.label}</Link>
        ) : (
          <button key={o.value} type="button" className={on ? 'is-on' : ''} aria-pressed={on} disabled={disabled} onClick={() => onChange?.(o.value)}>{o.label}</button>
        );
      })}
    </div>
  );
}
