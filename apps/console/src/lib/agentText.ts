export function formatAgentText(text: string | null | undefined) {
  return String(text || '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .split('\n')
    .map((line) => line
      .replace(/^(\s*)#{1,6}\s+/, '$1')
      .replace(/^(\s*)[-*]\s+/, '$1')
      .replace(/^(\s*)\d+[.)]\s+/, '$1'))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function formatResponseSourceLabel(source: string | null | undefined) {
  switch (String(source || '').trim().toLowerCase()) {
    case 'model_gateway':
      return 'Model answer';
    case 'backend_context':
      return 'Database and rules';
    case 'rag_fallback':
      return 'RAG fallback';
    case 'workflow_engine':
      return 'Workflow engine';
    case 'error':
      return 'Error';
    default:
      return '';
  }
}
