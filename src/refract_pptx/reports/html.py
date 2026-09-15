from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _load_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    return payload if isinstance(payload, list) else [payload]


def render_report(input_path: str | Path, output_path: str | Path) -> Path:
    source = Path(input_path)
    target = Path(output_path)
    records = _load_records(source)
    accepted = sum(bool(record.get("accepted")) for record in records)
    scores = [float(record["quality_score"]) for record in records if "quality_score" in record]
    average = sum(scores) / len(scores) if scores else 0.0
    rows = []
    for record in records:
        path = html.escape(str(record.get("path", record.get("task_id", "record"))))
        decision = "accepted" if record.get("accepted") else "review"
        score = record.get("quality_score", "-")
        families = ", ".join(record.get("recommended_families", [])) or "-"
        reasons = "; ".join(record.get("reasons", [])) or "-"
        rows.append(
            "<tr>"
            f"<td>{path}</td><td>{html.escape(decision)}</td>"
            f"<td>{html.escape(str(score))}</td>"
            f"<td>{html.escape(families)}</td><td>{html.escape(reasons)}</td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>REFRACT report</title>
  <style>
    body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; color: #17212b; }}
    header {{ background: #0b4f6c; color: white; padding: 28px max(24px, 5vw); }}
    main {{ padding: 24px max(24px, 5vw); }}
    .metrics {{ display: flex; gap: 28px; margin: 18px 0 28px; }}
    .metric strong {{ display: block; font-size: 28px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #d8e0e6; padding: 10px; text-align: left; }}
    th {{ color: #52616d; font-size: 13px; }}
    tr:hover {{ background: #f5f8fa; }}
  </style>
</head>
<body>
  <header><h1>REFRACT corpus report</h1><p>{html.escape(source.name)}</p></header>
  <main>
    <div class="metrics">
      <div class="metric"><strong>{len(records)}</strong>records</div>
      <div class="metric"><strong>{accepted}</strong>accepted</div>
      <div class="metric"><strong>{average:.3f}</strong>average quality</div>
    </div>
    <table>
      <thead><tr><th>Source</th><th>Decision</th><th>Score</th><th>Families</th><th>Reasons</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </main>
</body>
</html>
"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    return target
