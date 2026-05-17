"""Command-line interface for ENRICHR."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from enrichr import TOOL_NAME, TOOL_VERSION
from enrichr.core import (
    Cache,
    HeuristicProvider,
    MappingProvider,
    Provider,
    enrich_leads,
    read_leads_csv,
    write_results_csv,
)

EXAMPLES = """\
examples:
  # Enrich a leads CSV with the offline heuristic provider, print a table
  enrichr enrich demos/01-basic/leads.csv

  # Use a known-firmographics dataset first, then fall back to heuristics
  enrichr enrich leads.csv --mapping crm.json --cache .enrichr_cache.json

  # JSON out for piping into jq / CI
  enrichr enrich leads.csv --format json | jq '.results[] | select(.status=="ok")'

  # Write enriched rows back to a CSV
  enrichr enrich leads.csv -o enriched.csv

exit codes:
  0  every lead was enriched (status == ok)
  1  one or more leads could not be enriched (use for CI gates)
  2  usage / input error
"""


def _build_providers(args: argparse.Namespace) -> List[Provider]:
    providers: List[Provider] = []
    if args.mapping:
        try:
            providers.append(MappingProvider.from_json_file(args.mapping))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"error: could not load mapping {args.mapping!r}: {exc}")
    if not args.no_heuristic:
        providers.append(HeuristicProvider())
    if not providers:
        raise SystemExit("error: no providers enabled (gave --no-heuristic with no --mapping)")
    return providers


def _print_table(results, summary) -> None:
    headers = ["email", "domain", "company_name", "industry", "size", "country", "provider", "cached", "status"]
    rows = []
    for r in results:
        rows.append([
            r.email, r.domain, r.company_name, r.industry,
            r.size_bucket, r.country, r.provider,
            "yes" if r.cached else "", r.status,
        ])
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))
    print()
    print(
        f"{summary['total']} leads | {summary['enriched']} enriched | "
        f"{summary['unenriched']} unenriched | "
        f"cache hits {summary['cache_hits']} / misses {summary['cache_misses']}"
    )


def _cmd_enrich(args: argparse.Namespace) -> int:
    try:
        leads = read_leads_csv(args.input)
    except OSError as exc:
        print(f"error: cannot read {args.input!r}: {exc}", file=sys.stderr)
        return 2

    fmt = args.sub_format or args.format
    providers = _build_providers(args)
    cache = Cache(args.cache) if args.cache else None
    results = enrich_leads(leads, providers, cache=cache)

    enriched = sum(1 for r in results if r.status == "ok")
    summary = {
        "total": len(results),
        "enriched": enriched,
        "unenriched": len(results) - enriched,
        "cache_hits": cache.hits if cache else 0,
        "cache_misses": cache.misses if cache else 0,
    }

    if args.output:
        write_results_csv(results, args.output)

    if fmt == "json":
        print(json.dumps({
            "tool": TOOL_NAME,
            "version": TOOL_VERSION,
            "summary": summary,
            "results": [r.to_dict() for r in results],
        }, indent=2))
    else:
        if results:
            _print_table(results, summary)
        else:
            print("no leads found in input")
        if args.output:
            print(f"wrote {len(results)} rows to {args.output}")

    # Non-zero when any lead failed to enrich, unless caller relaxed it.
    if summary["unenriched"] > 0 and not args.allow_partial:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Enrich a leads CSV with firmographics from pluggable providers, with a local cache.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    parser.add_argument(
        "--format", choices=["table", "json"], default="table",
        help="output format (default: table; json for piping/CI)",
    )

    sub = parser.add_subparsers(dest="command", metavar="command")

    p_enrich = sub.add_parser(
        "enrich",
        help="enrich a leads CSV",
        description="Read a leads CSV (auto-detecting email/company/domain columns) and enrich each row.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_enrich.add_argument("input", help="path to leads CSV")
    p_enrich.add_argument(
        "--format", choices=["table", "json"], default=None, dest="sub_format",
        help="output format for this command (overrides the global --format)",
    )
    p_enrich.add_argument("-o", "--output", help="write enriched rows to this CSV")
    p_enrich.add_argument("--cache", help="JSON cache file (created if missing) to avoid duplicate lookups")
    p_enrich.add_argument("--mapping", help="JSON file mapping domain -> firmographics (tried before heuristics)")
    p_enrich.add_argument("--no-heuristic", action="store_true", help="disable the offline heuristic provider")
    p_enrich.add_argument(
        "--allow-partial", action="store_true",
        help="exit 0 even if some leads are unenriched (default: exit 1)",
    )
    p_enrich.set_defaults(func=_cmd_enrich)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        return int(exc.code or 0)


if __name__ == "__main__":
    sys.exit(main())
