# Presentation provenance

This report applies ATMAI Design System 1.2 at Abe's request. It presents the
completed capacity-controlled recurrence study; it is not a new experiment or
a change to the canonical algorithm.

## Design source

The visual specification was inspected in the local `atmai-design-system 1_2`
package at source revision `fb2f5735448f5b407d043e1a4b4f3e96fef35487`, alongside
its `docs/atmai-design-brief.html`. The operative rules are paper-led reading,
nested ink evidence panels, Archivo human text, IBM Plex Mono measurements,
Doto numeric readouts, semantic grayscale, one earned violet result region,
4px spacing units, small radii, and limits adjacent to claims.

| Source | SHA-256 |
| --- | --- |
| `readme.md` | `82209728544aed06c285627fbaa94be418cd6f9e5ce4c2b6c8e088cdde418d93` |
| `tokens/colors.css` | `c40dc5c459b7d91fc290671cbd956b36931aeb60a82dfc78277103e44e6a76c6` |
| `tokens/typography.css` | `a3291d95c6d7d23f34bfed325ec48e6bc54b1fd581fb9c7267e186d495ae4232` |
| `docs/atmai-design-brief.html` | `dccdce88463b898fb008490f5eb728fe447abd2f9866565326acbac23f93ca02` |

The source package has no explicit package/root license and its referenced
logo assets are absent. Its implementation code, bundled components and
artwork were not copied. The report's CSS, HTML, JavaScript and Python renderer
are original repository-owned code implementing the user-authorized visual
specification, under this repository's MIT license. ATMAI appears as ordinary
company-name text, not a recreated logo. No vendor effects are included.

The HTML requests Archivo, IBM Plex Mono and Doto from Google Fonts, matching
the specification's webfont approach. No font binaries are vendored. System
fallbacks keep the report readable offline. SVG images displayed by GitHub may
use those system fallbacks because image renderers do not load external fonts.
The responsive report and print treatment are adaptations for this document;
the source package does not provide a dedicated print specification.

## Scientific source

- Experiment: `exp-20260907-8313df3e`.
- Protocol revision: `e7b5e91`, committed before the full run.
- Research evidence revision: `9a2441980b15ba5123aac6fa8bb60a5ba0d5bc90`.
- JSON SHA-256: `105e4cd8571820cf22079e82ba6fad9d515c0e2d64acc3835e66c85c194e2bc4`.
- Source file: [retained results](../../../labs/002-controlled-drift/experiments/exp-20260907-8313df3e-capacity-controlled-recurrence/results/capacity-controlled-recurrence.json).

All experiments and the frozen registry remain unchanged. The builder verifies
their hashes before deriving the presentation. It reads primary outcomes and
the interval from the retained summary, calculates displayed phase means from
every retained seed, and embeds window-level measurements for the chart. The
B + A aggregate remains explicitly post hoc. Display rounding does not alter
the numerical evidence or exact-replay policy.

CI claims in the report are dated observations of the linked research runs,
not live status for the presentation branch. The failed full Linux replay and
its two scalar differences remain visible alongside the reference-runtime pass.

## Rebuild and check

From the repository root:

```bash
python3 scripts/build_research_report.py
python3 scripts/build_research_report.py --check
```

The first command writes only `index.html` and `overview.svg` in this report
directory. The second checks that those files match the source template,
stylesheet, script and frozen evidence. Both use the Python standard library.
