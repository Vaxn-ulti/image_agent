import type { Task } from './types';

export const queryKeys = {
  deployment: ['deployment'] as const,
  health: ['health'] as const,
  inventory: (projectId: number, uploadSessionId: number) => ['inventory', projectId, uploadSessionId] as const,
  logs: (taskId: number) => ['logs', taskId] as const,
  outputs: (taskId: number) => ['outputs', taskId] as const,
  project: (projectId: number) => ['project', projectId] as const,
  projects: ['projects'] as const,
  ragStatus: ['rag-status'] as const,
  resultContract: ['result-contract'] as const,
  resultSummary: (taskId: number) => ['result-summary', taskId] as const,
  runtime: ['runtime'] as const,
  series: (projectId: number) => ['series', projectId] as const,
  task: (taskId: number) => ['task', taskId] as const,
  tasks: (projectId: number) => ['tasks', projectId] as const,
  workflows: ['workflows'] as const,
};

export function hasActiveTasks(tasks: Task[] | undefined) {
  return Boolean(tasks?.some((task) => task.status === 'queued' || task.status === 'running'));
}
