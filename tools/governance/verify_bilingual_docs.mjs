#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const root = process.cwd();

async function walk(directory) {
  let entries;
  try { entries = await readdir(directory, { withFileTypes: true }); }
  catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  const files = [];
  for (const entry of entries) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(target)));
    else files.push(target);
  }
  return files;
}

function pair(input) {
  let english = path.resolve(root, input);
  english = english.replace(/\.i18n\.yaml$/u, '.md').replace(/\.zh\.md$/u, '.md');
  if (!english.endsWith('.md')) english += '.md';
  const stem = english.slice(0, -3);
  return { english, chinese: `${stem}.zh.md`, sidecar: `${stem}.i18n.yaml` };
}

function hash(content) {
  const body = Buffer.from(content);
  return createHash('sha1').update(`blob ${body.length}\0`).update(body).digest('hex');
}

function signature(markdown) {
  const headings = [...markdown.matchAll(/^(#{1,6})\s+/gmu)].map((match) => match[1].length);
  const lists = markdown.split(/\r?\n/u).flatMap((line) => {
    if (/^\s*[-+*]\s+/u.test(line)) return ['u'];
    const ordered = line.match(/^\s*(\d+)[.)]\s+/u);
    return ordered ? [`o:${ordered[1]}`] : [];
  });
  const tables = markdown.split(/\r?\n/u).filter((line) => /^\s*\|.*\|\s*$/u.test(line)).map((line) => line.split('|').length - 2);
  const fences = [...markdown.matchAll(/^(```+|~~~+)([^\n]*)\n([\s\S]*?)^\1\s*$/gmu)].map((match) => `${match[1][0]}:${match[2].trim()}\n${match[3]}`);
  const links = [...markdown.matchAll(/\[[^\]]*\]\(([^)]+)\)/gu)].map((match) => match[1].replace(/\.zh\.md(?=($|#))/u, '.md'));
  return JSON.stringify({ headings, lists, tables, fences, links });
}

async function check(item, write) {
  const errors = [];
  let english;
  let chinese;
  try { english = await readFile(item.english, 'utf8'); } catch { errors.push('missing English file'); }
  try { chinese = await readFile(item.chinese, 'utf8'); } catch { errors.push('missing Chinese file'); }
  if (errors.length) return errors;
  const en = path.basename(item.english);
  const zh = path.basename(item.chinese);
  if (!english.includes(`[中文](${zh})`)) errors.push('missing Chinese switcher');
  if (!chinese.includes(`[English](${en})`)) errors.push('missing English switcher');
  if (signature(english) !== signature(chinese)) errors.push('structural mismatch');
  if (errors.length) return errors;
  const expected = `${en}: ${hash(english)}\n${zh}: ${hash(chinese)}\n`;
  if (write) await writeFile(item.sidecar, expected, 'utf8');
  else {
    let actual;
    try { actual = await readFile(item.sidecar, 'utf8'); } catch { errors.push('missing sidecar'); }
    if (actual !== undefined && actual !== expected) errors.push('stale sidecar');
  }
  return errors;
}

const args = process.argv.slice(2);
const write = args[0] === '--write';
const requested = write ? args.slice(1) : args;
if (write && requested.length === 0) {
  console.error('Usage: verify_bilingual_docs.mjs --write <pair...>');
  process.exit(2);
}
let items;
if (requested.length) items = requested.map(pair);
else {
  const sources = new Set([path.resolve(root, 'docs/architecture.md')]);
  for (const file of await walk(path.resolve(root, 'agent_notes'))) {
    if (file.endsWith('.md') && !file.endsWith('.zh.md')) sources.add(file);
    else if (file.endsWith('.zh.md') || file.endsWith('.i18n.yaml')) sources.add(pair(file).english);
  }
  items = [...sources].sort().map(pair);
}
let failed = false;
for (const item of items) {
  const errors = await check(item, write);
  const label = path.relative(root, item.english);
  if (errors.length) { failed = true; errors.forEach((error) => console.error(`${label}: ${error}`)); }
  else console.log(`${write ? 'recorded' : 'ok'} ${label}`);
}
if (failed) process.exit(1);
