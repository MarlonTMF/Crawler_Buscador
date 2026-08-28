import yaml
from pathlib import Path
from crawler.core import wayback_engine, subdomain_finder, async_fetcher
import sys


def load_config(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_head(fetcher, url: str):
    try:
        allowed, status, headers = fetcher.fetch_head_sync(url)
        return {"url": url, "allowed": allowed, "status": status, "headers": headers}
    except Exception as e:
        return {"url": url, "allowed": False, "status": None, "error": str(e)}


def main():
    repo = Path(__file__).resolve().parents[1]
    cfg_path = repo / "config" / "source_finrural.yaml"
    if not cfg_path.exists():
        print("Config not found:", cfg_path)
        sys.exit(1)

    cfg = load_config(cfg_path)
    crawl = cfg.get("crawl", {})
    seeds = crawl.get("seeds", [])
    allowed = cfg.get("source", {}).get("allowed_domains", [])
    domain = cfg.get("source", {}).get("base_url", "").split("//")[-1]

    print("Seeds:")
    for s in seeds:
        print(" -", s)

    af = async_fetcher.AsyncFetcher()

    print("\nTesting seeds (HEAD):")
    seed_results = []
    for s in seeds:
        r = test_head(af, s)
        seed_results.append(r)
        print(r)

    print("\nQuerying Wayback (limit 50) for domain:", domain)
    wb_urls = wayback_engine.query_wayback_urls(domain, file_types=["pdf", "xlsx", "csv", "zip"], limit=50)
    print(f"Found {len(wb_urls)} wayback URLs (showing up to 10):")
    for u in wb_urls[:10]:
        print(" -", u)

    print("\nTesting first 10 Wayback URLs (HEAD):")
    wb_results = []
    for u in wb_urls[:10]:
        r = test_head(af, u)
        wb_results.append(r)
        print(r)

    print("\nDiscovering subdomains via crt.sh:")
    subs = subdomain_finder.find_subdomains(domain)
    print(f"Found {len(subs)} subdomains (showing up to 10):")
    for s in subs[:10]:
        print(" -", s)

    print("\nTesting first 10 subdomain roots (HEAD):")
    sub_results = []
    for s in subs[:10]:
        url = f"https://{s}/"
        r = test_head(af, url)
        sub_results.append(r)
        print(r)

    # Summaries
    def summarize(results):
        ok = [r for r in results if r.get("allowed")]
        bad = [r for r in results if not r.get("allowed")]
        return len(ok), len(bad)

    print("\nSummary:")
    print(" Seeds OK/Bad:", summarize(seed_results))
    print(" Wayback OK/Bad:", summarize(wb_results))
    print(" Subdomains OK/Bad:", summarize(sub_results))


if __name__ == "__main__":
    main()
