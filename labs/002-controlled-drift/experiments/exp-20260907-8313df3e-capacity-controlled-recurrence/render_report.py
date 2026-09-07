#!/usr/bin/env python3
"""Render the retained numeric report; optional matplotlib dependency only."""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
from pathlib import Path
from statistics import mean


ARMS = {
    "stationary": ("Stationary A", "#66768a"),
    "abrupt": ("Prior A / abrupt B", "#097f82"),
    "gradual": ("Prior A / gradual B", "#c77b27"),
    "b_only": ("Prior B / B-only history", "#7860a3"),
}


def render(report: dict, source: Path) -> tuple[str, bytes]:
    # Keep plotting dependencies separate from the standard-library experiment.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outcomes = report["seed_outcomes"]
    is_smoke = report.get("configuration_kind") != "preregistered"
    primary = report["summary"]["primary"]
    if not outcomes:
        raise ValueError("cannot render a report without seed outcomes")
    seed_ids = [row["seed_id"] for row in outcomes]
    differences = [row["comparisons"]["primary_return_qe_difference"] for row in outcomes]
    ci_low, ci_high = primary["ci95"]
    intervention_means = {
        arm: mean(row["arms"][arm]["phases"][0]["mean_qe"] for row in outcomes)
        for arm in ("abrupt", "b_only")
    }
    two_phase_means = {
        arm: mean(sum(phase["cumulative_qe"] for phase in row["arms"][arm]["phases"])
                  / sum(phase["samples"] for phase in row["arms"][arm]["phases"])
                  for row in outcomes)
        for arm in ("abrupt", "b_only")
    }
    mismatch_ids = primary["capacity_mismatch_seed_ids"]
    warmup_failures = primary["warmup_capacity_failure_seed_ids"]
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.labelcolor": "#24334b", "text.color": "#24334b",
        "axes.edgecolor": "#bcc5ce", "xtick.color": "#526179",
        "ytick.color": "#526179", "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.8), layout="constrained")
    fig.set_facecolor("#faf9f5")
    phase_length = outcomes[0]["arms"]["abrupt"]["phases"][0]["windows"][-1]["end_sample"]
    for arm, (label, color) in ARMS.items():
        series = []
        for row in outcomes:
            windows = []
            offset = 0
            for phase in row["arms"][arm]["phases"]:
                windows.extend((offset + window["end_sample"], window) for window in phase["windows"])
                offset += phase["windows"][-1]["end_sample"]
            series.append(windows)
        xs = [point[0] for point in series[0]]
        if any([point[0] for point in points] != xs for points in series):
            raise ValueError("window schedules differ across paired seeds")
        for axis, metric in ((axes[0, 0], "mean_qe"), (axes[0, 1], "mean_te")):
            ys = [mean(points[index][1][metric] for points in series) for index in range(len(xs))]
            axis.plot(xs, ys, label=label, color=color, linewidth=1.8)
        components = [mean(points[index][1]["components_end"] for points in series) for index in range(len(xs))]
        axes[1, 1].plot(xs, components, label=label, color=color, linewidth=1.8)

    for axis in (axes[0, 0], axes[0, 1], axes[1, 1]):
        axis.axvline(phase_length, color="#8694a4", linestyle="--", linewidth=1)
        axis.set_xlabel("Samples after warmup · return A begins at dashed line")
        axis.grid(axis="y", color="#dfe3e7", linewidth=0.6)
        axis.set_facecolor("#faf9f5")
    axes[0, 0].set(title="Representation error · mean across seeds", ylabel="Pre-update mean squared error · log scale", yscale="log")
    axes[0, 0].legend(frameon=False, fontsize=8)
    axes[0, 1].set(title="Topology error · mean across seeds", ylabel="Fraction of disconnected nearest pairs")
    axes[1, 1].set(title="Graph components · mean across seeds", ylabel="Connected components after each window")
    axes[1, 0].axvline(0, color="#8993a1", linewidth=1)
    axes[1, 0].scatter(differences, seed_ids, color="#097f82", s=26)
    axes[1, 0].set(title="Return-to-A comparison · every seed", xlabel="Mean squared error: prior A minus prior B\nNegative values favor prior-A training history", ylabel="Seed ID", yticks=seed_ids)
    axes[1, 0].grid(axis="x", color="#dfe3e7", linewidth=0.6)
    axes[1, 0].set_facecolor("#faf9f5")
    plot_title = ("SMOKE VALIDATION · reduced protocol" if is_smoke else
                  "Capacity-controlled geometric recurrence")
    fig.suptitle(plot_title, fontsize=19, fontweight="bold")
    svg_buffer = io.StringIO()
    fig.savefig(svg_buffer, format="svg", metadata={"Date": None})
    png_buffer = io.BytesIO()
    fig.savefig(png_buffer, format="png", dpi=160)
    plt.close(fig)
    svg = svg_buffer.getvalue()
    svg = svg[svg.index("<svg"):]

    def metric(value: float) -> str:
        return f"{value:.6g}"

    rows = []
    for outcome in outcomes:
        comparisons = outcome["comparisons"]
        mismatch = comparisons["primary_capacity_by_phase"]["return"]["mismatched_steps"]
        return_rows = [outcome["arms"][arm]["phases"][1] for arm in ("abrupt", "b_only")]
        recovery = []
        for row in return_rows:
            score = row["recovery"]["qe"]
            recovery.append("Not confirmed" if score["censored"] else f'{score["onset_samples"]} / {score["confirmation_samples"]}')
        values = [str(outcome["seed_id"]), metric(comparisons["primary_return_qe_difference"]),
                  metric(comparisons["primary_return_te_difference"]), str(mismatch), *recovery]
        rows.append("<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in values) + "</tr>")
    limited = bool(mismatch_ids or warmup_failures)
    capacity_note = (
        f"Capacity-isolated interpretation is limited. Mismatched-capacity seed IDs: {mismatch_ids}; "
        f"warmup-capacity failures: {warmup_failures}. Every seed remains in the estimate."
        if limited else
        "All seed pairs achieved the target starting node count and matched live-node capacity throughout the comparison. Edge counts, geometry and training history can still differ."
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    escaped_id = html.escape(report["experiment_id"])
    smoke_note = ('<p class="note"><strong>Smoke validation only.</strong> This reduced '
                  'configuration is a mechanics check, not the full preregistered experiment.</p>'
                  if is_smoke else '')
    document = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GNG · Capacity-controlled recurrence</title>
<style>
body{{margin:0;background:#faf9f5;color:#24334b;font:17px/1.55 system-ui,sans-serif}}main{{max-width:1180px;margin:48px auto;padding:0 24px 64px}}
.eyebrow{{letter-spacing:.12em;text-transform:uppercase;font-size:12px;color:#526179}}h1{{font-size:clamp(30px,4vw,48px);line-height:1.15;max-width:850px}}h2{{font-size:23px;margin-top:40px}}
.lead{{font-size:21px;max-width:900px}}.metrics{{display:flex;gap:24px;flex-wrap:wrap;border-block:1px solid #cbd2da;padding:20px 0;margin:28px 0}}.metric{{flex:1;min-width:230px}}.metric strong{{display:block;font-size:29px}}.metric span{{color:#526179;font-size:14px}}
.note{{border-left:4px solid #c77b27;padding:12px 18px;background:#f0ece2}}figure{{margin:28px 0}}figure svg{{width:100%;height:auto}}figcaption,.muted{{font-size:14px;color:#526179}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #dce1e6}}th{{font-weight:650}}.scroll{{overflow:auto}}code{{font-size:12px;overflow-wrap:anywhere}}li{{margin-bottom:8px}}
</style><main>
<p class="eyebrow">ATMAI · Growing Neural Gas Model Lab · {escaped_id}</p>
<h1>Does prior A training help when A returns?</h1>
{smoke_note}
<p class="lead">Two training histories receive the same intervening B stream and identical return-to-A samples. The canonical algorithm is unchanged. This experiment measures the effect of prior geometric experience.</p>
<div class="metrics"><div class="metric"><strong>{len(outcomes)} paired seeds</strong><span>All outcomes retained; windows are not independent replicates.</span></div>
<div class="metric"><strong>{metric(primary["mean_return_qe_difference"])}</strong><span>Mean return-error difference · prior A minus prior B</span></div>
<div class="metric"><strong>[{metric(ci_low)}, {metric(ci_high)}]</strong><span>Descriptive 95% seed-bootstrap percentile interval</span></div></div>
<p class="note">{html.escape(capacity_note)}</p>
<h2>The comparison</h2><div class="scroll"><table><tr><th>Arm</th><th>Warmup</th><th>Intervention</th><th>Return</th></tr>
<tr><td>Stationary reference</td><td>A</td><td>A</td><td>A</td></tr><tr><td>Prior A / abrupt B</td><td>A</td><td>B</td><td>A</td></tr>
<tr><td>Prior A / gradual B</td><td>A</td><td>Ramp A → B</td><td>A</td></tr><tr><td>Prior B / B-only history</td><td>B</td><td>B</td><td>A</td></tr></table></div>
<p>Warmup duration and total updates are matched. The warmup distribution is the treatment, so total lifetime B exposure differs. All three A-warm arms clone the same full model state. The gradual arm has no full-B hold and is a secondary tracking/history comparison.</p>
<h2>The return result has an intervention cost</h2>
<div class="scroll"><table><tr><th>Mean squared quantization error</th><th>Prior A / abrupt B</th><th>Prior B / B-only history</th></tr>
<tr><td>Preceding B intervention</td><td>{metric(intervention_means["abrupt"])}</td><td>{metric(intervention_means["b_only"])}</td></tr>
<tr><td>B and A phases together · post hoc descriptive</td><td>{metric(two_phase_means["abrupt"])}</td><td>{metric(two_phase_means["b_only"])}</td></tr></table></div>
<p>The combined-phase mean is an explicitly post hoc description of the retained losses, not the preregistered primary estimand or a new statistical test. A return-only advantage does not establish better overall adaptation.</p>
<figure>{svg}<figcaption>Lines average the same nonoverlapping window across seeds; the scatter retains individual seed differences. These panels summarize the JSON evidence and introduce no new statistical test.</figcaption></figure>
<h2>Every seed and its recovery measurements</h2><p>Recovery cells show <strong>onset / confirmation</strong> in samples after A returns. Onset is assigned retrospectively; confirmation requires two consecutive qualifying windows. “Not confirmed” is retained censoring.</p>
<div class="scroll"><table><tr><th>Seed</th><th>Δ return QE</th><th>Δ return TE</th><th>Return capacity mismatch steps</th><th>Prior-A QE onset / confirmation</th><th>Prior-B QE onset / confirmation</th></tr>{''.join(rows)}</table></div>
<h2>Interpretation boundary</h2><ul><li>A lower return error supports an effect of prior training history under this protocol. It does not establish semantic identity, explicit concept matching or a new memory mechanism.</li><li>Representation error and topographic error answer different questions. Both remain visible even when their changes disagree.</li><li>Recovery bands are operational tolerances fixed from independent pre-change evaluation, not confidence bands. Stationary behavior shows their calibration limits.</li><li>The bootstrap resamples seed-level paired differences. Its interval is descriptive; there is no aggregate pass or multiple-comparison-adjusted superiority claim.</li></ul>
<p class="muted">Source JSON SHA-256: <code>{digest}</code><br>Rendered with matplotlib {html.escape(matplotlib.__version__)}. The numerical experiment uses only the Python standard library. This report is a local static artifact; it makes no live-state claim.</p>
</main></html>'''
    # Matplotlib SVG path lines contain trailing spaces; keep generated text
    # clean for repository whitespace checks without changing the drawing.
    document = "\n".join(line.rstrip() for line in document.splitlines()) + "\n"
    return document, png_buffer.getvalue()


def output_path(path: Path) -> Path:
    destination = path.expanduser().resolve()
    if destination.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite {path}")
    # Do not add new files to an already completed experiment.
    for parent in destination.parents:
        manifest = parent / "experiment.json"
        if manifest.is_file() and json.loads(manifest.read_text()).get("status") == "complete":
            raise ValueError("render fresh reports outside completed experiment directories")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--png", type=Path)
    args = parser.parse_args()
    output = output_path(args.output)
    png_output = output_path(args.png) if args.png else None
    document, png = render(json.loads(args.input.read_text()), args.input)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(document)
    if png_output:
        png_output.parent.mkdir(parents=True, exist_ok=True)
        with png_output.open("xb") as handle:
            handle.write(png)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
