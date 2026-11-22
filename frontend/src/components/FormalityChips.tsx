import { ChipGroup } from './ui/Chips';
import { formalityNeighbours } from '../labels';

export const ALSO_HINT = 'Choose a second level when it could be either, like penny loafers.';

/**
 * The formality as chips: the level it sits at most, then the level right below or above that it can also be
 * (a penny loafer: smart casual, and business too). Choosing a level makes it one level again.
 */
export function FormalityChips({ levels, value, also, disabled, onLevel, onAlso }: {
  /** the levels from most casual to most formal, as the vocabulary lists them */
  levels: string[];
  value: string | null | undefined;
  also: string | null | undefined;
  disabled?: boolean;
  onLevel(value: string | null): void;
  onAlso(value: string | null): void;
}) {
  const next = formalityNeighbours(value, levels);
  return (
    <>
      <ChipGroup field="formality" options={levels} value={value} disabled={disabled} onChange={onLevel} />
      {next.length > 0 && (
        <div className="formality-also">
          <ChipGroup field="formality_also" options={next} value={also} disabled={disabled} onChange={onAlso} />
          <p className="hint">{ALSO_HINT}</p>
        </div>
      )}
    </>
  );
}
