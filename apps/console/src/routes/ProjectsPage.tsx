import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderPlus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const { data: projects = [], error, isLoading } = useQuery({ queryFn: api.listProjects, queryKey: queryKeys.projects });
  const createProject = useMutation({
    mutationFn: api.createProject,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  });

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    createProject.mutate({ description: String(form.get('description') || ''), name: String(form.get('name') || '') });
    event.currentTarget.reset();
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <PageHeader description="Select a project or create a workspace for a new imaging dataset." eyebrow="Workspace" title="Projects" />
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Panel>
          <PanelHeader>
            <PanelTitle>Create project</PanelTitle>
            <FolderPlus className="h-4 w-4 text-muted" />
          </PanelHeader>
          <PanelBody>
            <form className="space-y-3" onSubmit={onSubmit}>
              <label className="block text-sm font-medium">
                Project name
                <Input className="mt-1" name="name" required />
              </label>
              <label className="block text-sm font-medium">
                Description
                <Input className="mt-1" name="description" />
              </label>
              <Button disabled={createProject.isPending} variant="primary">
                Create project
              </Button>
            </form>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader>
            <PanelTitle>Recent projects</PanelTitle>
          </PanelHeader>
          <PanelBody>
            {isLoading ? <p className="text-sm text-muted">Loading projects...</p> : null}
            {error ? <p className="text-sm text-danger">{error instanceof Error ? error.message : 'Could not load projects'}</p> : null}
            <div className="space-y-2">
              {projects.map((project) => (
                <Link className="block rounded-md border border-border bg-background p-3 hover:border-accent/40" key={project.id} to={`/projects/${project.id}/dashboard`}>
                  <div className="text-sm font-medium">{project.name}</div>
                  <div className="mt-1 text-xs text-muted">{project.description || 'No description'}</div>
                </Link>
              ))}
            </div>
          </PanelBody>
        </Panel>
      </div>
    </main>
  );
}
