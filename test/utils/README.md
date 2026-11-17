# Code analysis tools

Reports that point to where the code most needs tests or a refactoring.
None of them is part of `make check`: they are reports, not tests, and
nothing fails when a function scores high. Each one is run from the top of
the project with its `make` target, or directly with the options its
`--help` describes.

| Target | Script | Measures | Needs |
|---|---|---|---|
| `make crap` | `crap_report.py`, `frontend/scripts/crap_report.mjs` | CRAP score of the Python code and of the frontend | the virtual environment of the API with `api/requirements-dev.txt`, and npm |
| `make bash-complexity` | `bash_complexity.py` | complexity of the Bash functions of the engine | Python 3 |
| `make hotspots` | `hotspots.py` | files both complex and often changed, in every language | Python 3, git |
| `make coupling` | `coupling.py` | files that change together in the same commits | Python 3, git |
| `make module-depth` | `module_depth.py` | depth of the modules: code against the cost of their interface | Python 3 |

## CRAP score

The CRAP score (Change Risk Anti-Patterns) of a function weighs its
cyclomatic complexity against its test coverage:

    CRAP(f) = comp(f)^2 * (1 - cov(f))^3 + comp(f)

Above 30, a function is too complex for how little it is tested. With full
coverage the score equals the complexity, so a function whose complexity is
above 30 stays above the threshold however well it is tested: only splitting
it helps.

`crap_report.py` runs a pytest suite under coverage and measures the
complexity with radon; `make crap` runs it on the API and on the Python part
of the engine. The frontend has a report of its own, `npm run crap` (see
`frontend/README.md`), which `make crap` runs next. The engine tests that run
the real `debasher_exec` are only measured with `DEBASHER_RUN_CHAOS_TEST=1`.

## Complexity of the Bash functions

Bash has no CRAP score here, since nothing measures its coverage, but the
complexity of a function says on its own when it is worth splitting.
`bash_complexity.py` lists, for every function of `engine/*.sh` whose
complexity is above 10 (`--top N` for the N most complex instead):

- **CC**: the cyclomatic complexity, one plus the decision points (`if`,
  `elif`, loops, `case` items but a final `*)`, `&&` and `||`);
- **lines** and **depth**: the size of the body and its deepest nesting;
- **tests**: how many files of `test/engine/` name the function. It counts
  direct mentions only, so 0 means that no test calls it directly, not that
  no test reaches it.

Its parser follows the style of the engine (`name()`, a function ending at
the `}` with the indentation of its start) rather than the whole Bash
grammar: enough to rank functions, not to measure them exactly.

## Hotspots

A complex file that nobody touches is a latent risk; a complex file that
changes all the time is where bugs concentrate and where a refactoring pays
back most. `hotspots.py` ranks the source files of `engine/`, `api/` and
`frontend/src/` by the number of commits that changed them in the last year
(`--since` for another period; renames are followed) times their
indentation complexity: the sum over their lines of code of the
indentation level, which grows with size and nesting and does not depend on
the language. Tests are left out unless `--include-tests` is given.

It works at the level of files. For the functions of a hotspot, look at the
other two reports.

## Change coupling

Two files that keep changing in the same commits depend on each other,
whether or not the code says so. `coupling.py` counts, for every pair of
source files of `engine/`, `api/` and `frontend/src/`, the commits of the
last year that changed both (**shared**; `--since` for another period,
renames are followed, as in the hotspots) and its **degree**: shared over
the mean of the commits of each file, as a percentage. At 100, neither file
ever changes without the other.

The measure is one of coupling; it reads as one of cohesion through where
the two files lie, the **span** of the pair:

- `dir`: same directory. Files that change together inside a module are
  what a cohesive module looks like.
- `part`: same part of the code (engine, api, frontend), different
  directory.
- `cross`: different parts of the code. A responsibility spread over
  several places, or an implicit contract between them (the API and its
  client in the frontend, for instance): the pairs worth looking at.
- `test`: a test and a file that is not one, which is expected. Tests are
  left out unless `--include-tests` is given.

`--span` (which may be repeated) lists only the pairs of a span, for
instance `--span cross --span part`, since the engine is a single directory
and its `dir` pairs fill the first rows otherwise. To leave out noise, a
pair is listed with at least 5 shared commits (`--min-shared`), a degree of
at least 30% (`--min-degree`) and 5 commits of each file (`--min-revs`),
and commits that changed more than 30 files of the report
(`--max-changeset`), such as a mass rename or reformatting, are not
counted.

The report ends with the **sum of coupling** of each file: for every commit
that changed it, how many other files the commit also changed. A file with a
high sum drags changes elsewhere; crossed with the hotspots, it tells whether
a hotspot also spreads its changes.

## Depth of the modules

A deep module, in the sense of John Ousterhout (*A Philosophy of Software
Design*), hides a lot of implementation behind a small interface; a shallow
one is almost all interface, and its callers pay for what it saves them.
`module_depth.py` weighs the two for every file of the Bash library of the
engine (`engine/debasher_lib_*.sh`) and of its Python runtime library
(`engine/debasher_runtime_*.py`), or of the files it is given. Bash and
Python modules are reported apart, from the shallowest one:

- **code**: the lines of code of the module, without blank lines, comments
  or docstrings. It stands for what the module implements.
- **names**: the functions of the module (in Python, also its classes) that
  another file uses. The interface is what other files use, not what the
  names say: a function with a leading `_` that another file calls is
  interface all the same, and one without it that nobody calls is not.
- **params**: the parameters of those names, since a function that takes
  four costs its caller more than one that takes none. In Bash they are the
  positional parameters that the body reads, plus one if it takes `"$@"`.
  A Python class adds the parameters of its constructor and, for each public
  method, one plus its parameters.
- **state**: the variables of the module that other files share and that
  some function writes. In Bash, the globals: variables in capitals,
  declared at the top level or with `declare -g`. In Python, the module
  variables that a function rebinds with `global`. Shared state couples
  modules more than any call, so it counts as interface.
- **const**: the shared variables that no function writes. They are shown,
  but not counted: a constant costs its reader little.
- **I**: the cost of the interface, names + params + state.
- **depth**: code / I. A low depth is a shallow module. A module that no
  other file uses shows `-`.

Who uses a module are the other modules of the report and the clients: the
Bash or Python files under `engine`, `api`, `data` and `sdk` (`--clients`
for others). Tests are not clients, nor are the installed copies under
`share` and `lib`. The last row of each report takes all the modules as a
single one, whose interface is what the clients use of it: the depth of the
library as a whole, against which its files compare. With `--clients
data/programs data/webui_programs`, it is the interface that the authors of
modules see. `-v` lists the names and the state of each module.

The measure is a heuristic, as Ousterhout's own notion is: lines of code
stand for functionality, and the informal part of an interface (the order
of the calls, the files expected on disk) is not seen. Its parsers are line
based for Bash (the one of the complexity report) and use `ast` for Python.
It ranks modules to look at; it does not grade them.
