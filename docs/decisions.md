# Architectural & Methodological Decisions

Durable repository-wide decisions recorded so future contributors and agents understand *why* constraints exist rather than working around them.

## D-001 — Split license: MIT for code, CC BY 4.0 for documentation and figures (2026-11-25)

- **Decision:** Keep [`LICENSE`](../LICENSE) as verbatim MIT text for all executable code (`src/`, `tests/`, `tools/`, notebook code cells) and [`LICENSE-DOCS.md`](../LICENSE-DOCS.md) as CC BY 4.0 for documentation, protocols, and original figures.
- **Reason:** Pure MIT in `LICENSE` lets standard tooling (including GitHub's license detector) classify software permissions unambiguously, while CC BY 4.0 preserves attribution for scientific syntheses, protocols, and figures. Upstream datasets and third-party papers remain outside Git under their own licenses.

## D-002 — `uv` lockfile, CPU-first baseline, and explicit UTF-8 text I/O (2026-11-25)

- **Decision:** Manage Python dependencies via `pyproject.toml` and `uv.lock` (`python >= 3.11`), default to CPU-reproducible workflows, and enforce explicit `encoding="utf-8"` on every Python text read/write via `tools/check_declared_encoding.py`.
- **Reason:** Development spans Windows (`cp949` default locale) and Linux CI (`UTF-8`). Bare `open()` or `Path.read_text()` silently corrupts or crashes on non-ASCII characters (such as units `µg/L`, `sr⁻¹`, or accented author names) across platforms.

## D-003 — Four-lane exploration vs. promotion model (2026-11-25)

- **Decision:** Separate off-repo scratch, unmerged `sprint/*` branches, fresh `promote/*` branches, and standard `feat/*`/`fix/*`/`docs/*` branches ([`docs/lanes-and-promotion.md`](lanes-and-promotion.md)). Forbid merging `sprint/*` into `main` via `tools/check_repo_hygiene.py`.
- **Reason:** Hyperspectral band selection and EO feature engineering invite look-elsewhere bias. Re-implementing surviving methods on a fresh branch from `main` with disclosed prior exposure prevents sprint-tuned thresholds from masquerading as confirmatory findings.

## D-004 — External source manifests with `digest_verified` honesty and gitignored local paths (2026-11-25)

- **Decision:** Track external datasets via `manifests/sources/*.yaml` validated against [`schemas/source_manifest.schema.json`](../schemas/source_manifest.schema.json), referencing symbolic keys in gitignored `config/local_paths.yaml`. Keep `digest_verified: false` until the SHA-256 hash is recomputed on the local checkout.
- **Reason:** Keeps multi-hundred-megabyte archives (`.zip`, `.nc`) and workstation paths out of public Git history while distinguishing upstream/handoff checksums from locally verified files.

## D-005 — No empty stub scripts for unbuilt analyses (2026-11-25)

- **Decision:** Do not commit placeholder `.py` scripts or empty notebooks for `Q01`–`Q13`, `HS-R*`, `OPT-*`, or `EA-R*` before their real logic and tests exist. Track planned vs. implemented status explicitly in `README.md`.
- **Reason:** A stub script that exits 0 or returns an empty table is indistinguishable from a working analysis over an empty cohort. Every committed module or check must fail on broken or empty inputs (`tests/conftest.py`).

## D-006 — Explicit path staging (`git add <paths>`) over wildcard staging (2026-11-25)

- **Decision:** Stage files explicitly by path (`git add path/one path/two`), inspect `git diff --cached --stat` and `git diff --cached --check` immediately prior to `git commit`, and avoid `git add -A` / `git add .` (`AGENTS.md` rule 4).
- **Reason:** Prevents untracked files, temporary outputs, or concurrent session edits in a shared working directory from being swept into an unrelated public commit.
