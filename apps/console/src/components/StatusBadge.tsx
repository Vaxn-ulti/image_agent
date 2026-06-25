import { clsx } from 'clsx';
import type { TaskStatus } from '../lib/types';

const labels: Record<TaskStatus, string> = {
  cancelled: 'Cancelled',
  completed: 'Completed',
  completed_with_partial_failures: 'Partial',
  failed: 'Failed',
  queued: 'Queued',
  running: 'Running',
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold',
        'before:h-1.5 before:w-1.5 before:rounded-full',
        status === 'completed' && 'border-success/35 bg-success/10 text-success before:bg-success',
        status === 'running' && 'border-accent/35 bg-accentSoft text-accent before:bg-accent',
        status === 'queued' && 'border-border bg-paper text-muted before:bg-muted',
        status === 'completed_with_partial_failures' && 'border-warning/35 bg-warning/10 text-warning before:bg-warning',
        (status === 'failed' || status === 'cancelled') && 'border-danger/35 bg-danger/10 text-danger before:bg-danger',
      )}
    >
      {labels[status]}
    </span>
  );
}
