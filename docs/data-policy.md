# Public data and artifact policy

## Default rule

Git stores code, manifests, compact evidence, and documentation. It is not the
default storage system for datasets, checkpoints, embeddings, full logs, or
large experiment output.

## Prohibited content

Never commit:

- patient, clinical, personal, confidential, or restricted data;
- secrets, credentials, signed URLs, private hostnames, or local absolute paths;
- raw proprietary inputs;
- model weights or checkpoints;
- archives, executables, or serialized Python objects;
- third-party data or code without an explicit license and redistribution
  permission.

This prohibition includes samples, screenshots, filenames, notebook output, and
logs that indirectly expose sensitive information.

## Permitted public evidence

The repository may contain:

- generated synthetic fixtures required for tests;
- compact CSV or JSON summaries;
- small plots with a documented reproduction command;
- sanitized aggregate results;
- dataset descriptors containing stable public identifiers, licenses, versions,
  retrieval dates, and checksums.

No committed file may exceed 5 MiB. Smaller limits may be introduced for
specific evidence types as the lab matures.

## Licensing

The repository's MIT License applies to repository software. Every dataset,
paper, figure, external implementation, and generated artifact retains or
declares its own terms.

Code without an explicit license may be studied but not copied.

## Future external artifact storage

When experiments produce durable large artifacts, use immutable,
checksum-addressed storage and record its stable URI in the experiment
manifest. Prefer an archival record with a DOI for publication-grade evidence.
Do not record expiring signed download URLs.
