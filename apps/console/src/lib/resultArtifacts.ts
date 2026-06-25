import type { OutputItem, ResultSummary } from './types';

export function flattenOutputs(outputs: ResultSummary['outputs'], excludedKeys = new Set<string>()): OutputItem[] {
  const result: OutputItem[] = [];

  for (const [key, value] of Object.entries(outputs)) {
    if (excludedKeys.has(key)) continue;
    if (Array.isArray(value)) {
      result.push(...value);
    } else if (value && typeof value === 'object') {
      result.push(...flattenOutputs(value as ResultSummary['outputs'], excludedKeys));
    }
  }

  return result;
}

export function getReportArtifacts(outputs: ResultSummary['outputs']) {
  const reports = outputs.reports;
  const figures = outputs.figures;
  return [
    ...(Array.isArray(reports) ? reports : []),
    ...(Array.isArray(figures) ? figures : []),
  ];
}

export function isPreviewableFigure(artifact: OutputItem) {
  const relativePath = (artifact.relative_path || artifact.path || '').toLowerCase();
  const contentType = (artifact.content_type || '').toLowerCase();
  return (
    contentType.startsWith('image/') ||
    relativePath.endsWith('.svg') ||
    relativePath.endsWith('.png') ||
    relativePath.endsWith('.jpg') ||
    relativePath.endsWith('.jpeg') ||
    relativePath.endsWith('.webp')
  );
}

export function displayArtifactName(artifact: OutputItem, fallback = 'artifact') {
  const relativePath = artifact.relative_path || artifact.path || fallback;
  return relativePath.split('/').filter(Boolean).pop() || relativePath;
}

function encodeArtifactRoutePath(relativePath: string) {
  return relativePath.split('/').map(encodeURIComponent).join('/');
}

export function artifactUrl(taskId: number, artifact: OutputItem, apiBase: string) {
  if (artifact.download_url?.startsWith('http')) return artifact.download_url;
  if (artifact.download_url) return `${apiBase}${artifact.download_url}`;
  return `${apiBase}/tasks/${taskId}/artifacts/${encodeArtifactRoutePath(artifact.relative_path || artifact.path || '')}`;
}

export function groupArtifactsByFeature(artifacts: OutputItem[]) {
  return artifacts.reduce<Record<string, OutputItem[]>>((groups, artifact) => {
    const group = artifact.feature_group || artifact.output_type || 'other';
    groups[group] = groups[group] || [];
    groups[group].push(artifact);
    return groups;
  }, {});
}
