import { clsx } from 'clsx';

export function TabList({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx('inline-flex rounded-md border border-border bg-background p-1', className)} {...props} />;
}

export function TabButton({ active, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      className={clsx(
        'rounded px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:text-foreground',
        active && 'bg-panel text-foreground shadow-hairline',
        className,
      )}
      {...props}
    />
  );
}
