"""Core enrichment engine for ENRICHR.

A *Provider* takes a normalized lead (mainly its company domain) and returns
firmographic fields (company name, industry, employee count, location, ...).
Providers are pluggable: the built-ins do real, deterministic work with no
network, and you can drop in your own (Apollo/Clearbit/etc.) by subclassing
``Provider``.

A *Cache* persists results keyed by ``provider:domain`` to a JSON file so the
same domain is never looked up twice — the whole point of avoiding duplicate
spend against a paid API.
"""
from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

# Public email providers — a lead with one of these has no usable company
# domain, so heuristic enrichment must not invent firmographics for them.
FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "aol.com", "icloud.com", "me.com",
    "mac.com", "proton.me", "protonmail.com", "gmx.com", "zoho.com",
    "mail.com", "yandex.com", "fastmail.com",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@([^@\s]+\.[^@\s]+)$")
_DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/\s]+)")


@dataclass
class Lead:
    """A normalized input lead. Free-form extra columns ride along in ``raw``."""
    email: str = ""
    company: str = ""
    domain: str = ""
    name: str = ""
    raw: Dict[str, str] = field(default_factory=dict)

    def resolved_domain(self) -> str:
        """Best-effort company domain: explicit domain, else from the email."""
        if self.domain:
            return normalize_domain(self.domain)
        return domain_from_email(self.email)


@dataclass
class EnrichmentResult:
    """Firmographics for one lead."""
    email: str = ""
    domain: str = ""
    company_name: str = ""
    industry: str = ""
    employee_count: Optional[int] = None
    size_bucket: str = ""
    country: str = ""
    provider: str = ""
    cached: bool = False
    status: str = "ok"          # ok | no_domain | free_email | unenriched
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def normalize_domain(value: str) -> str:
    """Strip scheme/www/path/port and lowercase. ``HTTPS://WWW.A.com/x`` -> ``a.com``."""
    value = (value or "").strip().lower()
    if not value:
        return ""
    m = _DOMAIN_RE.match(value)
    host = m.group(1) if m else value
    return host.split(":")[0].rstrip(".")


def domain_from_email(email: str) -> str:
    """Return the domain part of an email, normalized; ``""`` if not an email."""
    email = (email or "").strip().lower()
    m = _EMAIL_RE.match(email)
    if not m:
        return ""
    return normalize_domain(m.group(1))


def is_free_email_domain(domain: str) -> bool:
    return normalize_domain(domain) in FREE_EMAIL_DOMAINS


def company_size_bucket(employees: Optional[int]) -> str:
    """Map an employee headcount to a standard firmographic size band."""
    if employees is None:
        return ""
    if employees < 0:
        return ""
    if employees <= 10:
        return "1-10"
    if employees <= 50:
        return "11-50"
    if employees <= 200:
        return "51-200"
    if employees <= 1000:
        return "201-1000"
    if employees <= 5000:
        return "1001-5000"
    return "5000+"


def _company_from_domain(domain: str) -> str:
    """Derive a human company name from a domain (``acme-corp.io`` -> ``Acme Corp``)."""
    if not domain:
        return ""
    label = domain.split(".")[0]
    words = re.split(r"[-_]+", label)
    return " ".join(w.capitalize() for w in words if w)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class Provider:
    """Base provider. Override :meth:`lookup` with real logic / an API call."""

    name = "base"

    def lookup(self, domain: str) -> Optional[Dict[str, object]]:
        """Return firmographics dict for ``domain`` or ``None`` if unknown.

        Keys understood by the engine: company_name, industry, employee_count,
        country, confidence.
        """
        raise NotImplementedError


# Lightweight TLD-country and keyword-industry maps used by the heuristic
# provider. These are deterministic, offline, and good enough to be useful
# for triage before you spend on a paid provider.
_TLD_COUNTRY = {
    "us": "United States", "io": "United States", "ai": "United States",
    "uk": "United Kingdom", "co.uk": "United Kingdom",
    "de": "Germany", "fr": "France", "es": "Spain", "it": "Italy",
    "nl": "Netherlands", "se": "Sweden", "ca": "Canada", "au": "Australia",
    "jp": "Japan", "in": "India", "br": "Brazil", "ch": "Switzerland",
}

_INDUSTRY_KEYWORDS = [
    ("Financial Services", ("bank", "capital", "finance", "fund", "invest", "trade", "equity", "asset")),
    ("Energy", ("energy", "solar", "power", "grid", "oil", "gas", "nuclear", "renew")),
    ("Healthcare", ("health", "med", "bio", "pharma", "care", "clinic", "therapeut")),
    ("Software", ("soft", "app", "cloud", "data", "ai", "labs", "tech", "io", "dev", "code")),
    ("Retail", ("shop", "store", "retail", "market", "commerce", "goods")),
    ("Logistics", ("ship", "logistic", "freight", "cargo", "supply", "transport")),
    ("Education", ("edu", "learn", "academy", "school", "university", "training")),
    ("Media", ("media", "news", "press", "studio", "film", "music")),
]


class HeuristicProvider(Provider):
    """Offline, deterministic enrichment from the domain string itself.

    No network, no fabricated headcounts: it derives a company name, guesses an
    industry from keywords, and a country from the TLD. ``employee_count`` is
    left ``None`` (unknown) so we never invent a number we can't justify.
    """

    name = "heuristic"

    def lookup(self, domain: str) -> Optional[Dict[str, object]]:
        domain = normalize_domain(domain)
        if not domain or is_free_email_domain(domain):
            return None

        industry = ""
        hay = domain.lower()
        for label, kws in _INDUSTRY_KEYWORDS:
            if any(k in hay for k in kws):
                industry = label
                break

        country = ""
        parts = domain.split(".")
        if len(parts) >= 3 and ".".join(parts[-2:]) in _TLD_COUNTRY:
            country = _TLD_COUNTRY[".".join(parts[-2:])]
        elif parts[-1] in _TLD_COUNTRY:
            country = _TLD_COUNTRY[parts[-1]]

        confidence = 0.3
        if industry:
            confidence += 0.2
        if country:
            confidence += 0.1

        return {
            "company_name": _company_from_domain(domain),
            "industry": industry,
            "employee_count": None,
            "country": country,
            "confidence": round(confidence, 2),
        }


class MappingProvider(Provider):
    """Provider backed by a domain->firmographics dict (e.g. a CRM export).

    This is how you'd plug a real dataset: load a JSON file mapping domains to
    known firmographics and pass it here. High confidence because it's ground
    truth, not a guess.
    """

    name = "mapping"

    def __init__(self, data: Dict[str, Dict[str, object]], name: str = "mapping"):
        self._data = {normalize_domain(k): v for k, v in (data or {}).items()}
        self.name = name

    @classmethod
    def from_json_file(cls, path: str, name: str = "mapping") -> "MappingProvider":
        with open(path, "r", encoding="utf-8") as fh:
            return cls(json.load(fh), name=name)

    def lookup(self, domain: str) -> Optional[Dict[str, object]]:
        rec = self._data.get(normalize_domain(domain))
        if rec is None:
            return None
        out = dict(rec)
        out.setdefault("confidence", 0.95)
        return out


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class Cache:
    """JSON-file cache keyed by ``provider:domain`` to avoid duplicate lookups."""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._store: Dict[str, Dict[str, object]] = {}
        self.hits = 0
        self.misses = 0
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    self._store = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self._store = {}

    @staticmethod
    def _key(provider: str, domain: str) -> str:
        return f"{provider}:{normalize_domain(domain)}"

    def get(self, provider: str, domain: str) -> Optional[Dict[str, object]]:
        val = self._store.get(self._key(provider, domain))
        if val is not None:
            self.hits += 1
        else:
            self.misses += 1
        return val

    def put(self, provider: str, domain: str, value: Dict[str, object]) -> None:
        self._store[self._key(provider, domain)] = value

    def save(self) -> None:
        if not self.path:
            return
        d = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._store, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def __len__(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# CSV IO
# ---------------------------------------------------------------------------

_EMAIL_COLS = ("email", "e-mail", "email_address", "work_email")
_COMPANY_COLS = ("company", "company_name", "organization", "account")
_DOMAIN_COLS = ("domain", "website", "url", "company_domain")
_NAME_COLS = ("name", "full_name", "contact", "contact_name")


def _pick(row: Dict[str, str], cols: Iterable[str]) -> str:
    for c in cols:
        for k, v in row.items():
            if k and k.strip().lower() == c and (v or "").strip():
                return v.strip()
    return ""


def read_leads_csv(path: str) -> List[Lead]:
    """Read a leads CSV, auto-detecting email/company/domain/name columns."""
    leads: List[Lead] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return leads
        for row in reader:
            row = {(k or ""): (v or "") for k, v in row.items()}
            leads.append(Lead(
                email=_pick(row, _EMAIL_COLS),
                company=_pick(row, _COMPANY_COLS),
                domain=_pick(row, _DOMAIN_COLS),
                name=_pick(row, _NAME_COLS),
                raw=row,
            ))
    return leads


_RESULT_FIELDS = [
    "email", "domain", "company_name", "industry", "employee_count",
    "size_bucket", "country", "provider", "cached", "status", "confidence",
]


def write_results_csv(results: List[EnrichmentResult], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_RESULT_FIELDS)
        writer.writeheader()
        for r in results:
            writer.writerow({k: ("" if v is None else v) for k, v in r.to_dict().items()})


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def enrich_leads(
    leads: List[Lead],
    providers: List[Provider],
    cache: Optional[Cache] = None,
) -> List[EnrichmentResult]:
    """Enrich each lead by trying providers in order; first hit wins.

    Results are cached per provider+domain. Leads with no resolvable company
    domain (or a free-email domain) are marked but never fabricated.
    """
    results: List[EnrichmentResult] = []

    for lead in leads:
        domain = lead.resolved_domain()
        res = EnrichmentResult(email=lead.email, domain=domain)

        if not domain:
            res.status = "no_domain"
            res.company_name = lead.company
            results.append(res)
            continue

        if is_free_email_domain(domain):
            res.status = "free_email"
            res.company_name = lead.company
            results.append(res)
            continue

        record = None
        used_provider = ""
        was_cached = False

        for provider in providers:
            if cache is not None:
                hit = cache.get(provider.name, domain)
                if hit is not None:
                    record, used_provider, was_cached = hit, provider.name, True
                    break
            found = provider.lookup(domain)
            if found is not None:
                if cache is not None:
                    cache.put(provider.name, domain, found)
                record, used_provider = found, provider.name
                break

        if record is None:
            res.status = "unenriched"
            res.company_name = lead.company or _company_from_domain(domain)
            results.append(res)
            continue

        emp = record.get("employee_count")
        emp = int(emp) if isinstance(emp, (int, float)) else None
        res.company_name = str(record.get("company_name") or lead.company or _company_from_domain(domain))
        res.industry = str(record.get("industry") or "")
        res.employee_count = emp
        res.size_bucket = company_size_bucket(emp)
        res.country = str(record.get("country") or "")
        res.provider = used_provider
        res.cached = was_cached
        res.confidence = float(record.get("confidence") or 0.0)
        res.status = "ok"
        results.append(res)

    if cache is not None:
        cache.save()
    return results
