# Lanes & Promotion Policy

**Exploration and authority are separate states.** When exploring aquatic spectra, satellite granules, or foundation-model embeddings, interactive experimentation is essential—yet exploratory parameter choices made while inspecting outputs must never silently become confirmatory claims on `main`.

**Sprints relax evidence gates, never safety or data-hygiene gates.**

## Four Lanes

| Lane | Branch / Location | Independent review? | Merged to `main`? |
| --- | --- | --- | --- |
| **Scratch** | Outside the repository (temp/scratch dir) | No | **Never** |
| **Sprint** | `sprint/<topic>-<yyyy-mm>` (local by default) | No | **Never** |
| **Promotion** | `promote/<topic>`, cut fresh from `main` | Yes, at head SHA | Yes, after review & green checks |
| **Fixes, docs & infra** | `fix/*`, `docs/*`, `feat/*`, `chore/*` | Yes (except trivial typos) | Yes, after review & green checks |

**A promotion re-implements what survived; it never merges a `sprint/*` branch.** (`tools/check_repo_hygiene.py` fails in CI if a `sprint/*` merge commit appears in history.)

Why: a sprint branch accumulates wavelengths selected after eyeing correlations, display stretches, ad-hoc cohort drops, or model hyperparameters tuned on the cohort in front of you. Merging the sprint branch imports both the code and the look-elsewhere bias. Instead, cut a fresh `promote/<topic>` branch from `main`, record the sprint SHA in the protocol/manifest provenance as prior exposure, and implement only the clean, tested pipeline.

## The Sprint Contract

**Allowed and expected in `sprint/*`:**
- Exploratory band ratios, smoothing windows, clustering experiments, and abandoned prototypes.
- Parameter sweeps inspected interactively before deciding whether an idea merits promotion.

**Still strictly forbidden in every lane (including `sprint/*`):**
- Committing raw archives, satellite granules (`.zip`, `.nc`, `.h5`, `.tif`), or third-party publisher PDFs.
- Committing `config/local_paths.yaml`, cloud project IDs, `.env`, `.netrc`, or credentials.
- Describing a sprint output as "validated", "confirmed", or "reproduced" in prose, figure titles, or commit messages.

**Required sprint header:** Start a short `SPRINT_LOG.md` (kept on the sprint branch only) stating the question, allowed shortcuts, **explicit stop condition**, and the sentence: *"Exploratory sprint branch; nothing here is authoritative."* Without a stop condition, a sprint stops when attention runs out and its final trial acquires false authority by being last.

## Promotion Gates into `main`

A `promote/*` pull request must arrive with:

1. **Honest status & pre-registration:** Either an `exploratory` educational/baseline designation (disclosing prior sprint exposure) or a dated protocol in `pre-registrations/` committed *before* confirmatory evaluation on held-out folds. A threshold chosen afterwards is an observation, never a confirmatory gate.
2. **Physical & statistical baselines:** Comparison against interpretable physical baselines (2-band ratios, AVW, OWTs, PCA) and location/season baselines (`M0`) on identical cohorts and paired splits (waterbody-held-out, `Dataset_ID`-held-out, temporal).
3. **Applicability & denominator accounting:** Explicit `attempted`, `completed`, `failed`, and `excluded` counts with denominators, units, and out-of-distribution diagnostics.
4. **Tests that can fail & green guards:** Unit/boundary/planted-defect tests in `tests/` (`uv run pytest -q`) plus green repository guards (`tools/check_*.py --self-test`).
5. **Independent review:** Review of the diff, claims, and checks by someone other than the author (a person or a fresh review agent without the author's reasoning).
