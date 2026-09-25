---
name: wrap-up
description: Runs checklist validation (git status, code quality, DVC pipeline status, and document freshness) before finalizing or committing a coding session in this project.
---

# Session Wrap-up Skill

Run the following checks in order, then produce a consolidated report and
suggest next actions. Fix nothing automatically — report and suggest.

## 1. Pipeline status

Run `uv run dvc status` and note which stages (if any) are out of date or
have missing outputs. If a stage is out of date, name it explicitly.

## 2. Git status

Run `git status` to list all modified, staged, and untracked files.

Group the pending changes by concern:
- Pipeline scripts (`pipeline/`)
- Package code (`pkg/`)
- Notebooks / images (`book/notebooks/`, `output/`)
- Config / infrastructure (`dvc.yaml`, `dvc.lock`, `pyproject.toml`, `Makefile`)
- Docs (`README.md`, `AGENTS.md`, `PROJECT.md`, `book/markdown/`)

Flag if the pending changes span unrelated concerns (e.g., both new
analysis scripts and infrastructure changes). In that case, suggest
splitting into separate commits and propose groupings.

## 3. Code quality

This project uses `pre-commit` (check-toml, check-yaml, end-of-file-fixer,
trailing-whitespace, check-added-large-files) — there is no ruff or pyright
configured. Run:

```bash
uv run pre-commit run --all-files
```

Report pass/fail with any error details.

## 4. Doc freshness

Run `git diff HEAD` to understand what changed this session.

Read the current contents of `README.md`, `AGENTS.md`, and `PROJECT.md`.

For each file, assess whether it needs updating based on the diff:
- **README.md** — update if setup steps, tool commands, or entry points changed.
- **AGENTS.md** — update if new pipeline patterns, path conventions, DVC
  stage patterns, or tooling were introduced.
- **PROJECT.md** — almost always needs updating: current state, next
  steps, and (if something non-obvious was learned this session) a new
  dated entry appended under "Lessons Learned" — do not overwrite prior
  entries there, only append.

State for each file: "looks current" or "suggest update: <brief reason>".

Then ask: *What should be recorded as the key outcome of this session and
what is the next step?*

Use the answer to draft updated `## Current State` and `## Next Steps`
sections, plus a new dated `### <date> — <title>` entry under
`## Lessons Learned` in `PROJECT.md` if applicable. Show the draft for
approval before writing it.

## 5. Summary

Report a final checklist:

- [ ] Pipeline up to date (`dvc status` clean)
- [ ] No uncommitted relevant files (or commit plan is clear)
- [ ] `pre-commit run --all-files` passing
- [ ] `README.md` current
- [ ] `AGENTS.md` current
- [ ] `PROJECT.md` current

If all pass, suggest a git commit message but do not run `git commit`
automatically.

If anything is failing or stale, list what needs to be addressed first.
