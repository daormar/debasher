// CRAP report of the frontend.
//
// Runs the vitest suite with V8 coverage, measures the cyclomatic complexity
// of every function of src/ with the TypeScript compiler, and combines both
// into the CRAP score (Change Risk Anti-Patterns) of each function:
//
//     CRAP(f) = comp(f)^2 * (1 - cov(f))^3 + comp(f)
//
// where comp(f) is the cyclomatic complexity of f and cov(f) the fraction of
// its statements that the tests execute. It is the same score that
// test/utils/crap_report.py gives for the Python code.
//
// The report has two parts:
//
// - Logic (every file but the views, the store included): the functions
//   whose score is above the threshold (30), as in the Python report: they
//   need tests, or a split when their complexity alone is above it.
// - Views (the .tsx files of components/ and of the top of src/): the
//   functions whose complexity is above a threshold of their own (10),
//   whatever their coverage. Views are rarely tested and would all score
//   high; what a high complexity there points to is logic that belongs in
//   adapters/ or store/, so they are ranked apart.
//
// Usage: node scripts/crap_report.mjs [--top N] [--threshold T]
//            [--view-complexity C]
//
// Run it from frontend/ (npm run crap). The report goes to standard output,
// with the summary line of vitest; the whole output of vitest goes to
// standard error only when the suite fails.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import ts from "typescript";

const FRONTEND_DIR = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const ROOT = path.dirname(FRONTEND_DIR);
const SRC_DIR = path.join(FRONTEND_DIR, "src");

function crapScore(complexity, coverageFraction) {
  return complexity ** 2 * (1 - coverageFraction) ** 3 + complexity;
}

// Runs the vitest suite with coverage and returns its exit status, its
// summary line and the coverage data (the "coverage-final.json" of istanbul,
// keyed by absolute file path).
function runCoverage() {
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), "crap_report."));
  try {
    const vitest = spawnSync(
      path.join(FRONTEND_DIR, "node_modules", ".bin", "vitest"),
      [
        "run",
        "--coverage.enabled",
        "--coverage.reporter=json",
        `--coverage.reportsDirectory=${workDir}`,
        "--coverage.include=src/**/*.{ts,tsx}",
      ],
      { cwd: FRONTEND_DIR, encoding: "utf8", env: { ...process.env, NO_COLOR: "1" } },
    );
    if (vitest.error) throw vitest.error;
    if (vitest.status !== 0) process.stderr.write(vitest.stdout + vitest.stderr);
    const summary = (vitest.stdout.match(/^\s*Tests\s+(.*)$/m) ?? [])[1] ?? "";
    const coverageFile = path.join(workDir, "coverage-final.json");
    const coverage = fs.existsSync(coverageFile)
      ? JSON.parse(fs.readFileSync(coverageFile, "utf8"))
      : {};
    return { status: vitest.status, summary: summary.trim(), coverage };
  } finally {
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

// Source files of src/, without tests, type declarations and the test setup.
function sourceFiles(dir) {
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (full !== path.join(SRC_DIR, "test")) files.push(...sourceFiles(full));
    } else if (/\.tsx?$/.test(entry.name) && !/\.(test|d)\.tsx?$/.test(entry.name)) {
      files.push(full);
    }
  }
  return files.sort();
}

// A view is a .tsx file of components/ or of the top of src/ (App, main).
// The store is a .tsx file too, but it is logic.
function isView(file) {
  return (
    file.endsWith(".tsx") &&
    (path.dirname(file) === SRC_DIR || file.startsWith(path.join(SRC_DIR, "components") + path.sep))
  );
}

function isFunction(node) {
  return (
    ts.isFunctionDeclaration(node) ||
    ts.isFunctionExpression(node) ||
    ts.isArrowFunction(node) ||
    ts.isMethodDeclaration(node) ||
    ts.isConstructorDeclaration(node) ||
    ts.isGetAccessorDeclaration(node) ||
    ts.isSetAccessorDeclaration(node)
  );
}

const DECISION_OPERATORS = new Set([
  ts.SyntaxKind.AmpersandAmpersandToken,
  ts.SyntaxKind.BarBarToken,
  ts.SyntaxKind.QuestionQuestionToken,
  ts.SyntaxKind.AmpersandAmpersandEqualsToken,
  ts.SyntaxKind.BarBarEqualsToken,
  ts.SyntaxKind.QuestionQuestionEqualsToken,
]);

// Cyclomatic complexity of a function: one plus its decision points (the
// same ones the ESLint "complexity" rule counts), leaving out those of the
// functions nested in it, which are measured on their own.
function complexity(fn) {
  let count = 1;
  const visit = (node) => {
    if (isFunction(node)) return;
    if (
      ts.isIfStatement(node) ||
      ts.isConditionalExpression(node) ||
      ts.isForStatement(node) ||
      ts.isForInStatement(node) ||
      ts.isForOfStatement(node) ||
      ts.isWhileStatement(node) ||
      ts.isDoStatement(node) ||
      ts.isCatchClause(node) ||
      ts.isCaseClause(node) ||
      (ts.isBinaryExpression(node) && DECISION_OPERATORS.has(node.operatorToken.kind))
    ) {
      count += 1;
    }
    ts.forEachChild(node, visit);
  };
  if (fn.body) ts.forEachChild(fn.body, visit);
  for (const p of fn.parameters) ts.forEachChild(p, visit);
  return count;
}

// A readable name for a function: its own, or that of what it is assigned
// to, or the call or the JSX attribute it is passed to ("useEffect(...)",
// "onClick").
function functionName(fn) {
  if (ts.isConstructorDeclaration(fn)) return "constructor";
  if (fn.name) return fn.name.getText();
  let parent = fn.parent;
  while (ts.isParenthesizedExpression(parent) || ts.isAsExpression(parent)) {
    parent = parent.parent;
  }
  if (
    ts.isVariableDeclaration(parent) ||
    ts.isPropertyAssignment(parent) ||
    ts.isPropertyDeclaration(parent)
  ) {
    return parent.name.getText();
  }
  if (ts.isJsxExpression(parent) && ts.isJsxAttribute(parent.parent)) {
    return parent.parent.name.getText();
  }
  if (ts.isCallExpression(parent)) {
    if (ts.isVariableDeclaration(parent.parent)) return parent.parent.name.getText();
    const callee = parent.expression;
    const calleeName = ts.isPropertyAccessExpression(callee)
      ? callee.name.getText()
      : callee.getText();
    return `${calleeName}(...)`;
  }
  return "<anonymous>";
}

// Every function of a source file, as { node, name }, with its
// name qualified by the functions and classes around it.
function functionsOf(sourceFile) {
  const found = [];
  const visit = (node, prefix) => {
    if (isFunction(node)) {
      const name = prefix + functionName(node);
      found.push({ node, name });
      ts.forEachChild(node, (child) => visit(child, `${name}.`));
    } else if (ts.isClassDeclaration(node) && node.name) {
      ts.forEachChild(node, (child) => visit(child, `${prefix}${node.name.text}.`));
    } else {
      ts.forEachChild(node, (child) => visit(child, prefix));
    }
  };
  visit(sourceFile, "");
  return found;
}

// Istanbul positions: line from 1, column from 0.
function position(sourceFile, pos) {
  const { line, character } = sourceFile.getLineAndCharacterOfPosition(pos);
  return { line: line + 1, column: character };
}

function before(a, b) {
  return a.line < b.line || (a.line === b.line && a.column <= b.column);
}

// Rows { crap, complexity, coverage, name, file, line } of every function of
// a source file. Each statement counts for the innermost function that holds
// it; a function with no statement of its own (an arrow returning an
// expression) is covered when the coverage data saw it called.
function rowsOf(file, fileCoverage) {
  const sourceFile = ts.createSourceFile(
    file,
    fs.readFileSync(file, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const functions = functionsOf(sourceFile).map((f) => ({
    ...f,
    start: position(sourceFile, f.node.getStart()),
    end: position(sourceFile, f.node.getEnd()),
    statements: 0,
    executed: 0,
  }));
  const innermost = (at) => {
    let best = null;
    for (const f of functions) {
      if (before(f.start, at) && before(at, f.end) && (!best || before(best.start, f.start))) {
        best = f;
      }
    }
    return best;
  };
  if (fileCoverage) {
    for (const [id, loc] of Object.entries(fileCoverage.statementMap)) {
      const f = innermost(loc.start);
      if (!f) continue;
      f.statements += 1;
      if (fileCoverage.s[id] > 0) f.executed += 1;
    }
  }
  const calls = new Map();
  if (fileCoverage) {
    for (const [id, fn] of Object.entries(fileCoverage.fnMap)) {
      calls.set(`${fn.loc.start.line}:${fn.loc.start.column}`, fileCoverage.f[id]);
    }
  }
  return functions.map((f) => {
    let fraction;
    if (f.statements > 0) {
      fraction = f.executed / f.statements;
    } else {
      const body = position(sourceFile, (f.node.body ?? f.node).getStart());
      const called =
        calls.get(`${body.line}:${body.column}`) ??
        calls.get(`${f.start.line}:${f.start.column}`) ??
        0;
      fraction = called > 0 ? 1 : 0;
    }
    const cc = complexity(f.node);
    return {
      crap: crapScore(cc, fraction),
      complexity: cc,
      coverage: fraction,
      name: f.name,
      file,
      line: f.start.line,
    };
  });
}

function printRows(rows) {
  if (rows.length === 0) return;
  console.log();
  console.log(`${"CRAP".padStart(7)} ${"CC".padStart(4)} ${"cov".padStart(5)}  function`);
  for (const r of rows) {
    console.log(
      `${r.crap.toFixed(1).padStart(7)} ${String(r.complexity).padStart(4)} ` +
        `${(r.coverage * 100).toFixed(0).padStart(4)}%  ` +
        `${r.name}  (${path.relative(ROOT, r.file)}:${r.line})`,
    );
  }
}

function main() {
  const { values } = parseArgs({
    options: {
      threshold: { type: "string", default: "30" },
      "view-complexity": { type: "string", default: "10" },
      top: { type: "string" },
    },
  });
  const threshold = Number(values.threshold);
  const viewComplexity = Number(values["view-complexity"]);
  const top = values.top === undefined ? undefined : Number(values.top);

  const { status, summary, coverage } = runCoverage();
  const rows = sourceFiles(SRC_DIR).flatMap((file) => rowsOf(file, coverage[file]));

  const logic = rows.filter((r) => !isView(r.file)).sort((a, b) => b.crap - a.crap);
  const flagged = logic.filter((r) => r.crap > threshold);
  const views = rows
    .filter((r) => isView(r.file))
    .sort((a, b) => b.complexity - a.complexity || b.crap - a.crap);
  const complex = views.filter((r) => r.complexity > viewComplexity);

  console.log(`CRAP report of ${path.relative(ROOT, SRC_DIR)} (tests: vitest)`);
  console.log(`vitest: ${summary}`);
  if (status !== 0) {
    console.log(
      `WARNING: vitest exited with status ${status}, so the coverage below ` +
        "may be lower than the real one",
    );
  }
  console.log();
  console.log(`Logic: ${logic.length} functions, ${flagged.length} above ${threshold}`);
  printRows(top === undefined ? flagged : logic.slice(0, top));
  console.log();
  console.log(
    `Views: ${views.length} functions, ${complex.length} ` +
      `with complexity above ${viewComplexity}`,
  );
  printRows(top === undefined ? complex : views.slice(0, top));
}

main();
