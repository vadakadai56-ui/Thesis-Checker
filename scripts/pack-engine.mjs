// Packs the Python engine (engine/thesischeck/) into public/engine/thesischeck.zip.
// The worker downloads this one file and unpacks it into Pyodide's file system.
// Also writes public/engine/manifest.json (version + SHA-256), which the worker and
// the service worker use to know when the engine changed.
//
// Node has no built-in ZIP writer, so this file contains a tiny one (the ZIP format
// is simple: each file gets a header + compressed data, then a directory at the end).

import { createHash } from 'node:crypto';
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { crc32, deflateRawSync } from 'node:zlib';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE = join(ROOT, 'engine', 'thesischeck');
const OUT_DIR = join(ROOT, 'public', 'engine');

function listFiles(dir) {
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== '__pycache__') files.push(...listFiles(path));
    } else if (!entry.name.endsWith('.pyc')) {
      files.push(path);
    }
  }
  return files.sort(); // fixed order = identical zip every time
}

// 1980-01-01 00:00 in DOS format: a fixed date so the zip is reproducible.
const DOS_TIME = 0;
const DOS_DATE = 0x21;

function zip(entries) {
  const parts = [];
  const directory = [];
  let offset = 0;
  for (const { name, data } of entries) {
    const nameBytes = Buffer.from(name, 'utf8');
    const compressed = deflateRawSync(data, { level: 9 });
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); // "PK\3\4" local file header
    local.writeUInt16LE(20, 4); // version needed
    local.writeUInt16LE(0x0800, 6); // flags: UTF-8 names
    local.writeUInt16LE(8, 8); // method: deflate
    local.writeUInt16LE(DOS_TIME, 10);
    local.writeUInt16LE(DOS_DATE, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(compressed.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBytes.length, 26);
    parts.push(local, nameBytes, compressed);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0); // central directory entry
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt16LE(8, 10);
    central.writeUInt16LE(DOS_TIME, 12);
    central.writeUInt16LE(DOS_DATE, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(compressed.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(nameBytes.length, 28);
    central.writeUInt32LE(offset, 42);
    directory.push(central, nameBytes);
    offset += local.length + nameBytes.length + compressed.length;
  }
  const directorySize = directory.reduce((n, b) => n + b.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); // end of central directory
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(directorySize, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...parts, ...directory, end]);
}

const entries = listFiles(SOURCE).map((path) => ({
  // Paths inside the zip start with "thesischeck/" and always use forward slashes.
  name: ['thesischeck', ...relative(SOURCE, path).split(sep)].join('/'),
  data: readFileSync(path),
}));
const archive = zip(entries);
const api = readFileSync(join(SOURCE, 'api.py'), 'utf8');
const version = /ENGINE_VERSION = "([^"]+)"/.exec(api)?.[1] ?? '0.0.0';
const manifest = {
  version: 1,
  engineVersion: version,
  file: 'thesischeck.zip',
  sha256: createHash('sha256').update(archive).digest('hex'),
  bytes: archive.length,
  files: entries.length,
};
mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(join(OUT_DIR, 'thesischeck.zip'), archive);
writeFileSync(join(OUT_DIR, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(
  `pack-engine: ${entries.length} files -> public/engine/thesischeck.zip (${(archive.length / 1024).toFixed(0)} KB, engine ${version})`,
);
