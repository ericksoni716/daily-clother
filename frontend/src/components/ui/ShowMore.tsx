import { useState, type ReactNode } from 'react';
import { Link, useMediaQuery } from '../../router';
import { buttonClass } from './Button';
import { cls } from './cls';
import { PHONE } from './Sheet';

/** The words of the button under a list cut short: "See all 9", or "See all" when the whole count is not known. */
export function seeAllWords(total: number | null): string {
  return total === null ? 'See all' : `See all ${total}`;
}

/**
 * A list that shows its first few on a phone (`first`; `wide` on a wider screen, every one when left out), then
 * "See all N", which shows the rest in place, or goes to `to` (a page with the whole list) when it is given.
 */
export function ShowMore<T>({ items, first, wide, keyOf, render, to, total, moreLabel, as: Tag = 'ul', label, className, itemClassName, testId }: {
  items: readonly T[];
  first: number;
  wide?: number;
  keyOf(item: T): string;
  render(item: T, index: number): ReactNode;
  to?: string;
  /** How many there are in all, when that is more than `items` holds (a list read a page at a time); null: unknown. */
  total?: number | null;
  moreLabel?: string;
  as?: 'ul' | 'ol';
  label?: string;
  className?: string;
  itemClassName?: string;
  testId?: string;
}) {
  const phone = useMediaQuery(PHONE);
  const [all, setAll] = useState(false);
  const limit = all ? items.length : phone ? first : wide ?? items.length;
  const shown = items.slice(0, limit);
  const count = total === undefined ? items.length : total;
  const cut = count === null || count > shown.length;
  const words = moreLabel ?? seeAllWords(count);
  return (
    <>
      <Tag className={className} aria-label={label} data-testid={testId}>
        {shown.map((item, i) => <li key={keyOf(item)} className={itemClassName}>{render(item, i)}</li>)}
      </Tag>
      {cut && (to !== undefined
        ? <Link to={to} className={buttonClass({ variant: 'link', className: 'show-more' })}>{words}</Link>
        : <button type="button" className={cls(buttonClass({ variant: 'link' }), 'show-more')} onClick={() => setAll(true)}>{words}</button>)}
    </>
  );
}
