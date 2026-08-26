import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from benchmark_runner import SOURCES
from crawler.core.fetcher import HttpFetcher


def main() -> None:
    fetcher = HttpFetcher(timeout=15, max_retries=2, rate_limit_seconds=0.5)
    records = []

    for item in SOURCES:
        url = item['url']
        result = fetcher.validate_url_access(url, browser_fallback=True)
        effective_score = float(result.get('effective_score', 0.0) or 0.0)
        http_status = result.get('status_code')
        http_status = str(http_status) if http_status not in (None, 0) else (result.get('error_type') or 'CONN_ERROR')
        reachable = bool(result.get('reachable_http'))
        has_doc_signal = bool(result.get('has_document_signal'))
        robots_allowed = fetcher.is_url_allowed_by_robots(url)
        doc_links = int(result.get('document_links_found') or 0)
        keyword_hits = list(result.get('keyword_hits') or [])
        document_evidence = result.get('document_evidence') or {
            'keyword_hits': keyword_hits,
            'file_type': None,
            'quality_score': effective_score,
            'snippet_text': '',
        }

        if not reachable:
            diagnostics = ['sin enlace directo', 'fallo operativo']
        elif has_doc_signal:
            diagnostics = ['exitoso', 'documento detectado', 'acceso real']
        else:
            diagnostics = ['exitoso', 'sin enlace directo']

        error_detail = result.get('error_type')
        if error_detail:
            diagnostics.append(error_detail.lower())

        record = {
            'Fuente': item['code'],
            'Institucion': item['name'],
            'Url_Original': url,
            'Score_Excel': round(effective_score, 1),
            'Diagnosticos_Excel': diagnostics,
            'Robots_Allowed': robots_allowed,
            'HTTP_Status': http_status,
            'Final_Url': result.get('final_url') or url,
            'Doc_Links_Found_In_Seed': doc_links,
            'Subpage_Keywords_Found': len(keyword_hits),
            'Document_Evidence': document_evidence,
            'Error_Detail': error_detail if error_detail else None,
        }
        records.append(record)

    output_path = ROOT / 'output' / 'excel_urls_diagnostic.json'
    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')

    counts = Counter(float(r['Score_Excel']) for r in records)
    print(f'records={len(records)}')
    print(f'score_distribution={ {str(k): v for k, v in sorted(counts.items())} }')
    print(f'sample={records[0]}')


if __name__ == '__main__':
    main()
