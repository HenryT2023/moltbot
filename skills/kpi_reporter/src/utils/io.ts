/**
 * 文件 I/O 工具
 */

import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  existsSync,
  readdirSync,
  copyFileSync,
} from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { parse as parseYaml } from 'yaml';

export function ensureDir(dirPath: string): void {
  if (!existsSync(dirPath)) {
    mkdirSync(dirPath, { recursive: true });
  }
}

export function readYaml<T>(filePath: string): T {
  const content = readFileSync(filePath, 'utf-8');
  return parseYaml(content) as T;
}

export function writeJson(filePath: string, data: unknown): void {
  ensureDir(dirname(filePath));
  writeFileSync(filePath, JSON.stringify(data, null, 2));
}

export function readJson<T>(filePath: string): T {
  const content = readFileSync(filePath, 'utf-8');
  return JSON.parse(content) as T;
}

export function writeText(filePath: string, content: string): void {
  ensureDir(dirname(filePath));
  writeFileSync(filePath, content);
}

export function listFiles(dirPath: string, pattern?: RegExp): string[] {
  if (!existsSync(dirPath)) {
    return [];
  }

  const files = readdirSync(dirPath);
  const filtered = pattern ? files.filter((f) => pattern.test(f)) : files;
  return filtered.map((f) => join(dirPath, f));
}

export function copyFile(src: string, dest: string): void {
  ensureDir(dirname(dest));
  copyFileSync(src, dest);
}

export function generateRunId(): string {
  const now = new Date();
  const datePart = now.toISOString().slice(0, 10).replace(/-/g, '');
  const timePart = now.toISOString().slice(11, 19).replace(/:/g, '');
  const randomPart = Math.random().toString(36).slice(2, 8);
  return `${datePart}_${timePart}_${randomPart}`;
}

export function getBaseDir(): string {
  // 获取 skill 根目录
  const currentFile = new URL(import.meta.url).pathname;
  return join(dirname(currentFile), '..', '..');
}

export function getRunsDir(): string {
  const envDir = process.env.KPI_REPORTER_OUTPUT_DIR;
  if (envDir) {
    return envDir;
  }
  return join(getBaseDir(), 'runs');
}
