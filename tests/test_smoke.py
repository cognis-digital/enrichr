"""Smoke tests for ENRICHR — import the core engine, run it on the demo data,
and assert real behavior (no network)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from enrichr import TOOL_NAME, TOOL_VERSION  # noqa: E402
from enrichr.core import (  # noqa: E402
    Cache,
    HeuristicProvider,
    MappingProvider,
    company_size_bucket,
    domain_from_email,
    enrich_leads,
    normalize_domain,
    read_leads_csv,
    write_results_csv,
)
from enrichr.cli import main  # noqa: E402

DEMO = os.path.join(ROOT, "demos", "01-basic")
LEADS = os.path.join(DEMO, "leads.csv")
CRM = os.path.join(DEMO, "crm.json")


def test_metadata():
    assert TOOL_NAME == "enrichr"
    assert TOOL_VERSION.count(".") == 2


def test_domain_helpers():
    assert domain_from_email("a@Foo.com") == "foo.com"
    assert domain_from_email("not-an-email") == ""
    assert normalize_domain("HTTPS://WWW.Acme.io/path") == "acme.io"
    assert company_size_bucket(48) == "11-50"
    assert company_size_bucket(240) == "201-1000"
    assert company_size_bucket(None) == ""


def test_read_demo_leads_autodetect():
    leads = read_leads_csv(LEADS)
    assert len(leads) == 8
    by_email = {l.email: l for l in leads}
    assert by_email["jane@greenway-energy.com"].resolved_domain() == "greenway-energy.com"
    assert by_email["marcus.lee@northpeak-capital.com"].resolved_domain() == "northpeak-capital.com"


def test_heuristic_industry_and_country():
    h = HeuristicProvider()
    fin = h.lookup("northpeak-capital.com")
    assert fin["industry"] == "Financial Services"
    se = h.lookup("bergdata.se")
    assert se["country"] == "Sweden"
    # free-email domain is never fabricated
    assert h.lookup("gmail.com") is None


def test_mapping_provider_ground_truth():
    m = MappingProvider.from_json_file(CRM)
    rec = m.lookup("greenway-energy.com")
    assert rec["employee_count"] == 240
    assert rec["company_name"] == "Greenway Energy Capital"


def test_enrich_end_to_end():
    leads = read_leads_csv(LEADS)
    providers = [MappingProvider.from_json_file(CRM), HeuristicProvider()]
    results = enrich_leads(leads, providers)
    by_email = {r.email: r for r in results}

    # mapping wins -> real headcount + size bucket
    g = by_email["jane@greenway-energy.com"]
    assert g.provider == "mapping"
    assert g.employee_count == 240
    assert g.size_bucket == "201-1000"
    assert g.status == "ok"

    # heuristic fallback
    n = by_email["marcus.lee@northpeak-capital.com"]
    assert n.provider == "heuristic"
    assert n.industry == "Financial Services"
    assert n.status == "ok"

    # free email + no domain are flagged, not fabricated
    assert by_email["tom.becker@gmail.com"].status == "free_email"
    assert by_email[""].status == "no_domain"


def test_cache_avoids_second_lookup(tmp_path):
    cache_path = str(tmp_path / "cache.json")
    leads = read_leads_csv(LEADS)
    providers = [HeuristicProvider()]

    c1 = Cache(cache_path)
    enrich_leads(leads, providers, cache=c1)
    assert c1.misses > 0
    assert os.path.exists(cache_path)

    # second run: enrichable domains served from cache
    c2 = Cache(cache_path)
    results = enrich_leads(leads, providers, cache=c2)
    assert c2.hits > 0
    assert any(r.cached for r in results if r.status == "ok")


def test_write_results_csv(tmp_path):
    leads = read_leads_csv(LEADS)
    results = enrich_leads(leads, [HeuristicProvider()])
    out = str(tmp_path / "out.csv")
    write_results_csv(results, out)
    with open(out, encoding="utf-8") as fh:
        text = fh.read()
    assert "company_name" in text
    assert "northpeak-capital.com" in text


def test_cli_json_and_exit_codes(capsys):
    # default: some leads unenriched -> exit 1
    code = main(["--format", "json", "enrich", LEADS, "--mapping", CRM])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["tool"] == "enrichr"
    assert payload["summary"]["total"] == 8
    assert payload["summary"]["enriched"] >= 6
    assert code == 1  # free_email + no_domain remain unenriched

    # --allow-partial relaxes the gate to exit 0
    code2 = main(["enrich", LEADS, "--mapping", CRM, "--allow-partial"])
    assert code2 == 0


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "enrichr" in capsys.readouterr().out
