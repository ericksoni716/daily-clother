import { useState, type ReactNode } from 'react';
import { cls } from './cls';

/**
 * Something closed until it is wanted: a line with a chevron that opens what it holds in place, pushing nothing else
 * around until it is tapped. `lazy` draws what it holds only once it has been opened (charts, a long list).
 */
export function Fold({ title, open: startOpen = false, lazy = false, className, testId, onToggle, children }: {
  title: ReactNode;
  /** Open to begin with. */
  open?: boolean;
  lazy?: boolean;
  className?: string;
  testId?: string;
  onToggle?(open: boolean): void;
  children: ReactNode;
}) {
  const [opened, setOpened] = useState(startOpen);
  return (
    <details className={cls('more fold', className)} open={startOpen} data-testid={testId}
      onToggle={(e) => {
        const open = (e.currentTarget as HTMLDetailsElement).open;
        if (open) setOpened(true);
        onToggle?.(open);
      }}>
      <summary>{title}</summary>
      <div className="fold-body">{!lazy || opened ? children : null}</div>
    </details>
  );
}
