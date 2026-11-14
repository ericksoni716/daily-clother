import { Button, ChipGroup } from './ui';
import type { DetailChoices } from '../corrections';

interface Props {
  choices: DetailChoices;
  busy: boolean;
  /** Offer to give the kind back to Claude's description (only when the owner set it and there is one). */
  canGiveBack: boolean;
  onPick(value: unknown, words: string): void;
  onGiveBack(): void;
}

/** The kind of garment (joggers, a fleece pullover…): the kinds an item of its category can be, in words. */
export function KindChoices({ choices, busy, canGiveBack, onPick, onGiveBack }: Props) {
  const words = new Map(choices.choices.map((c) => [String(c.value), c.words]));
  return (
    <div className="fix-choices">
      <ChipGroup field="garment" title="Which kind is it?" options={[...words.keys()]} value={String(choices.value)}
        disabled={busy} clearable={false} labelOf={(v) => words.get(v) ?? v}
        onChange={(v) => { if (v !== null && v !== String(choices.value)) onPick(v, words.get(v) ?? v); }} />
      {canGiveBack && (
        <Button small className="fix-give-back" disabled={busy} onClick={onGiveBack}>Use what Claude saw instead</Button>
      )}
    </div>
  );
}
