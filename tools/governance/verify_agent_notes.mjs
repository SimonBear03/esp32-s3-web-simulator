#!/usr/bin/env node

import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const root = path.resolve(process.cwd(), 'agent_notes');
const lifecycles = new Set(['proposed', 'building', 'review', 'implemented', 'rejected']);
const classes = new Set(['feature', 'bug-fix', 'simplification', 'architecture', 'process', 'testing']);
const required = {
  proposed: ['Problem', 'Proposal', 'Alternatives considered', 'Acceptance criteria', 'Risks'],
  building: ['Problem', 'Proposal', 'Alternatives considered', 'Acceptance criteria', 'Risks'],
  review: ['Problem', 'Proposal', 'Alternatives considered', 'Acceptance criteria', 'Risks', 'Verification'],
  implemented: ['Problem', 'Decision', 'Alternatives considered', 'Consequences', 'Verification'],
  rejected: ['Problem', 'Proposal', 'Alternatives considered'],
};

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

const files = await walk(root);
const notes = files.filter((file) => file.endsWith('.md') && !file.endsWith('.zh.md') && path.basename(file) !== 'README.md');
const present = new Set(files);
let failed = false;

for (const file of notes.sort()) {
  const relative = path.relative(root, file);
  const [lifecycle, noteClass, filename] = relative.split(path.sep);
  const errors = [];
  const markdown = await readFile(file, 'utf8');
  const status = markdown.match(/^Status:\s*(.+)$/mu)?.[1]?.trim();
  const headings = [...markdown.matchAll(/^##\s+(.+)$/gmu)].map((match) => match[1].trim());
  if (!/^# Agent Note: .+\n\nStatus: .+\n/mu.test(markdown.slice(0, 300))) errors.push('invalid Agent Note header block');
  if (lifecycle === 'archived') {
    if (!classes.has(noteClass)) errors.push('invalid class');
    if (status !== 'implemented') errors.push('archive status must remain implemented');
    if (!/^Archived:\s*\d{4}-\d{2}-\d{2}$/mu.test(markdown)) errors.push('missing archive date');
  } else {
    if (!lifecycles.has(lifecycle)) errors.push('invalid lifecycle');
    if (!classes.has(noteClass)) errors.push('invalid class');
    if (lifecycle === 'rejected' ? !status?.startsWith('rejected — ') : status !== lifecycle) errors.push('status/path mismatch');
    const requiredHeadings = required[lifecycle] ?? [];
    for (const heading of requiredHeadings) if (!headings.includes(heading)) errors.push(`missing ## ${heading}`);
    const indexes = requiredHeadings.map((heading) => headings.indexOf(heading));
    if (indexes.every((index) => index >= 0) && indexes.some((index, position) => position > 0 && index <= indexes[position - 1])) errors.push('required sections are out of order');
    if (lifecycle === 'implemented') {
      for (const heading of ['Proposal', 'Plan', 'Migration plan', 'Acceptance criteria', 'Risks']) {
        if (headings.includes(heading)) errors.push(`implemented note contains ## ${heading}`);
      }
    }
  }
  if (!/^\d{4}-\d{2}-\d{2}-.+\.md$/u.test(filename ?? '')) errors.push('invalid filename');
  if (!markdown.startsWith('# Agent Note: ')) errors.push('missing Agent Note H1');
  const stem = file.slice(0, -3);
  if (!present.has(`${stem}.zh.md`)) errors.push('missing Chinese counterpart');
  else {
    const chinese = await readFile(`${stem}.zh.md`, 'utf8');
    const chineseStatus = chinese.match(/^Status:\s*(.+)$/mu)?.[1]?.trim();
    if (chineseStatus !== status) errors.push('Chinese status differs from English');
  }
  if (!present.has(`${stem}.i18n.yaml`)) errors.push('missing sidecar');
  if (errors.length) { failed = true; errors.forEach((error) => console.error(`${relative}: ${error}`)); }
  else console.log(`ok agent_notes/${relative}`);
}

if (!notes.length) console.log('ok no active Agent Notes');
if (failed) process.exit(1);
