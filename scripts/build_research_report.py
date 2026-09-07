#!/usr/bin/env python3
"""Build the ATMAI v1.2 presentation from immutable recurrence evidence."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from statistics import mean

from reproduce_experiments import load_registry, verify_frozen_files

ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "docs/reports/recurrence-v1.2"
EXPERIMENT = ROOT / "labs/002-controlled-drift/experiments/exp-20260907-8313df3e-capacity-controlled-recurrence"
SOURCE = EXPERIMENT / "results/capacity-controlled-recurrence.json"
ARMS = ("abrupt", "b_only", "gradual", "stationary")
LABELS = ("Prior A, abrupt B", "B-only history", "Prior A, gradual B", "Stationary A")


def svg_overview(n: int, nodes: int, delta: float, ci: list, qe: dict, cost: float) -> str:
    """GitHub-native image; SVG text has a portable system-font fallback."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 700" role="img" aria-labelledby="title desc">
<title id="title">ATMAI: a return advantage, an adaptation cost</title>
<desc id="desc">{n} paired seeds, {nodes} nodes. Prior A minus B-only return error: {delta:.6f}, descriptive 95 percent interval {ci[0]:.6f} to {ci[1]:.6f}. Return error improves in all seeds; topology error worsens in all seeds. Combined B and A error is {cost:.2f} percent higher for prior A, a post hoc description.</desc>
<style>text{{font-family:Archivo,Arial,sans-serif;fill:#0a0a0a}}.mono{{font-family:'IBM Plex Mono',monospace}}.light{{fill:#f4f4f2}}.muted{{fill:#5c5c58}}</style>
<rect width="1200" height="700" fill="#f4f4f2"/>
<path d="M48 90H1152M48 650H1152" stroke="#737370"/>
<text x="48" y="60" font-size="27" font-weight="900">ATMAI</text>
<text x="1152" y="57" text-anchor="end" font-size="15" class="mono">RESEARCH / GNG / 2026-09-07</text>
<text x="48" y="164" font-size="16" class="mono">[ CAPACITY-CONTROLLED RECURRENCE ]</text>
<text x="44" y="242" font-size="66" font-weight="800" letter-spacing="-3">A return advantage.</text>
<text x="44" y="312" font-size="66" font-weight="800" letter-spacing="-3">An adaptation cost.</text>
<text x="940" y="209" font-size="64" font-weight="800">{n:02d}</text>
<text x="940" y="239" font-size="16" class="mono">PAIRED SEEDS</text>
<text x="940" y="300" font-size="48" font-weight="800">{nodes}</text>
<text x="940" y="328" font-size="16" class="mono">NODES PER ARM</text>
<rect x="48" y="360" width="1104" height="130" fill="#6c2bee"/>
<text x="72" y="390" font-size="15" class="mono light">OBSERVED RETURN DIFFERENCE / PRIOR A MINUS B-ONLY</text>
<text x="68" y="460" font-size="62" font-weight="800" class="light">{delta:.6f}</text>
<text x="640" y="422" font-size="17" class="light">Descriptive 95% seed-bootstrap interval</text>
<text x="640" y="455" font-size="23" class="mono light">[{ci[0]:.6f}, {ci[1]:.6f}]</text>
<text x="48" y="539" font-size="18" font-weight="700">Lower return representation error.</text>
<text x="48" y="575" font-size="25" class="mono">{qe['abrupt']:.6f} vs {qe['b_only']:.6f}</text>
<text x="48" y="611" font-size="17" class="muted">Prior A vs B-only. Every seed retained.</text>
<text x="650" y="539" font-size="18" font-weight="700">Higher topology error. Higher combined loss.</text>
<text x="650" y="575" font-size="25" class="mono">+{cost:.2f}% B + A error</text>
<text x="650" y="611" font-size="17" class="muted">Combined-phase summary is post hoc.</text>
<text x="48" y="679" font-size="15" class="mono">SYNTHETIC GEOMETRY / NO SEMANTIC MEMORY CLAIM</text>
<text x="1152" y="679" text-anchor="end" font-size="15" class="mono">DESIGN LANGUAGE 1.2</text>
</svg>'''


def build() -> dict[str, str]:
    failures = verify_frozen_files(ROOT, load_registry(ROOT))
    if failures:
        raise ValueError("frozen evidence check failed: " + "; ".join(failures))
    raw = SOURCE.read_bytes()
    report = json.loads(raw)
    if report["configuration_kind"] != "preregistered":
        raise ValueError("the research report requires the full preregistered panel")
    outcomes = report["seed_outcomes"]
    config = report["configuration"]
    primary = report["summary"]["primary"]
    qe = {arm: mean(row["arms"][arm]["phases"][1]["mean_qe"] for row in outcomes) for arm in ARMS}
    te = {arm: mean(row["arms"][arm]["phases"][1]["mean_te"] for row in outcomes) for arm in ARMS}
    intervention = {arm: mean(row["arms"][arm]["phases"][0]["mean_qe"] for row in outcomes) for arm in ARMS}
    combined = {arm: mean(sum(p["cumulative_qe"] for p in row["arms"][arm]["phases"])
                          / sum(p["samples"] for p in row["arms"][arm]["phases"])
                         for row in outcomes) for arm in ARMS}
    cost = (combined["abrupt"] / combined["b_only"] - 1) * 100
    qe_wins = sum(row["comparisons"]["primary_return_qe_difference"] < 0 for row in outcomes)
    te_losses = sum(row["comparisons"]["primary_return_te_difference"] > 0 for row in outcomes)
    # This presentation's prose names the observed, frozen outcome explicitly.
    if (qe_wins != len(outcomes) or te_losses != len(outcomes)
            or primary["capacity_mismatch_seed_ids"] or primary["warmup_capacity_failure_seed_ids"]):
        raise ValueError("evidence no longer supports this presentation's interpretation")

    def windows(row: dict, arm: str) -> list[list[float]]:
        return [[window["mean_qe"], window["mean_te"], window["components_end"]]
                for phase in row["arms"][arm]["phases"] for window in phase["windows"]]

    series = {str(row["seed_id"]): {arm: windows(row, arm) for arm in ARMS} for row in outcomes}
    count = len(series[str(outcomes[0]["seed_id"])]["abrupt"])
    aggregate = {arm: [[mean(seed[arm][i][metric] for seed in series.values())
                       for metric in range(3)] for i in range(count)] for arm in ARMS}
    series["all"] = aggregate
    payload = {"series": series, "arms": list(ARMS), "labels": list(LABELS),
               "phase": config["phase_steps"], "window": config["window_size"],
               "n": len(outcomes)}

    rows = []
    for outcome in outcomes:
        comparison = outcome["comparisons"]
        recovery = []
        for arm in ("abrupt", "b_only"):
            score = outcome["arms"][arm]["phases"][1]["recovery"]["qe"]
            recovery.append("Not confirmed" if score["censored"] else
                            f'{score["onset_samples"]:,} / {score["confirmation_samples"]:,}')
        values = [f'{outcome["seed_id"]:02d}',
                  f'{comparison["primary_return_qe_difference"]:.6f}',
                  f'{comparison["primary_return_te_difference"]:+.6f}', *recovery]
        rows.append("<tr>" + "".join(f"<td>{html.escape(v)}</td>" for v in values) + "</tr>")

    comparison_rows = []
    for label, values, posthoc in (("Return A: representation error", qe, False),
                                  ("Return A: topographic error", te, False),
                                  ("Preceding B: representation error", intervention, False),
                                  ("B + A: representation error", combined, True)):
        suffix = '<span class="table-note">Post hoc descriptive</span>' if posthoc else ""
        comparison_rows.append(f'<tr><th scope="row">{label}{suffix}</th><td>{values["abrupt"]:.6f}</td><td>{values["b_only"]:.6f}</td></tr>')

    values = {
        "CSS": (PRESENTATION / "report.css").read_text(),
        "SCRIPT": (PRESENTATION / "report.js").read_text(),
        "DATA": json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c"),
        "N": str(len(outcomes)), "NODES": str(config["max_nodes"]),
        "PHASE": f'{config["phase_steps"]:,}', "WARMUP": f'{config["warmup_steps"]:,}',
        "WINDOW": str(config["window_size"]),
        "DELTA": f'{primary["mean_return_qe_difference"]:.6f}',
        "CI": f'[{primary["ci95"][0]:.6f}, {primary["ci95"][1]:.6f}]',
        "COST": f"{cost:.2f}", "SEED_ROWS": "\n".join(rows),
        "COMPARISON_ROWS": "\n".join(comparison_rows),
        "SEED_OPTIONS": "".join(f'<option value="{row["seed_id"]}">Seed {row["seed_id"]:02d}</option>' for row in outcomes),
        "QE_RECOVERY_A": str(report["summary"]["recovery_counts"]["abrupt"]["qe"]["confirmed"]),
        "QE_RECOVERY_B": str(report["summary"]["recovery_counts"]["b_only"]["qe"]["confirmed"]),
        "SOURCE_SHA": hashlib.sha256(raw).hexdigest(),
    }
    document = (PRESENTATION / "template.html").read_text()
    for key, value in values.items():
        document = document.replace(f"@@{key}@@", value)
    if "@@" in document:
        raise ValueError("unresolved template marker")
    return {"index.html": document,
            "overview.svg": svg_overview(len(outcomes), config["max_nodes"],
                                          primary["mean_return_qe_difference"], primary["ci95"], qe, cost) + "\n"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if a committed presentation is stale")
    args = parser.parse_args()
    for name, content in build().items():
        path = PRESENTATION / name
        if args.check:
            if not path.is_file() or path.read_text() != content:
                print(f"STALE {path.relative_to(ROOT)}")
                return 1
        else:
            path.write_text(content)
        print(f'{"PASS" if args.check else "BUILT"} {path.relative_to(ROOT)}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
