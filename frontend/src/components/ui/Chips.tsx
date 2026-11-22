import { Fragment, useId, type ReactNode } from 'react';
import { label as labelFor, FIELD_TITLES, swatchOf } from '../../labels';

interface Props {
  field: string;
  options: string[];
  value: string | null | undefined;
  onChange(value: string | null): void;
  disabled?: boolean;
  title?: string;
  labelOf?: (v: string) => string;
  /** A colour swatch on each chip: `true` for the colour words' own swatches, or the colour of each option. */
  swatches?: boolean | ((v: string) => string);
  /** Allow tapping the chosen chip again to clear it. */
  clearable?: boolean;
  /** Shown just after the chosen chip (e.g. the colours measured from a pattern). */
  beside?: ReactNode;
}

/** A group of tappable chips where at most one is chosen. */
export function ChipGroup({ field, options, value, onChange, disabled, title, labelOf, swatches, clearable = true, beside }: Props) {
  const id = useId();
  const heading = title ?? FIELD_TITLES[field] ?? field;
  const swatch = typeof swatches === 'function' ? swatches : swatches ? swatchOf : null;
  return (
    <div className="chip-group" role="group" aria-labelledby={id} data-field={field}>
      <h3 className="chip-group-title" id={id}>{heading}</h3>
      <div className="chips">
        {options.map((opt) => {
          const on = value === opt;
          return (
            <Fragment key={opt}>
              <button
                type="button"
                className={`chip${on ? ' is-on' : ''}`}
                aria-pressed={on}
                disabled={disabled}
                onClick={() => onChange(on ? (clearable ? null : opt) : opt)}
              >
                {swatch && <span className="swatch" style={{ background: swatch(opt) }} aria-hidden="true" />}
                {labelOf ? labelOf(opt) : labelFor(field, opt)}
              </button>
              {on && beside}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
