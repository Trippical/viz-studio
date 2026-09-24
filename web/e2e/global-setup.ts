import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export default function globalSetup(): void {
  const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  execSync('npm run build', { cwd: web, stdio: 'inherit', shell: process.platform === 'win32' ? 'cmd.exe' : '/bin/sh' });
}
