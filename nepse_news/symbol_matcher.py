"""Fast, stdlib-only NEPSE stock symbol matcher using data/stocks.json."""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

DEFAULT_STOCKS_PATH = Path("data/stocks.json")

_SUFFIX_RE = re.compile(
    r"(?:\s+(?:pvt\.?\s*ltd\.?|limited|ltd\.?))+\s*$",
    re.IGNORECASE,
)
_PUNCT_SPACE_RE = re.compile(r"[-–—/]+")


def _norm(text: str) -> str:
    """Normalize whitespace and dashes for resilient name matching."""
    text = _PUNCT_SPACE_RE.sub(" ", text or "")
    return " ".join(text.split()).lower()


class SymbolMatcher:
    """Matches news/announcement titles to NEPSE stock symbols in a single regex pass."""

    def __init__(self, stocks_path: Path | str = DEFAULT_STOCKS_PATH) -> None:
        self._name_to_symbol: dict[str, str] = {}
        self._name_re: re.Pattern[str] | None = None
        self._sym_re: re.Pattern[str] | None = None
        self._load(Path(stocks_path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            return

        with open(path, encoding="utf-8") as f:
            stocks = json.load(f)

        best: dict[str, tuple[tuple[int, int, int], str]] = {}
        symbols: list[str] = []

        def register(raw_name: str | None, symbol: str, rank: tuple[int, int, int]) -> None:
            normed = _norm(raw_name or "")
            if not normed or len(normed) < 4:
                return
            variants = {normed}
            stripped = _SUFFIX_RE.sub("", normed).strip(" .,")
            if len(stripped) >= 4:
                variants.add(stripped)
            for v in variants:
                prev = best.get(v)
                if prev is None or rank > prev[0]:
                    best[v] = (rank, symbol)

        for entry in stocks:
            symbol = (entry.get("symbol") or "").strip()
            if not symbol:
                continue
            symbols.append(symbol)
            is_active = 1 if entry.get("status") == "A" else 0
            is_equity = 1 if entry.get("instrumentType") == "Equity" else 0

            register(entry.get("securityName"), symbol, (2, is_active, is_equity))
            register(entry.get("companyName"), symbol, (1, is_active, is_equity))

        self._name_to_symbol = {name: sym for name, (_, sym) in best.items()}

        if self._name_to_symbol:
            # Longest-first ensures specific names (e.g. "Nabil Balanced Fund 3") beat shorter prefixes.
            names_alt = "|".join(
                re.escape(n) for n in sorted(self._name_to_symbol, key=len, reverse=True)
            )
            self._name_re = re.compile(rf"(?<!\w)(?:{names_alt})(?!\w)")

        if symbols:
            syms_alt = "|".join(
                re.escape(s) for s in sorted(set(symbols), key=len, reverse=True)
            )
            self._sym_re = re.compile(rf"(?<!\w)(?:{syms_alt})(?!\w)")

    def match(self, title: str | None) -> str:
        """Return the best matching NEPSE symbol for a title, or '' if none."""
        if not title:
            return ""
        if self._name_re is not None:
            m = self._name_re.search(_norm(title))
            if m:
                return self._name_to_symbol[m.group(0)]
        if self._sym_re is not None:
            m = self._sym_re.search(title)
            if m:
                return m.group(0)
        return ""


def backfill_csv(path: Path, fields: list[str], matcher: SymbolMatcher) -> tuple[int, int]:
    """Add/update the 'symbol' column in an existing CSV atomically. Returns (total, matched)."""
    if not path.exists():
        return 0, 0

    with open(path, "r", newline="", encoding="utf-8-sig") as in_f:
        rows = list(csv.DictReader(in_f))

    matched = 0
    for row in rows:
        sym = matcher.match(row.get("title"))
        row["symbol"] = sym
        if sym:
            matched += 1

    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as out_f:
        writer = csv.DictWriter(
            out_f,
            fieldnames=fields,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)
    return len(rows), matched


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NEPSE symbol matcher & CSV backfill")
    parser.add_argument("--backfill", action="store_true", help="Backfill symbol column in CSVs")
    args = parser.parse_args()

    if args.backfill:
        matcher = SymbolMatcher()
        targets = [
            (
                Path("data/nepse_headlines.csv"),
                ["title", "published", "published_raw", "tag", "symbol", "url", "scraped_at"],
            ),
            (
                Path("data/announcements.csv"),
                ["title", "symbol", "url", "date", "scraped_at"],
            ),
        ]
        for csv_path, csv_fields in targets:
            total, hits = backfill_csv(csv_path, csv_fields, matcher)
            print(f"{csv_path}: {hits}/{total} matched")
