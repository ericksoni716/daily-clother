import type { ReactNode } from 'react';
import { Link } from '../../router';
import type { ItemSummary } from '../../types';
import { Pic } from '../ItemPic';
import { cls } from './cls';

/**
 * An item's small picture on its light card (Today, Worn, What's missing, Insights). The size comes from the
 * screen's own class. `picture` replaces the usual cutout-drawing-photo choice; `to` makes it a link to the item.
 */
export function ItemThumb({ item, picture, to, title, className, testId }: {
  item?: ItemSummary;
  picture?: ReactNode;
  to?: string;
  title?: string;
  className?: string;
  testId?: string;
}) {
  const pic = picture ?? <Pic item={item} />;
  const classes = cls('item-thumb', className);
  if (to !== undefined) return <Link to={to} className={classes} title={title} data-testid={testId}>{pic}</Link>;
  return <span className={classes} title={title} data-testid={testId}>{pic}</span>;
}
