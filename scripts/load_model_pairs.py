# ruff: noqa: S608 - this script emits SQL text for psql; every value goes through _literal
"""Emit SQL that loads blind A/B answer pairs from scripts/compare_llms.py runs.

Only cases both models answered themselves (not Jev local refusals) become pairs. The A/B
order is shuffled per case from a hash of the run name, so the comparison stays blind and
reloading is stable. Standard library only: run on the host and pipe to psql as the owner.

    python3 scripts/load_model_pairs.py --run v41-vs-v4low \\
        --a results/compare-A.jsonl=deepseek/deepseek-v4.1-flash \\
        --b results/compare-B.jsonl=~deepseek/deepseek-v4-flash-latest | psql ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SPLITS = ("dev", "heldout", "challenge-v2")


def _literal(value: object) -> str:
    # standard_conforming_strings is on, so doubling quotes is the complete escape.
    return "'" + str(value).replace("'", "''") + "'"


def _answers(spec: str) -> tuple[str, dict[str, dict]]:
    path, model = spec.split("=", 1)
    rows = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["model"] == model and not row["localRefusal"] and row["answer"].strip():
            rows[row["caseId"]] = row
    if not rows:
        raise SystemExit(f"No model answers for {model} in {path}")
    return model, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True)
    parser.add_argument("--a", required=True, help="results.jsonl=model")
    parser.add_argument("--b", required=True, help="results.jsonl=model")
    parser.add_argument("--evaluation-dir", type=Path, default=Path("evaluation"))
    args = parser.parse_args()

    history = {
        case["id"]: case.get("history", [])
        for split in SPLITS
        for case in json.loads((args.evaluation_dir / f"{split}.json").read_text())["cases"]
    }
    model_one, first = _answers(args.a)
    model_two, second = _answers(args.b)
    print("BEGIN;")
    for case_id in sorted(set(first) & set(second)):
        swap = int(hashlib.sha256(f"{args.run}:{case_id}".encode()).hexdigest(), 16) % 2
        (model_a, row_a), (model_b, row_b) = sorted(
            [(model_one, first[case_id]), (model_two, second[case_id])],
            key=lambda item: item[0] == model_one,
            reverse=not swap,
        )
        values = [
            args.run,
            case_id,
            row_a["question"],
            json.dumps(history.get(case_id, []), ensure_ascii=False),
            row_a["answer"],
            row_b["answer"],
            model_a,
            model_b,
        ]
        print(
            "INSERT INTO model_pairs (run, case_id, question, history, answer_a, answer_b, "
            f"model_a, model_b) VALUES ({', '.join(_literal(v) for v in values)}) "
            "ON CONFLICT (run, case_id) DO NOTHING;"
        )
    print("COMMIT;")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
