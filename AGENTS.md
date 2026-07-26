# Repository instructions for AI coding agents

These instructions apply to the entire repository.

## Operating model

- Treat `main` as protected. Work on a feature branch and use a pull request.
- Organize labs by research question as `labs/NNN-kebab-case`, never by a
  contributor's personal folder.
- Organize experiments as
  `labs/NNN-kebab-case/experiments/exp-YYYYMMDD-8hex-kebab-case`.
- Record authors and owners in manifests. Do not infer authorship from a folder
  name.
- Do not edit a completed experiment to make a new claim. Create a new
  experiment and link the predecessor.
- Do not promote exploratory code into `src/` without reproducible evidence,
  tests, provenance, and maintainer approval.

## Safety and provenance

- Never commit secrets, credentials, `.env` files, patient or clinical data,
  personally identifying information, raw proprietary data, model weights, or
  large generated artifacts.
- Do not copy code from another repository unless its license and attribution
  have been reviewed and recorded.
- Code without an explicit license is not reusable.
- Keep geometric evidence, drift detection, concept identity, and delayed label
  semantics distinct in claims and implementations.
- Report failed and inconclusive experiments honestly.

## Required validation

Before handing off a change, run:

```bash
python3 scripts/validate_repository.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

Do not claim that checks passed unless they were run successfully in the current
worktree.
