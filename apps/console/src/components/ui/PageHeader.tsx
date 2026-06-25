import type { ReactNode } from 'react';

type PageHeaderProps = {
  title: string;
  eyebrow?: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ actions, description, eyebrow, title }: PageHeaderProps) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4 max-md:flex-col">
      <div>
        {eyebrow ? <div className="mb-1 text-xs font-semibold uppercase tracking-normal text-muted">{eyebrow}</div> : null}
        <h1 className="text-2xl font-semibold leading-tight text-foreground">{title}</h1>
        {description ? <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
