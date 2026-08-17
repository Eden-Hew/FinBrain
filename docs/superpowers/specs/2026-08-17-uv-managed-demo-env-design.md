# uv-Managed Demo Environment

Date: 2026-08-17

## Problem

`scripts/run_demo.ps1` throws "Required demo dependency is missing." when a root `.venv`
does not exist, because it hard-requires `.venv\Scripts\python.exe`. Creating and maintaining a
venv by hand is friction for running the local demo.

## Goal

The demo lifecycle scripts must work without a pre-created `.venv`. `uv` manages the Python
environment automatically: `uv run` creates and syncs the project environment on demand.

## Scope

- `scripts/run_demo.ps1`
- `scripts/prepare_demo.ps1`
- `README.md` setup notes

`scripts/check_demo.ps1` and `scripts/stop_demo.ps1` are unaffected (they do not invoke Python).

## Approach

Use `uv run` for every Python invocation inside the demo scripts:

- Resolve `uv` from `PATH` via `Get-Command uv`. If missing, fail with a clear message.
- Backend / telegram / email components start as `uv run python -m ...` with the working
  directory set to `backend`, so `uv` locates `backend/pyproject.toml` and syncs as needed.
- `prepare_demo.ps1` replaces the direct `& $python -m ...` calls and the
  `.venv\Scripts\ruff.exe` path with `uv run --extra dev ruff` (ruff is a dev dependency).
- The "required dependency" check no longer tests `.venv\Scripts\python.exe`; it tests that
  `uv` is on `PATH` instead.

## Changes

### scripts/run_demo.ps1

- Replace `$python = Join-Path $repoRoot ".venv\Scripts\python.exe"` with a `$uv` variable
  resolved from `Get-Command uv`.
- Update the `$required` path list: drop the venv python, keep `$node`, `$vite`, `$envFile`,
  and add the resolved `uv` path.
- Change all three `Start-DemoComponent` calls to use `-Executable $uv` with arguments
  `@("run", "python", "-m", ...)`.

### scripts/prepare_demo.ps1

- Replace `$python = Join-Path $repoRoot ".venv\Scripts\python.exe"` with `$uv`.
- Update the `$required` list: drop venv python, keep `$envFile` and `$frontendModules`,
  add `$uv`.
- Replace each `& $python -m ...` with `& $uv run python -m ...`.
- Replace `& .venv\Scripts\ruff.exe check ...` with `& $uv run --extra dev ruff check ...`.
- Replace `& $python -m pytest -q` with `& $uv run --extra dev python -m pytest -q`.

### README.md

- Update the launcher prerequisites paragraph (line ~287) to say `uv` manages the Python
  environment instead of requiring a root `.venv`.

## Verification

- `.\scripts\run_demo.ps1` runs without a `.venv` and starts backend + frontend.
- `.\scripts\prepare_demo.ps1 -SkipNetworkChecks -SkipDetector` runs without a `.venv`.

## Out of scope

- No change to how connector status is validated.
- No change to `check_demo.ps1` or `stop_demo.ps1`.
- No database reset behavior change.
