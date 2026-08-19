// Copies the shared API fixtures into public/ so the mock client can fetch them
// over HTTP, exactly as it would fetch the real API. Runs on predev and prebuild.
// Source of truth stays data/seed/api-fixtures/ per docs/api-contract.md section 6.
import { cp, mkdir, readdir, writeFile } from 'node:fs/promises';
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

// Write an index of every fixture so the service worker can precache the lot.
//
// Without this, offline only works for districts the farmer happened to visit
// while online — the cache fills on demand. Precaching the whole set (under a
// megabyte) means the app answers for any supported district with the network
// off, which is the point of the feature and the thing a demo will test.
async function listJson(dir, prefix = '') {
  const entries = await readdir(dir, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    const rel = `${prefix}${entry.name}`;
    if (entry.isDirectory()) {
      out.push(...(await listJson(path.join(dir, entry.name), `${rel}/`)));
    } else if (entry.name.endsWith('.json') && entry.name !== 'index.json') {
      out.push(`/fixtures/${rel}`);
    }
  }
  return out;
}

const paths = (await listJson(dest)).sort();
await writeFile(path.join(dest, 'index.json'), JSON.stringify(paths, null, 2) + '\n');
console.log(`[sync-fixtures] Copied ${paths.length} fixture(s) and wrote index.json`);
