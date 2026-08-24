"""HTML form expansion helpers for GET-based public report forms."""

from itertools import product
from typing import Dict, List
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup


class FormAutomator:
    """Generates candidate submission URLs from static HTML forms."""

    def generate_get_urls(self, page_url: str, html: str, max_combinations: int = 200) -> List[str]:
        soup = BeautifulSoup(html or "", "html.parser")
        urls: List[str] = []

        for form in soup.find_all("form"):
            method = str(form.get("method", "get")).lower()
            if method and method != "get":
                continue
            action = urljoin(page_url, form.get("action") or page_url)
            fields: Dict[str, List[str]] = {}

            for input_tag in form.find_all("input"):
                name = input_tag.get("name")
                if not name:
                    continue
                fields.setdefault(name, [input_tag.get("value", "")])

            for select in form.find_all("select"):
                name = select.get("name")
                if not name:
                    continue
                values = [opt.get("value", "").strip() for opt in select.find_all("option")]
                values = [value for value in values if value]
                if values:
                    fields[name] = values

            if not fields:
                continue

            keys = list(fields)
            for combo in product(*(fields[key] for key in keys)):
                query = urlencode(dict(zip(keys, combo)))
                urls.append(f"{action}?{query}")
                if len(urls) >= max_combinations:
                    return urls

        return urls
