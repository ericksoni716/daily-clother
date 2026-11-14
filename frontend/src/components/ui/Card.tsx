import type { HTMLAttributes, ReactNode } from 'react';
import { cls } from './cls';

type CardTag = 'div' | 'section' | 'article' | 'li' | 'form';

/** A surface with the app's one depth: a soft ring and, in light, a small shadow. */
export function Card({ as: Tag = 'div', className, ...rest }: { as?: CardTag } & HTMLAttributes<HTMLElement>) {
  return <Tag className={cls('card', className)} {...rest} />;
}

/** A card with a heading, an optional one-line hint and an optional action beside the heading. */
export function Section({ id, title, hint, action, className, children }: {
  id: string; title: ReactNode; hint?: ReactNode; action?: ReactNode; className?: string; children?: ReactNode;
}) {
  return (
    <section className={cls('card section', className)} aria-labelledby={id}>
      <div className="section-head">
        <div className="section-title">
          <h2 id={id}>{title}</h2>
          {hint && <p className="hint section-hint">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
