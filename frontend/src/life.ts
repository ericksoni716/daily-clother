export const SITUATIONS = [
  { id: 'work', label: 'Work' },
  { id: 'everyday', label: 'Everyday' },
  { id: 'going_out', label: 'Going out' },
  { id: 'lounging', label: 'Lounging at home' },
  { id: 'exercise', label: 'Exercise' },
  { id: 'vacation', label: 'Vacation' },
] as const;

export type SituationId = (typeof SITUATIONS)[number]['id'];

export interface Life {
  situations: Record<SituationId, number>;
  work_dress: 'casual' | 'smart_casual' | 'business' | 'formal';
  vacation_climate: 'warm' | 'cold' | 'both';
  vacation_weeks: number;
  style_words: string;
}

export const FREQUENCIES = [
  { value: 0, label: 'Never' },
  { value: 0.25, label: 'Now and then' },
  { value: 1, label: 'About weekly' },
  { value: 4, label: 'Most days' },
];

export function newLife(): Life {
  return {
    situations: { work: 0, everyday: 4, going_out: 0, lounging: 0, exercise: 0, vacation: 0 },
    work_dress: 'casual', vacation_climate: 'both', vacation_weeks: 0, style_words: '',
  };
}

export function activeSituations(life: Life | null | undefined) {
  return life ? SITUATIONS.filter(({ id }) => life.situations[id] > 0 && (id !== 'vacation' || life.vacation_weeks > 0)) : [];
}

export function frequencyWords(value: number): string {
  return FREQUENCIES.find((f) => f.value === value)?.label ?? `${value} days a week`;
}

export function situationLabel(id: string): string {
  return SITUATIONS.find((s) => s.id === id)?.label ?? id.replaceAll('_', ' ');
}

/** Reflect the saved answers, not assumptions inferred from the closet. */
export function lifeSummary(life: Life | null | undefined): string[] {
  if (!life) return [];
  return activeSituations(life).map(({ id, label }) => {
    if (id === 'vacation') {
      const climate = life.vacation_climate === 'both' ? 'warm and cold' : life.vacation_climate;
      return `vacation ${life.vacation_weeks} ${life.vacation_weeks === 1 ? 'week' : 'weeks'} a year, ${climate}`;
    }
    const days = life.situations[id];
    const frequency = days === .25 ? 'now and then' : `${days} ${days === 1 ? 'day' : 'days'} a week`;
    const dress = id === 'work' ? `, ${life.work_dress.replaceAll('_', ' ')}` : '';
    return `${label.toLowerCase()} ${frequency}${dress}`;
  });
}
