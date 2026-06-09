import { Brain } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { api } from '../lib/api';

export function LoginPage() {
  const navigate = useNavigate();
  const [error, setError] = useState('');

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const form = new FormData(event.currentTarget);
    try {
      await api.login(String(form.get('username') || ''), String(form.get('password') || ''));
      navigate('/projects');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <form className="w-full max-w-sm rounded-lg border border-border bg-panel p-6 shadow-hairline" onSubmit={onSubmit}>
        <div className="mb-6 flex items-center gap-2 text-base font-semibold">
          <Brain className="h-5 w-5 text-accent" />
          Brain Image Agent Console
        </div>
        <label className="mb-3 block text-sm font-medium">
          Username
          <Input className="mt-1" defaultValue="demo" name="username" />
        </label>
        <label className="mb-4 block text-sm font-medium">
          Password
          <Input className="mt-1" defaultValue="demo" name="password" type="password" />
        </label>
        <Button className="w-full" variant="primary">
          Connect
        </Button>
        {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      </form>
    </main>
  );
}
