# Contributing

The goal is to make experiments easy to add without making `main` fragile.

## Workflow

- External contributors use a fork.
- ATMAI contributors use a feature branch.
- Never push directly to `main`.
- Keep one experiment or shared concern per pull request.
- Open pull requests as drafts until the work and checks are ready.

A useful branch name is `<handle>/feature/<purpose>`. Abe's Codex preference is
`abe/feature/`.

## Add an experiment

1. If the scope is not already agreed, open an experiment-proposal issue.
2. Copy `templates/experiment/` into the accepted lab's `experiments/` folder.
3. Generate a collision-resistant token:

   ```bash
   python3 -c 'import secrets; print(secrets.token_hex(4))'
   ```

4. Name the folder `exp-YYYYMMDD-8hex-short-slug`.
5. Fill in `experiment.json` and state one falsifiable hypothesis.
6. Keep code and results inside that experiment until they are ready to be
   promoted into `src/`.

## Do not commit

- secrets, credentials, `.env` files, or signed URLs;
- personal, patient, clinical, confidential, or restricted data;
- raw datasets, model weights, checkpoints, archives, or large logs;
- third-party code without a compatible license and attribution.

Small synthetic fixtures and compact reproducible plots are welcome.

## Checks

```bash
python3 scripts/validate_repository.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Pull requests

Describe the question, what changed, commands run, sources/licenses, and known
limitations. Resolve review comments and use squash merge.

By contributing, you confirm that you have the right to submit the work under
the repository's MIT License. External data and artifacts keep their own
licenses.
