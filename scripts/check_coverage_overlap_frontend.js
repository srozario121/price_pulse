#!/usr/bin/env node
/*
 * Frontend intra-tier coverage overlap detector.
 *
 * Reads the per-test-file Istanbul reports staged by
 * check_coverage_overlap_frontend.sh under
 * logs/quality/frontend-coverage-per-file/<tier>__<name>/coverage-final.json
 * and flags any source line covered by two or more test files of the SAME tier
 * (both tests/unit/ or both tests/integration/). Cross-tier overlap is not
 * flagged.
 *
 * NOTE: per-line attribution requires the Istanbul `coverage-final.json`
 * (vitest `json` reporter). `coverage-summary.json` only carries per-file
 * percentages, not line numbers, so it cannot support this check.
 *
 * Enforcement: if `[test-health] max_intra_tier_duplicate_lines_frontend` is set
 * in config/quality-thresholds.toml and the actual count exceeds it, exit 1.
 * If absent, print an info note and exit 0.
 *
 * Usage: node scripts/check_coverage_overlap_frontend.js
 */

'use strict';

const fs = require('fs');
const path = require('path');

// PP_OVERLAP_ROOT lets tests point the script at a fixture root; defaults to the
// repo root (scripts/ lives one level below it).
const REPO_ROOT = process.env.PP_OVERLAP_ROOT
  ? path.resolve(process.env.PP_OVERLAP_ROOT)
  : path.resolve(__dirname, '..');
const STAGING = path.join(REPO_ROOT, 'logs', 'quality', 'frontend-coverage-per-file');
const THRESHOLDS_PATH = path.join(REPO_ROOT, 'config', 'quality-thresholds.toml');

/** Minimal TOML reader for a single `key = <int>` under `[test-health]`. */
function readThreshold(key) {
  if (!fs.existsSync(THRESHOLDS_PATH)) return null;
  const text = fs.readFileSync(THRESHOLDS_PATH, 'utf8');
  const lines = text.split(/\r?\n/);
  let inSection = false;
  for (const raw of lines) {
    const line = raw.replace(/#.*$/, '').trim();
    if (/^\[.+\]$/.test(line)) {
      inSection = line === '[test-health]';
      continue;
    }
    if (!inSection) continue;
    const m = line.match(/^([A-Za-z0-9_]+)\s*=\s*(-?\d+)\s*$/);
    if (m && m[1] === key) return parseInt(m[2], 10);
  }
  return null;
}

/** Covered lines (Set<number>) per source file from one coverage-final.json. */
function coveredLinesByFile(reportPath) {
  const data = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  const result = new Map(); // sourceFile -> Set<lineNumber>
  for (const [file, entry] of Object.entries(data)) {
    if (!entry || !entry.statementMap || !entry.s) continue;
    const lines = new Set();
    // Use each executed statement's start line — this mirrors how Istanbul
    // derives line coverage from statement coverage, keeping the overlap metric
    // consistent with the reported coverage numbers.
    for (const [id, hits] of Object.entries(entry.s)) {
      if (hits > 0 && entry.statementMap[id] && entry.statementMap[id].start) {
        lines.add(entry.statementMap[id].start.line);
      }
    }
    if (lines.size > 0) result.set(file, lines);
  }
  return result;
}

function main() {
  if (!fs.existsSync(STAGING)) {
    console.log(
      'Run make check-coverage-overlap-frontend to generate per-file data'
    );
    process.exit(0);
  }

  const slugs = fs
    .readdirSync(STAGING, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);

  // sourceFile -> line -> tier -> Set<slug>
  const index = new Map();
  let reportsRead = 0;

  for (const slug of slugs) {
    const tier = slug.startsWith('unit__')
      ? 'unit'
      : slug.startsWith('integration__')
        ? 'integration'
        : null;
    if (tier === null) continue;
    const reportPath = path.join(STAGING, slug, 'coverage-final.json');
    if (!fs.existsSync(reportPath)) continue;
    reportsRead += 1;

    for (const [file, lines] of coveredLinesByFile(reportPath)) {
      const relFile = path.relative(REPO_ROOT, file);
      const byLine = index.get(relFile) || new Map();
      index.set(relFile, byLine);
      for (const line of lines) {
        const byTier = byLine.get(line) || new Map();
        byLine.set(line, byTier);
        const slugSet = byTier.get(tier) || new Set();
        byTier.set(tier, slugSet);
        slugSet.add(slug);
      }
    }
  }

  if (reportsRead === 0) {
    console.log(
      'Run make check-coverage-overlap-frontend to generate per-file data'
    );
    process.exit(0);
  }

  const duplicates = []; // {file, line, tier, a, b}
  for (const [file, byLine] of index) {
    for (const [line, byTier] of byLine) {
      for (const [tier, slugSet] of byTier) {
        if (slugSet.size >= 2) {
          // Sort so the reported example pair is stable across runs/platforms
          // (enumeration order is not guaranteed). Does not affect the count.
          const [a, b] = [...slugSet].sort();
          duplicates.push({ file, line, tier, a, b });
        }
      }
    }
  }

  duplicates.sort((x, y) => x.file.localeCompare(y.file) || x.line - y.line);

  if (duplicates.length > 0) {
    console.log(
      `\n${'source_file'.padEnd(40)} ${'line'.padStart(6)}  ${'tier'.padEnd(
        12
      )} ${'test_file_a'.padEnd(22)} test_file_b`
    );
    console.log(`${'-'.repeat(40)} ${'-'.repeat(6)}  ${'-'.repeat(12)} ${'-'.repeat(22)} ${'-'.repeat(22)}`);
    for (const d of duplicates) {
      console.log(
        `${d.file.padEnd(40)} ${String(d.line).padStart(6)}  ${d.tier.padEnd(
          12
        )} ${d.a.padEnd(22)} ${d.b}`
      );
    }
  }

  const filesAffected = new Set(duplicates.map((d) => d.file)).size;
  console.log(
    `\n${duplicates.length} intra-tier duplicate lines found across ${filesAffected} source files`
  );

  const threshold = readThreshold('max_intra_tier_duplicate_lines_frontend');
  if (threshold === null) {
    console.log('No enforcement threshold set — run baseline task first');
    process.exit(0);
  }
  if (duplicates.length > threshold) {
    console.error(
      `ERROR: Frontend intra-tier duplicate lines (${duplicates.length}) exceeds threshold (${threshold})`
    );
    process.exit(1);
  }
  console.log(
    `Frontend intra-tier duplicate lines (${duplicates.length}) within threshold (${threshold})`
  );
}

if (require.main === module) {
  main();
}
