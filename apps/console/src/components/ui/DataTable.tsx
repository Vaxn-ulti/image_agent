import type { ReactNode } from 'react';
import { clsx } from 'clsx';

type DataTableProps = {
  children: ReactNode;
  className?: string;
  empty?: ReactNode;
  isEmpty?: boolean;
};

export function DataTable({ children, className, empty, isEmpty }: DataTableProps) {
  if (isEmpty) {
    return <div className="rounded-md border border-dashed border-border bg-panel p-4 text-sm text-muted">{empty || 'No records available.'}</div>;
  }

  return (
    <div className="scientific-scrollbar overflow-x-auto">
      <table className={clsx('w-full border-collapse text-left text-sm', className)}>{children}</table>
    </div>
  );
}

export function TableHead({ children, className }: { children: ReactNode; className?: string }) {
  return <thead className={clsx('border-b border-border text-xs font-semibold uppercase tracking-normal text-muted', className)}>{children}</thead>;
}

export function TableRow({ children, className }: { children: ReactNode; className?: string }) {
  return <tr className={clsx('border-b border-border/70 align-top last:border-b-0', className)}>{children}</tr>;
}

export function TableCell({ children, className, mono = false }: { children: ReactNode; className?: string; mono?: boolean }) {
  return <td className={clsx(mono ? 'px-3 py-2 font-mono text-xs' : 'px-3 py-2', className)}>{children}</td>;
}

export function TableHeaderCell({ children, className }: { children: ReactNode; className?: string }) {
  return <th className={clsx('px-3 py-2', className)}>{children}</th>;
}
