# Contributing

Thank you for helping build a careful, reproducible Growing Neural Gas research
lab.

## Before you start

- Read the [research charter](docs/research-charter.md), [repository structure
  contract](docs/repository-structure.md), and [governance](GOVERNANCE.md).
- Search existing issues and experiments before proposing another.
- Open an experiment proposal before creating a new lab or experiment.
- Ask privately through GitHub's security-reporting flow if your contribution
  may expose a vulnerability, secret, personal data, or confidential material.

## Branch and fork model

- External contributors work from a fork.
- ATMAI maintainers work from a feature branch.
- Never commit directly to `main`.
- Use a descriptive branch such as
  `<handle>/feature/<short-purpose>` or `<handle>/fix/<short-purpose>`.
- Keep one scientific question or shared concern per pull request.

The `abe/feature/` prefix is a local maintainer preference, not a requirement for
public contributors.

## Creating an experiment

1. Copy `templates/experiment/` into the accepted lab's `experiments/`
   directory.
2. Generate a random token locally:

   ```bash
   python3 -c 'import secrets; print(secrets.token_hex(4))'
   ```

3. Name the directory
   `exp-YYYYMMDD-8hex-lowercase-kebab-case`.
4. Set manifest `id` to `exp-YYYYMMDD-8hex`, set `slug` to the final directory
   segment, and fill every required field.
5. State one falsifiable hypothesis. Do not write the expected result as if it
   has already occurred.
6. Record code, data, paper, tool, and AI-assistance provenance where relevant.
7. Add deterministic commands and an environment description before moving the
   experiment out of `proposed`.

## Data and artifact rules

Do not commit:

- patient, clinical, confidential, restricted, or personally identifying data;
- API keys, credentials, `.env` files, signed URLs, or private host paths;
- raw datasets, checkpoints, embeddings, model weights, archives, or full logs;
- third-party code without an explicit compatible license and attribution.

Small synthetic test fixtures and compact generated figures may be accepted
when their origin and reproduction command are documented. The repository
validator rejects prohibited formats and files larger than 5 MiB.

## Local checks

Run both commands from the repository root:

```bash
python3 scripts/validate_repository.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

Do not claim a check passed unless you ran it successfully on the submitted
revision.

## Commit messages

Use imperative Conventional Commit-style subjects:

```text
<type>(<scope>): <summary>
```

Common types are `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `ci`, and
`chore`. Useful scopes include a lab ID, experiment ID, `core`, or `governance`.

Example:

```text
feat(exp-20260727-ee260fe9): add deterministic baseline runner
```

Explain why in the body when the subject is insufficient. Reference the issue or
experiment ID.

## Pull requests

- Open the pull request as a draft while work is incomplete.
- Complete the pull-request template.
- Link the accepted proposal issue.
- Separate observed results from interpretation and future work.
- Disclose data classification, provenance, licensing, limitations, and checks.
- Resolve every review conversation.
- Do not merge your own work. A code owner reviews and squash-merges it after
  required checks pass.

## Contribution license

By submitting a contribution, you confirm that you have the right to submit it
and agree that repository code is distributed under the MIT License. This does
not change the independent licenses of datasets, papers, figures, third-party
software, or other artifacts.
