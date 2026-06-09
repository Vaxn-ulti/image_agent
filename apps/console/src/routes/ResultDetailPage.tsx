import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ResultStudioLayout } from '../components/results/ResultStudioLayout';
import { api, getApiBase } from '../lib/api';
import { queryKeys } from '../lib/query';

export function ResultDetailPage() {
  const taskId = Number(useParams().taskId);
  const { data: summary, error, isLoading } = useQuery({ enabled: Boolean(taskId), queryFn: () => api.getResultSummary(taskId), queryKey: queryKeys.resultSummary(taskId) });

  if (isLoading) return <p className="text-sm text-muted">Loading result summary...</p>;
  if (error) return <p className="text-sm text-danger">{error instanceof Error ? error.message : 'Result summary unavailable'}</p>;
  if (!summary) return null;

  return <ResultStudioLayout apiBase={getApiBase()} summary={summary} />;
}
