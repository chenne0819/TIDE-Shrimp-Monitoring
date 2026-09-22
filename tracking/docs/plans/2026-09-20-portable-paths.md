# Portable project paths implementation plan

Historical plan completed on 2026-09-20 in the original integration checkout. In this monorepo, the component lives in `tracking/`; use the [maintained setup guide](../../README.md).

**Goal:** Make the integrated inference entry points relocatable and document how another user supplies model assets after cloning.

**Architecture:** Store default asset locations as project-relative names and resolve them against `project_paths.py` at runtime. Explicit user paths retain normal command-line semantics. Source provenance keeps hashes and descriptive origins, without personal filesystem paths.

**Tech Stack:** Python pathlib, existing inference configuration modules, pytest, Markdown and JSON.

## Work

1. Add a dependency-free project root/path helper; use it in the three inference configs and shared monitoring defaults.
2. Test defaults from a different working directory, then copy the relevant code and lightweight real assets into a renamed temporary checkout and verify resolution there.
3. Audit existing training configuration for machine-specific paths and fix any confirmed incompatible defaults without launching training.
4. Remove personal absolute paths from public documentation/manifests, preserve hashes, and document clone/setup/weight placement and optional missing models.
5. Run targeted portability and existing integration tests, inspect documentation links, and check the final diff. Publication was outside the scope of this original plan.

## Completion

Implemented all five steps. Six portability tests passed, including a relocated checkout with spaces and Chinese characters, real water/regression model loading, and the actual Ultralytics dataset YAML resolver. Forty-three existing integration/water tests also passed during this change. Public documentation links and both provenance JSON files were checked. At that stage, no training, publication, or cross-platform inference run was performed. See the [validation record](../monitoring-validation.md) for later verification.
