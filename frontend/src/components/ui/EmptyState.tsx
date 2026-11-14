import type { ReactNode } from 'react';
import { cls } from './cls';

/** What a screen shows when it has nothing yet: an icon, a title, one sentence and one button. */
export function EmptyState({ icon, title, body, action, big, className, testId, children }: {
  icon?: ReactNode;
  title: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
  big?: boolean;
  className?: string;
  testId?: string;
  children?: ReactNode;
}) {
  return (
    <div className={cls('empty', big && 'empty-big', className)} data-testid={testId}>
      {icon && <div className="empty-art">{icon}</div>}
      <p className="empty-title">{title}</p>
      {body && <p className="muted">{body}</p>}
      {action}
      {children}
    </div>
  );
}
