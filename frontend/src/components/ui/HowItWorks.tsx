import type { ReactNode } from 'react';
import { cls } from './cls';

/**
 * The one place a screen explains itself: a quiet line, closed by default, that opens a few sentences. It stands in for
 * hint paragraphs that would otherwise be said on every visit (DESIGN, "Reading load is a budget").
 */
export function HowItWorks({ title = 'How this works', className, testId, children }: {
  title?: ReactNode;
  className?: string;
  testId?: string;
  children: ReactNode;
}) {
  return (
    <details className={cls('how', className)} data-testid={testId}>
      <summary><span className="how-mark" aria-hidden="true">?</span>{title}</summary>
      <div className="how-body">{children}</div>
    </details>
  );
}
