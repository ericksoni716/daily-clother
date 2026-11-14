import type { AriaRole, ReactNode } from 'react';
import { cls } from './cls';

export type NoticeTone = 'info' | 'warning' | 'error';

/** A message set apart from the page: information, a warning or an error, with an optional action. */
export function Notice({ tone = 'info', icon, action, role, as: Tag = 'div', className, testId, children }: {
  tone?: NoticeTone;
  icon?: ReactNode;
  action?: ReactNode;
  role?: AriaRole;
  /** 'p' only when the children are plain text. */
  as?: 'div' | 'p';
  className?: string;
  testId?: string;
  children: ReactNode;
}) {
  const hasAction = action != null && action !== false;
  return (
    <Tag className={cls('notice', tone === 'warning' && 'notice-warn', tone === 'error' && 'notice-error', hasAction && 'has-action', className)}
      role={role} data-testid={testId}>
      {icon}
      {hasAction ? <><div className="notice-text">{children}</div><div className="notice-action">{action}</div></> : children}
    </Tag>
  );
}
