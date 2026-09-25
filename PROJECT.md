# Project State

Tracks the current state, roadmap, and lessons learned for this project.
See [AGENTS.md](AGENTS.md) for structure/tooling conventions.

## Current State

This is a template repository for research projects that publish a MyST
Jupyter Book, with DVC-orchestrated pipelines (migrated from Snakemake).
Docs were consolidated: contribution/agent conventions live in
`AGENTS.md`, project tracking lives here.

## Next Steps

- None pending — this file is now wired into the `wrap-up` skill workflow.

## Lessons Learned

### 2026-08-26 — Doc consolidation

- Renamed `contribution_conventions.md` → `AGENTS.md` so agent tooling
  (Claude Code and others reading the `AGENTS.md` convention) picks up
  project conventions automatically instead of relying on a human to
  point to a differently-named file.
- Added this `PROJECT.md` as a single running file for state/roadmap/
  lessons rather than splitting across `TODO.md` + a separate learnings
  file — lower overhead to keep in sync at this project's pace.
- Added a project-local `wrap-up` skill (`.claude/skills/wrap-up/`)
  rather than relying on the global `~/.agents/skills/wrap-up`, so the
  checklist can reference this project's actual files (`AGENTS.md`,
  `PROJECT.md`, `pre-commit` — no `ruff`/`pyright` here) without drifting
  from a shared, more generic version.
