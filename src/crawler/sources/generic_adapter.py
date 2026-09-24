"""Declarative YAML adapter for new sources."""

from pathlib import Path
from typing import Optional

from crawler.sources.base_adapter import BaseSourceAdapter


class GenericSourceAdapter(BaseSourceAdapter):
    """Classifies and filters URLs using only YAML rules."""

    def __init__(self, config_path: Path):
        super().__init__(config_path)
        self.excluded_keywords = self.config.get("classification", {}).get("excluded_path_keywords", [])
        self.dataset_rules = self.config.get("classification", {}).get("dataset_rules", [])

    def is_url_excluded(self, url: str) -> bool:
        url_lower = url.lower()
        return any(str(keyword).lower() in url_lower for keyword in self.excluded_keywords)

    def classify_dataset(self, url: str, anchor_text: str = "") -> Optional[str]:
        url_lower = url.lower()
        anchor_lower = anchor_text.lower()

        for rule in self.dataset_rules:
            for pattern in rule.get("url_patterns", []):
                if str(pattern).lower() in url_lower:
                    return rule.get("id")
            for keyword in rule.get("title_keywords", []):
                if str(keyword).lower() in anchor_lower:
                    return rule.get("id")

        if self.dataset_rules:
            return self.dataset_rules[0].get("id")
        return "documentos_publicos"

    def get_dataset_rule(self, dataset_id: str) -> Optional[dict]:
        for rule in self.dataset_rules:
            if rule.get("id") == dataset_id:
                return rule
        return None

    def get_dataset_periodicity(self, dataset_id: str) -> Optional[str]:
        rule = self.get_dataset_rule(dataset_id)
        return rule.get("periodicity") if rule else None

    def get_dataset_tolerance(self, dataset_id: str) -> Optional[int]:
        rule = self.get_dataset_rule(dataset_id)
        return rule.get("tolerance") if rule else None
