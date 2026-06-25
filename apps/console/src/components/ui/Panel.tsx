import { clsx } from 'clsx';

export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <section className={clsx('rounded-lg border border-border bg-paper shadow-hairline', className)} {...props} />;
}

export function PanelHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx('flex min-h-11 items-center justify-between gap-3 border-b border-border px-4 py-3', className)} {...props} />;
}

export function PanelTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={clsx('text-sm font-semibold text-foreground', className)} {...props} />;
}

export function PanelBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx('p-4', className)} {...props} />;
}
