# Frontend (React Flow)

Web interface for the project, built with Vite + React + @xyflow/react.

## Development

```bash
npm install
npm run dev
```

## Production build

Normally invoked from the top-level project `make`, but it can also be
run manually:

```bash
npm run build
```

## CRAP report

```bash
npm run crap
```

runs the vitest suite with coverage and weighs the cyclomatic complexity of
every function of `src/` against its test coverage (its CRAP score). The
report lists the logic functions (everything but the views, the store
included) whose score is above 30, and apart from them the functions of the
views (the `.tsx` files of `components/` and of the top of `src/`) whose
complexity is above 10: in a view, a high complexity points to logic that
belongs in `adapters/` or `store/`. See `scripts/crap_report.mjs` for the
details, and `make crap` at the top of the project for the report of the
Python code too.
