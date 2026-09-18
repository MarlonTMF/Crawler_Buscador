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
        fuente = r.get('Fuente', 'Desconocida')
        print(f"Buscando muestras para {fuente} ({url})...")
        try:
            res = fetcher.validate_url_access(url, allow_variants=False)
            evidence = res.get('document_evidence', {})
            if evidence and evidence.get('samples'):
                r['Document_Evidence'] = evidence
                r['Doc_Links_Found_In_Seed'] = len(evidence['samples'])
                updated += 1
                p.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f"  -> Se guardaron {len(evidence['samples'])} muestras reales para {fuente}!")
        except Exception as e:
            print(f"  -> Error procesando {url}: {e}")

print(f"\n¡Completado! Se actualizaron {updated} fuentes.")
