"""Pool retrieval evaluation runs into one comparison with intervals and paired tests.

Reads the per-question JSONL written by ``evaluate_jev_retrieval`` and
``evaluate_chunking_offline`` from one directory and writes one JSON summary: every route's
ranking scores with bootstrap intervals, each route's paired gap to a reference route, scores by
question category, and how each route handles questions that must be refused.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from math import comb
from pathlib import Path
from typing import Any

import numpy as np

METRICS = {
    # The first passage is a right one. Recall@1 is capped at 0.5 for a two-passage question.
    "hitAt1": "hitAt1",
    "recallAt1": "recallAt1",
    "recallAt3": "recallAt3",
    "recallAt5": "recallAt5",
    "mrrAt5": "reciprocalRankAt5",
    "allEvidenceAt3": "allEvidenceAt3",
    "allEvidenceAt5": "allEvidenceAt5",
}
# Production refuses without a language model when Jev's answerable signal is at or below this.
JEV_ANSWERABLE_THRESHOLD = 0.5


def _interval(values: np.ndarray, rng: np.random.Generator, resamples: int) -> list[float]:
    means = rng.choice(values, (resamples, len(values))).mean(axis=1)
    return [round(float(bound), 3) for bound in np.percentile(means, [2.5, 97.5])]


def _sign_test(wins: int, losses: int) -> float:
    """Two-sided exact binomial test that wins and losses are equally likely."""
    total = wins + losses
    if total == 0:
        return 1.0
    tail = sum(comb(total, k) for k in range(min(wins, losses) + 1)) / 2**total
    return round(min(1.0, 2 * tail), 6)


def _refused(row: dict[str, Any]) -> bool:
    if "answerableSignal" in row:
        return row["answerableSignal"] <= JEV_ANSWERABLE_THRESHOLD
    return bool(row["refusedLocally"])


def summarize(
    rows: list[dict[str, Any]], *, reference: str, resamples: int, seed: int
) -> dict[str, Any]:
    by_route: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        if row["caseId"] in by_route[row["embedder"]]:
            raise SystemExit(f"{row['embedder']}: {row['caseId']} appears in more than one run")
        by_route[row["embedder"]][row["caseId"]] = row
    case_ids = set(by_route[reference])
    for route, cases in by_route.items():
        if set(cases) != case_ids:
            raise SystemExit(f"{route} did not run the same questions as {reference}")
    scored_ids = sorted(
        case_id for case_id in case_ids if not by_route[reference][case_id]["refusalCase"]
    )
    refusal_ids = sorted(case_ids - set(scored_ids))
    rng = np.random.default_rng(seed)

    def values(route: str, key: str, ids: list[str]) -> np.ndarray:
        if key == "hitAt1":
            return np.array(
                [float(by_route[route][i]["metrics"]["reciprocalRankAt5"] == 1) for i in ids]
            )
        return np.array([float(by_route[route][case_id]["metrics"][key]) for case_id in ids])

    routes: dict[str, Any] = {}
    for route in by_route:
        entry: dict[str, Any] = {
            name: round(float(values(route, key, scored_ids).mean()), 3)
            for name, key in METRICS.items()
        }
        entry["hitAt1Ci95"] = _interval(values(route, "hitAt1", scored_ids), rng, resamples)
        entry["recallAt1Ci95"] = _interval(values(route, "recallAt1", scored_ids), rng, resamples)
        entry["mrrAt5Ci95"] = _interval(
            values(route, "reciprocalRankAt5", scored_ids), rng, resamples
        )
        categories: dict[str, list[str]] = defaultdict(list)
        for case_id in scored_ids:
            categories[by_route[route][case_id]["category"]].append(case_id)
        entry["byCategory"] = {
            category: {
                "cases": len(ids),
                "hitAt1": round(float(values(route, "hitAt1", ids).mean()), 3),
                "allEvidenceAt3": round(float(values(route, "allEvidenceAt3", ids).mean()), 3),
            }
            for category, ids in sorted(categories.items())
        }
        entry["refusals"] = {
            "mustRefuse": len(refusal_ids),
            "refusedWithoutLanguageModel": sum(_refused(by_route[route][i]) for i in refusal_ids),
            "answerable": len(scored_ids),
            "answerableWronglyRefused": sum(_refused(by_route[route][i]) for i in scored_ids),
        }
        if route != reference:
            gap = values(reference, "hitAt1", scored_ids) - values(route, "hitAt1", scored_ids)
            wins, losses = int((gap > 0).sum()), int((gap < 0).sum())
            entry["referenceMinusThis"] = {
                "hitAt1": round(float(gap.mean()), 3),
                "hitAt1Ci95": _interval(gap, rng, resamples),
                "referenceBetterOn": wins,
                "referenceWorseOn": losses,
                "signTestP": _sign_test(wins, losses),
            }
        routes[route] = entry
    return {
        "reference": reference,
        "answerableCases": len(scored_ids),
        "refusalCases": len(refusal_ids),
        "intervals": f"percentile bootstrap over questions, {resamples} resamples, seed {seed}",
        "routes": dict(sorted(routes.items(), key=lambda item: -item[1]["hitAt1"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path, help="Directory holding the runs' .jsonl files")
    parser.add_argument("--reference", default="jev-hybrid")
    parser.add_argument("--resamples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for path in sorted(args.results.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise SystemExit(f"No .jsonl runs under {args.results}")
    summaries = [json.loads(path.read_text()) for path in sorted(args.results.rglob("*.json"))]
    corpus = {summary["corpusSha256"] for summary in summaries}
    if len(corpus) != 1:
        raise SystemExit("The runs were made on different corpora")
    report = {
        "corpusSha256": corpus.pop(),
        "chunkCount": summaries[0]["chunkCount"],
        "splits": sorted({row["split"] for row in rows}),
        **summarize(rows, reference=args.reference, resamples=args.resamples, seed=args.seed),
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
