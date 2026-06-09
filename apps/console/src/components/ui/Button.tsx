import { forwardRef } from 'react';
import { clsx } from 'clsx';

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'danger' | 'ghost' | 'primary' | 'secondary';
  size?: 'sm' | 'md';
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, size = 'md', variant = 'secondary', ...props }, ref) => (
  <button
    ref={ref}
    className={clsx(
      'inline-flex shrink-0 items-center justify-center gap-2 rounded-md border font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50',
      size === 'sm' ? 'h-8 px-2.5 text-xs' : 'h-9 px-3 text-sm',
      variant === 'danger' && 'border-danger bg-danger text-paper hover:bg-danger/90',
      variant === 'ghost' && 'border-transparent text-muted hover:bg-panel hover:text-foreground',
      variant === 'primary' && 'border-accent bg-accent text-paper hover:bg-accent/90',
      variant === 'secondary' && 'border-border bg-paper text-foreground hover:bg-panel',
      className,
    )}
    {...props}
  />
));

Button.displayName = 'Button';
