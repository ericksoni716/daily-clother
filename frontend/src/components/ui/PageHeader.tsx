import type { ReactNode } from 'react';
import { BackIcon } from '../Icons';
import { Link } from '../../router';
import { cls } from './cls';

interface Props {
  title: ReactNode;
  /** The heading's id, for aria-labelledby and for tests. */
  titleId?: string;
  /** A short count beside the title ("12 items"). */
  count?: ReactNode;
  countTestId?: string;
  /** One line under the title. */
  subtitle?: ReactNode;
  back?: { to: string; label: string; className?: string };
  primary?: ReactNode;
  secondary?: ReactNode;
  className?: string;
}

/** The top of a screen: the title, then at most one secondary and one primary action. */
export function PageHeader({ title, titleId, count, countTestId, subtitle, back, primary, secondary, className }: Props) {
  const titleRow = (
    <div className="page-title-row">
      <h1 id={titleId}>{title}</h1>
      {count != null && count !== false && <span className="count" data-testid={countTestId}>{count}</span>}
    </div>
  );
  return (
    <header className={cls('page-header', className)}>
      {back || subtitle ? (
        <div className="page-heading">
          {back && <Link to={back.to} className={cls('btn btn-ghost btn-small page-back', back.className)}><BackIcon /> {back.label}</Link>}
          {titleRow}
          {subtitle && <p className="muted page-subtitle">{subtitle}</p>}
        </div>
      ) : titleRow}
      {secondary}
      {primary}
    </header>
  );
}
