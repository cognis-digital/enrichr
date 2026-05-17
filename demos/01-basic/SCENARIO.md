# Demo 01 — Basic lead enrichment

## What this shows

`enrichr` reads a messy real-world leads CSV (`leads.csv`) where the company
domain sometimes lives in a `website` column, sometimes only in the email, and
sometimes is missing entirely. It auto-detects the relevant columns, resolves a
company domain for each lead, and enriches it with firmographics.

Two providers are combined:

1. **MappingProvider** (`crm.json`) — your known, ground-truth firmographics
   (e.g. an export from your CRM or a paid API). Tried first, highest confidence.
2. **HeuristicProvider** — a fully offline fallback that derives a company name,
   guesses an industry from keywords, and infers a country from the TLD. It never
   invents an employee count it can't justify.

A local JSON cache (`--cache`) stores each `provider:domain` result so re-runs
make zero provider calls for already-seen domains — the point of avoiding
duplicate spend against a paid enrichment API.

## Run it

```bash
# Heuristic-only, table output
python -m enrichr enrich demos/01-basic/leads.csv --allow-partial

# CRM mapping first, then heuristics, with a cache, JSON output
python -m enrichr enrich demos/01-basic/leads.csv \
    --mapping demos/01-basic/crm.json \
    --cache .enrichr_cache.json \
    --format json
```

## Expected result

- `greenway-energy.com` and `helixbio.io` enrich from `crm.json` with real
  headcounts (240 -> size `201-1000`, 48 -> size `11-50`) at confidence ~0.95.
- `northpeak-capital.com`, `cloudforge.dev`, `bergdata.se`, `shopharbor.co.uk`
  enrich heuristically: industries like `Financial Services`, `Software`,
  countries like `Sweden` / `United Kingdom` from the TLD.
- `tom.becker@gmail.com` is flagged `free_email` (no company domain to enrich).
- The row with no email/domain is flagged `no_domain`.

Because two leads cannot be enriched, the command **exits 1** by default — useful
as a CI gate that fails when your list has too much junk. Pass `--allow-partial`
to force exit 0. Re-running with `--cache` reports cache **hits** instead of misses.
