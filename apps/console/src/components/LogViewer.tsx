export function LogViewer({ text }: { text: string }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-md border border-border bg-foreground/95 p-3 font-mono text-xs leading-relaxed text-background">
      {text || 'No logs available.'}
    </pre>
  );
}
