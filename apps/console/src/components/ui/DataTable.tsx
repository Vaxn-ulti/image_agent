import type { ReactNode } from 'react';

type DataTableProps = {
  children: ReactNode;
  empty?: ReactNode;
  isEmpty?: boolean;
};

export function DataTable({ children, empty, isEmpty }: DataTableProps) {
  if (isEmpty) {
    return <div className="rounded-md border border-dashed border-border bg-panel p-4 text-sm text-muted">{empty || 'No records available.'}</div>;
  }

  return (
    <div className="scientific-scrollbar overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

export function TableHead({ children }: { children: ReactNode }) {
  return <thead className="border-b border-border text-xs font-semibold uppercase tracking-normal text-muted">{children}</thead>;
}

export function TableRow({ children }: { children: ReactNode }) {
  return <tr className="border-b border-border/70 align-top last:border-b-0">{children}</tr>;
}

export function TableCell({ children, mono = false }: { children: ReactNode; mono?: boolean }) {
  return <td className={mono ? 'px-3 py-2 font-mono text-xs' : 'px-3 py-2'}>{children}</td>;
}

export function TableHeaderCell({ children }: { children: ReactNode }) {
  return <th className="px-3 py-2">{children}</th>;
}
