import { ExternalLink } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import type { OutputItem } from '../../lib/types';

export function artifactRelativePath(artifact: OutputItem, fallback = '') {
  if (artifact.relative_path || artifact.path) return artifact.relative_path || artifact.path || fallback;
  const downloadUrl = artifact.download_url || '';
  const marker = '/artifacts/';
  const markerIndex = downloadUrl.indexOf(marker);
  if (markerIndex >= 0) return decodeURIComponent(downloadUrl.slice(markerIndex + marker.length));
  return fallback;
}

function useArtifactObjectUrl(taskId: number, relativePath: string) {
  const [objectUrl, setObjectUrl] = useState('');

  useEffect(() => {
    let active = true;
    let createdUrl = '';
    if (!relativePath) {
      setObjectUrl('');
      return undefined;
    }
    api.getArtifactUrl(taskId, relativePath).then((blob) => {
      if (!active) return;
      createdUrl = URL.createObjectURL(blob);
      setObjectUrl(createdUrl);
    }).catch(() => {
      if (active) setObjectUrl('');
    });
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [relativePath, taskId]);

  return objectUrl;
}

type AuthenticatedArtifactImageLinkProps = {
  alt: string;
  className?: string;
  relativePath: string;
  taskId: number;
};

export function AuthenticatedArtifactImageLink({ alt, className, relativePath, taskId }: AuthenticatedArtifactImageLinkProps) {
  const objectUrl = useArtifactObjectUrl(taskId, relativePath);

  return (
    <a className="block" href={objectUrl || undefined} rel="noreferrer" target="_blank">
      <img alt={alt} className={className} loading="lazy" src={objectUrl} />
    </a>
  );
}

type AuthenticatedArtifactOpenButtonProps = {
  className?: string;
  relativePath: string;
  taskId: number;
};

export function AuthenticatedArtifactOpenButton({ className, relativePath, taskId }: AuthenticatedArtifactOpenButtonProps) {
  async function openArtifact() {
    const blob = await api.getArtifactUrl(taskId, relativePath);
    const objectUrl = URL.createObjectURL(blob);
    window.open(objectUrl, '_blank', 'noopener,noreferrer');
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  }

  return (
    <button className={className} onClick={openArtifact} type="button">
      Open <ExternalLink className="h-3 w-3" />
    </button>
  );
}
