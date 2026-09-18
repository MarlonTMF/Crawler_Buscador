import json
from pathlib import Path
from src.crawler.core.fetcher import HttpFetcher

p = Path('output/excel_urls_diagnostic.json')
records = json.loads(p.read_text(encoding='utf-8'))
fetcher = HttpFetcher(timeout=4, max_retries=1)

updated = 0
for r in records:
    score = float(r.get('Score_Excel', 0))
    url = r.get('Final_Url') or r.get('Url_Original') or ''
    if score >= 3.0 and url.startswith('http'):
        fuente = r.get('Fuente', 'Fuente')
        print(f"Procesando muestras para {fuente} ({url})...")
        try:
            res = fetcher.validate_url_access(url, allow_variants=False)
            evidence = res.get('document_evidence', {})
            if evidence:
                r['Document_Evidence'] = evidence
                if evidence.get('samples'):
                    r['Doc_Links_Found_In_Seed'] = len(evidence['samples'])
                updated += 1
        except Exception as e:
            print(f"  Error en {url}: {e}")

p.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"\n¡Completado exitosamente! Se actualizaron {updated} fuentes con sus PDFs y documentos reales.")
