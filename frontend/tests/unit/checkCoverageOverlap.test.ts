/**
 * Unit tests for scripts/check_coverage_overlap_frontend.js.
 *
 * The script is a repo-root CommonJS tool; we exercise it as a child process
 * with PP_OVERLAP_ROOT pointed at a per-test fixture root so it reads staged
 * Istanbul coverage-final.json reports and quality-thresholds.toml from there.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const SCRIPT = path.resolve(__dirname, '../../../scripts/check_coverage_overlap_frontend.js');

let root: string;

beforeEach(() => {
  root = mkdtempSync(path.join(tmpdir(), 'pp-overlap-'));
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

/** Stage one per-file coverage-final.json under <root>/logs/quality/... */
function stageReport(slug: string, file: string, coveredLines: number[]): void {
  const dir = path.join(root, 'logs', 'quality', 'frontend-coverage-per-file', slug);
  mkdirSync(dir, { recursive: true });
  const abs = path.join(root, file);
  const statementMap: Record<string, unknown> = {};
  const s: Record<string, number> = {};
  coveredLines.forEach((line, i) => {
    statementMap[i] = { start: { line, column: 0 }, end: { line, column: 1 } };
    s[i] = 1;
  });
  const report = { [abs]: { path: abs, statementMap, s, fnMap: {}, f: {}, branchMap: {}, b: {} } };
  writeFileSync(path.join(dir, 'coverage-final.json'), JSON.stringify(report));
}

function writeThresholds(body: string): void {
  const dir = path.join(root, 'config');
  mkdirSync(dir, { recursive: true });
  writeFileSync(path.join(dir, 'quality-thresholds.toml'), body);
}

function run(): { status: number; stdout: string; stderr: string } {
  try {
    const stdout = execFileSync('node', [SCRIPT], {
      env: { ...process.env, PP_OVERLAP_ROOT: root },
      encoding: 'utf8',
    });
    return { status: 0, stdout, stderr: '' };
  } catch (err) {
    const e = err as { status: number; stdout: string; stderr: string };
    return { status: e.status, stdout: e.stdout ?? '', stderr: e.stderr ?? '' };
  }
}

describe('check_coverage_overlap_frontend.js', () => {
  it('flags a line covered by two same-tier test files', () => {
    stageReport('unit__A', 'src/foo.ts', [10]);
    stageReport('unit__B', 'src/foo.ts', [10]);
    const { status, stdout } = run();
    expect(status).toBe(0); // no threshold set yet
    expect(stdout).toContain('1 intra-tier duplicate lines found');
  });

  it('does not flag cross-tier overlap', () => {
    stageReport('unit__A', 'src/foo.ts', [10]);
    stageReport('integration__B', 'src/foo.ts', [10]);
    const { stdout } = run();
    expect(stdout).toContain('0 intra-tier duplicate lines found');
  });

  it('exits 0 with a warning when the staging directory is missing', () => {
    const { status, stdout } = run();
    expect(status).toBe(0);
    expect(stdout).toContain('Run make check-coverage-overlap-frontend');
  });

  it('exits 0 with an info note when no threshold is set', () => {
    stageReport('unit__A', 'src/foo.ts', [10]);
    stageReport('unit__B', 'src/foo.ts', [10]);
    const { status, stdout } = run();
    expect(status).toBe(0);
    expect(stdout).toContain('No enforcement threshold set');
  });

  it('exits 1 when the count exceeds the configured threshold', () => {
    stageReport('unit__A', 'src/foo.ts', [10]);
    stageReport('unit__B', 'src/foo.ts', [10]);
    writeThresholds('[test-health]\nmax_intra_tier_duplicate_lines_frontend = 0\n');
    const { status, stderr } = run();
    expect(status).toBe(1);
    expect(stderr).toContain('exceeds threshold');
  });

  it('exits 0 when the count is within the configured threshold', () => {
    stageReport('unit__A', 'src/foo.ts', [10]);
    stageReport('unit__B', 'src/foo.ts', [10]);
    writeThresholds('[test-health]\nmax_intra_tier_duplicate_lines_frontend = 1\n');
    const { status, stdout } = run();
    expect(status).toBe(0);
    expect(stdout).toContain('within threshold');
  });
});
