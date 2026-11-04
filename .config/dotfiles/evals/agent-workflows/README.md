# agent-workflows — relocated Git-pilot evaluation project (dotfiles)

Relocated 2026-11-03 (P0.2) from
`/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/`
(portable closure only; see `MIGRATION` notes below and
`.config/dotfiles/docs/plans/2026-11-02-dotfiles-pr-trace-remediation.md`).

Basic Git-task END-STATE pilot: return to `main` and fast-forward it to
`origin/main`, preserving `feature/keep-history` and the untracked user
file; no cleanup, commit, push, or review. Deterministic final-state
verifier; `procedure_attempt_coverage: not_measured`.

**The only executed path in the SOURCE project was the native Harbor
ORACLE run (no model).** Latest executed receipt remains at the SOURCE,
not here: `harbor/runs/oracle-20261027c` at
`/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/`
(2026-10-27, mean_reward 1.0, 1 case, cost/tokens NULL). It is
**historical wiring-only evidence** for the source project — this
destination project has NOT run it. The future agent-model run
(opencode + model) is NOT RUN and NOT READY.

**Known limitation preserved:** the pinned stock Harbor OpenCode agent
is **1.19.4** (official npm package); the host orchestrator stack is
OpenCode **2.1.4**. The 1.19.4-vs-2.x gap is recorded, out of scope for
this migration, and not fixed here.

## Layout

- `eval.git.yaml` — native Harbor config (renamed from source
  `eval.harbor.yaml`; the packaged case's `config_chain` matches).
- `git_pilot_fixture.py` — shared deterministic fixture/verifier library
  (project root; imported by `harbor/` tooling and tests).
- `harbor/` — tooling only: `git_pilot_package.py` (task-package
  generator), `verifier.py` (in-image final-state oracle),
  `README-operator.md` (operator runbook), `image/Containerfile` +
  `image/bin/verify.sh` (trial image recipe; the ~211 MB opencode
  binary and vendored wrapper/lib copies are NOT tracked — the
  generator re-vendors from canonical sources).
- `cases/return-main-no-cleanup-v1/` — flat case root. The generated
  package was produced (P0.3, 2026-11-03) via the relocated generator;
  the whole package is a generated runtime payload and stays git-ignored
  (see `.gitignore`). **On a fresh clone it does not exist** — see
  "Fresh-clone bootstrap" below.
- `tests/test_git_pilot_harbor.py` — relocated original suite (62
  tests; see Test interpreter below).
- `tests/p03_migration_proof.py` — offline migration proof (typed
  config/validator/native Task load + verifier positive/negative;
  13 checks).
- `runtime-lock.json`, `runtime-lock-pypi.txt` — **historical**
  environment/pin provenance recorded at the SOURCE project
  (harness 1.57.1 @ `b041d5a6…`, Harbor 0.25.0, image digests, oracle
  receipts). Absolute paths inside are historical labels of the source
  environment, NOT active configuration of this project and NOT proof
  of fresh-build reproducibility.

## Fresh-clone bootstrap (caveats)

A fresh clone of this project is **not** immediately runnable:

1. **Generated case package is absent** (git-ignored). Regenerate it:
   `python3 harbor/git_pilot_package.py --out cases` (generator refuses
   to overwrite; requires the `sandbox-git` wrapper, see below).
2. **`sandbox-git` wrapper** must exist at `~/.local/bin/sandbox-git`
   (or `AGENT_WORKFLOWS_SANDBOX_GIT`); the generator vendors it into
   `harbor/image/bin/` (git-ignored copy).
3. **Trial image, venv, harness checkout and the ~211 MB opencode
   binary are untracked environment assets** — see
   `harbor/README-operator.md` §2/§4 for the pinned versions, digests
   and the fresh-machine re-fetch procedure.
4. **Offline validation** (no run needed): follow "Running the offline
   unit tests" below and `tests/p03_migration_proof.py` — both work
   once the case package from step 1 exists.

## Running the offline unit tests

The suite needs the pinned Harbor 0.25.0 SDK (from the historical
source environment) supplied **externally** via
`AGENT_WORKFLOWS_TEST_PYTHON` — never hardcoded. Use `unittest discover`
with that pinned interpreter (no pytest dependency):

```bash
# SDK interpreter supplied via environment (source pinned venv; not copied):
AGENT_WORKFLOWS_TEST_PYTHON=/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python \
  /Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python \
  -m unittest discover -s /Users/kpiwko/.config/dotfiles/evals/agent-workflows/tests \
  -t /Users/kpiwko/.config/dotfiles/evals/agent-workflows/tests
# -> Ran 62 tests ... OK (after P0.3: the generated case exists; the
#    suite generates its own disposable packages either way)
```

The `sandbox-git` wrapper is resolved from `$HOME/.local/bin/sandbox-git`
or `AGENT_WORKFLOWS_SANDBOX_GIT` (portable HOME-relative, not absolute).

Offline migration proof (typed config/validator/Task load + verifier
positive/negative; requires the generated case from bootstrap step 1
and the vendored harness on `PYTHONPATH`):

```bash
PYTHONPATH=<vendored harness b041d5a6…> <pinned venv python> \
  tests/p03_migration_proof.py    # 13/13 checks expected
```

## Scope labels (unchanged from source)

`judge_mode: deterministic-final-state-only`; no model judge;
`procedure_attempt_coverage: not_measured`; no MLflow logging.
