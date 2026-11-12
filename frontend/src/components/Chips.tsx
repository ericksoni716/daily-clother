import { useId } from 'react';
import { label as labelFor, FIELD_TITLES, SWATCH } from '../labels';

interface Props {
  field: string;
  options: string[];
  value: string | null | undefined;
  onChange(value: string | null): void;
  disabled?: boolean;
  title?: string;
  labelOf?: (v: string) => string;
  swatches?: boolean;
  /** Allow tapping the chosen chip again to clear it. */
  clearable?: boolean;
}

/** A group of tappable chips where at most one is chosen. */
export function ChipGroup({ field, options, value, onChange, disabled, title, labelOf, swatches, clearable = true }: Props) {
  const id = useId();
  const heading = title ?? FIELD_TITLES[field] ?? field;
  return (
    <div className="chip-group" role="group" aria-labelledby={id} data-field={field}>
      <h3 className="chip-group-title" id={id}>{heading}</h3>
      <div className="chips">
        {options.map((opt) => {
          const on = value === opt;
          return (
            <button
              key={opt}
              type="button"
              className={`chip${on ? ' is-on' : ''}`}
              aria-pressed={on}
              disabled={disabled}
              onClick={() => onChange(on ? (clearable ? null : opt) : opt)}
            >
              {swatches && <span className="swatch" style={{ background: SWATCH[opt] ?? '#ccc' }} aria-hidden="true" />}
              {labelOf ? labelOf(opt) : labelFor(field, opt)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
