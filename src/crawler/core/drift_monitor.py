"""DOM and volumetric drift detection."""

import hashlib
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional

from bs4 import BeautifulSoup


@dataclass
class DriftResult:
    drift_detected: bool
    similarity: float
    fingerprint: str
    reason: str


class DriftMonitor:
    """Computes lightweight structural fingerprints for HTML pages."""

    def __init__(self, threshold: float = 0.30):
        self.threshold = threshold

    def structural_sequence(self, html: str) -> List[str]:
        soup = BeautifulSoup(html or "", "html.parser")
        sequence = []
        for tag in soup.find_all(True):
            attrs = []
            if tag.get("id"):
                attrs.append("#")
            if tag.get("class"):
                attrs.append(".")
            if tag.get("href"):
                attrs.append("@href")
            sequence.append(f"{tag.name}{''.join(attrs)}")
        return sequence

    def fingerprint(self, html: str) -> str:
        joined = "|".join(self.structural_sequence(html))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def compare(self, previous_html: Optional[str], current_html: str) -> DriftResult:
        current_fp = self.fingerprint(current_html)
        if not previous_html:
            return DriftResult(False, 1.0, current_fp, "baseline_created")

        previous = self.structural_sequence(previous_html)
        current = self.structural_sequence(current_html)
        similarity = SequenceMatcher(a=previous, b=current).ratio()
        drift = (1.0 - similarity) > self.threshold
        return DriftResult(drift, similarity, current_fp, "structural_drift" if drift else "within_threshold")

    def volumetric_anomaly(self, historical_counts: Iterable[int], current_count: int, drop_ratio: float = 0.70) -> bool:
        counts = [count for count in historical_counts if count >= 0]
        if not counts:
            return False
        baseline = sum(counts) / len(counts)
        return baseline > 0 and current_count <= baseline * (1.0 - drop_ratio)
