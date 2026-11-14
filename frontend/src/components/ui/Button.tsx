import type { ButtonHTMLAttributes } from 'react';
import { cls } from './cls';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger-quiet' | 'link';

export interface ButtonLook {
  variant?: ButtonVariant;
  small?: boolean;
  block?: boolean;
  className?: string;
}

/** The classes of a button, for a link that looks like one. */
export function buttonClass({ variant = 'secondary', small, block, className }: ButtonLook = {}): string {
  return cls(
    'btn',
    variant === 'primary' && 'btn-primary',
    variant === 'ghost' && 'btn-ghost',
    variant === 'danger-quiet' && 'btn-ghost btn-danger-quiet',
    variant === 'link' && 'btn-link',
    small && 'btn-small',
    block && 'btn-block',
    className,
  );
}

/** A button over the app's `.btn` classes. It is not a submit button unless `type="submit"` is given. */
export function Button({ variant, small, block, className, type = 'button', ...rest }: ButtonLook & ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type={type} className={buttonClass({ variant, small, block, className })} {...rest} />;
}
