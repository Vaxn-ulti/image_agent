import type { LucideIcon } from 'lucide-react';
import { Button } from './ui/Button';

type EmptyStateProps = {
  actionLabel?: string;
  body: string;
  icon: LucideIcon;
  onAction?: () => void;
  title: string;
};

export function EmptyState({ actionLabel, body, icon: Icon, onAction, title }: EmptyStateProps) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-background p-8 text-center">
      <Icon aria-hidden="true" className="mb-3 h-6 w-6 text-muted" />
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      <p className="mt-1 max-w-md text-sm text-muted">{body}</p>
      {actionLabel ? (
        <Button className="mt-4" onClick={onAction} variant="primary">
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
