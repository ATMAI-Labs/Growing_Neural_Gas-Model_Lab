# Dataset registry

Do not commit raw datasets to this repository.

Experiments record stable source URLs or identifiers, licenses, versions, and
checksums in `experiment.json`. If a tiny generated fixture is required for a
test, keep it under the experiment's `tests/fixtures/` directory, document how
it was generated, and keep it below the repository file-size limit.

Patient, clinical, confidential, or personally identifying data is prohibited.
