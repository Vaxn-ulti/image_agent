import type { ReactNode } from 'react';
import { clsx } from 'clsx';

type MetricBlockProps = {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: 'accent' | 'muted' | 'success' | 'warning' | 'danger';
};

export function MetricBlock({ detail, label, tone = 'muted', value }: MetricBlockProps) {
  return (
    <div className="rounded-lg border border-border bg-paper p-3">
      <div className="text-xs font-semibold uppercase tracking-normal text-muted">{label}</div>
      <div
        className={clsx(
          'mt-2 text-2xl font-semibold tabular-nums',
          tone === 'accent' && 'text-accent',
          tone === 'muted' && 'text-foreground',
          tone === 'success' && 'text-success',
          tone === 'warning' && 'text-warning',
          tone === 'danger' && 'text-danger',
        )}
      >
        {value}
      </div>
      {detail ? <div className="mt-1 text-xs leading-5 text-muted">{detail}</div> : null}
    </div>
  );
}
