export function redactEvidenceText(value: string) {
  return value
    .replace(/[A-Za-z]:[\\/][^\s"']+/g, '[redacted-host-path]')
    .replace(/\/(?:home|Users|mnt|data|tmp|var)\/[^\s"']+/g, '[redacted-host-path]')
    .replace(/(^|[\s`"'([{])data[\\/]+projects[\\/]+[^\s`"',)\]}]+/g, '$1[redacted-host-path]')
    .replace(/sk-[A-Za-z0-9._-]+/g, '[redacted-secret]')
    .replace(/((?:OPENAI|DEEPSEEK|IMAGE_AGENT_SUDO)_?[A-Z_]*\s*[:=]\s*)[^\s"',}]+/gi, '$1[redacted-secret]');
}

export function safeEvidenceJson(value: unknown) {
  return redactEvidenceText(JSON.stringify(value, null, 2));
}
