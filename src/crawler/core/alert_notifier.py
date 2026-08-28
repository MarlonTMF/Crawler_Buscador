"""Alert report writer for drift and crawl anomalies."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class AlertNotifier:
    """Writes alert reports to output/alerts in JSON and Markdown formats."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def notify(self, source_id: str, alert_type: str, payload: Dict[str, Any]) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_name = f"{timestamp}_{source_id}_{alert_type}"
        data = {
            "source_id": source_id,
            "alert_type": alert_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        json_path = self.output_dir / f"{base_name}.json"
        md_path = self.output_dir / f"{base_name}.md"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Alert: {alert_type}\n\n")
            f.write(f"- Source: {source_id}\n")
            f.write(f"- Generated at: {data['generated_at']}\n\n")
            f.write("```json\n")
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
            f.write("\n```\n")

        return json_path
