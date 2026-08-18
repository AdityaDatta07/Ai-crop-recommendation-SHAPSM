// Copies the shared API fixtures into public/ so the mock client can fetch them
// over HTTP, exactly as it would fetch the real API. Runs on predev and prebuild.
// Source of truth stays data/seed/api-fixtures/ per docs/api-contract.md section 6.
import { cp, mkdir, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, '../../../data/seed/api-fixtures');
const dest = path.resolve(here, '../public/fixtures');

if (!existsSync(src)) {
  console.error(`[sync-fixtures] Source not found: ${src}`);
  process.exit(1);
}

await mkdir(dest, { recursive: true });
await cp(src, dest, { recursive: true });
const files = await readdir(dest);
console.log(`[sync-fixtures] Copied ${files.length} fixture(s) to public/fixtures`);
