"""Compare the judge's grades with a person's grades of the same answers.

The person grades answers on the private grading page (good, ok, bad). This reads the judge's
output from ``judge_answers`` and an export of those grades, keeps the answers both graded,
and reports how often they agree and Cohen's kappa, which discounts agreement expected by
chance.

Export the grades on the server with:
  SELECT json_object_agg(query_log_id, grade) FROM answer_grades;
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

GRADES = ("good", "ok", "bad")


def kappa(
    pairs: list[tuple[str, str]], labels: tuple[str, ...], *, weighted: bool = False
) -> float:
    """Cohen's kappa; with ``weighted`` a good/ok disagreement costs half a good/bad one."""
    total = len(pairs)
    span = len(labels) - 1
    cost = lambda a, b: (  # noqa: E731
        abs(labels.index(a) - labels.index(b)) / span if weighted else float(a != b)
    )
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    observed = sum(cost(a, b) for a, b in pairs) / total
    expected = sum(left[a] * right[b] * cost(a, b) for a in labels for b in labels) / total**2
    return 1.0 if expected == 0 else round(1 - observed / expected, 3)


def compare(judged: list[dict], human: dict[str, str]) -> dict:
    pairs = [(human[row["requestId"]], row["grade"]) for row in judged if row["requestId"] in human]
    if not pairs:
        raise SystemExit("No answer was graded by both the judge and a person")
    acceptable = [(str(a != "bad"), str(b != "bad")) for a, b in pairs]
    return {
        "gradedByBoth": len(pairs),
        "sameGrade": round(sum(a == b for a, b in pairs) / len(pairs), 3),
        "kappa": kappa(pairs, GRADES),
        "weightedKappa": kappa(pairs, GRADES, weighted=True),
        "sameOnAcceptable": round(sum(a == b for a, b in acceptable) / len(pairs), 3),
        "kappaOnAcceptable": kappa(acceptable, ("True", "False")),
        "personThenJudge": {f"{a}/{b}": count for (a, b), count in sorted(Counter(pairs).items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("judged", type=Path, help="judged-*.jsonl from judge_answers")
    parser.add_argument("grades", type=Path, help="JSON object of query log id to grade")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    judged = [json.loads(line) for line in args.judged.read_text().splitlines() if line]
    report = compare(judged, json.loads(args.grades.read_text()))
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
