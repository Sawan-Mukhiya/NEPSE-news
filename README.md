# NEPSE-news

A continuously maintained dataset of **Nepal Stock Exchange (NEPSE)** stock market news headlines and listed-company corporate announcements, automatically calibrated with company ticker symbols.

**The dataset is updated daily** (at 22:00 NPT), with new entries added to the top of each file.

---

## Datasets

| File | Description | Source | Coverage | Records |
| :--- | :--- | :--- | :--- | :--- |
| [`data/nepse_headlines.csv`](data/nepse_headlines.csv) | English-language NEPSE stock & market news headlines | `nepsetrading.com` | `4/18/2024` – Present | 3,290+ |
| [`data/announcements.csv`](data/announcements.csv) | Listed company corporate announcements (financials, AGMs, dividends, book closures, auctions, etc.) | `sharesansar.com` | `3/16/2011` – Present | 41,900+ |
| [`data/stocks.json`](data/stocks.json) | NEPSE listed security reference master (names, symbols, sectors, instruments, statuses) | NEPSE | Active & historical | 651 securities |

---

## Data Format

Both CSV files follow a consistent, parser-safe format:

- **Encoding**: UTF-8 with BOM (`utf-8-sig`)
- **Line endings**: Unix (`\n`)
- **Quoting**: All fields wrapped in double quotes (`"..."`) so commas, apostrophes, and special characters in headlines never break CSV parsing
- **Ordering**: **Newest first** (latest entries appear at the top)
- **Deduplication**: Unique by `url`

---

## Schema

### 1. `data/nepse_headlines.csv`

| Column | Type / Format | Description | Example |
| :--- | :--- | :--- | :--- |
| `title` | `string` | Single-line news headline | `"NIC Asia Bank Sets November 26 Book Closure for 50 Percent Rights Share Issue"` |
| `published` | `M/D/YYYY` | Normalized publication date | `"11/13/2026"` |
| `published_raw` | `string` | Original date text from the source | `"13 Nov, 2026"` |
| `tag` | `string` | News category tag (e.g. `Stock`, `Economy`) | `"Stock"` |
| `symbol` | `string` | Calibrated NEPSE stock ticker symbol (blank for general/macro news) | `"NICA"` |
| `url` | `string` | Canonical English article URL (`?lang=en`) | `"https://nepsetrading.com/news/...?lang=en"` |
| `scraped_at` | `ISO-8601 UTC` | Timestamp when collected (blank for historical backfill rows) | `"2026-11-13T05:51:44+00:00"` |

### 2. `data/announcements.csv`

| Column | Type / Format | Description | Example |
| :--- | :--- | :--- | :--- |
| `title` | `string` | Single-line corporate announcement title | `"Manakamana Engineering Hydropower Limited has posted a net profit..."` |
| `symbol` | `string` | Calibrated NEPSE stock ticker symbol (blank if company is unlisted/unmatched) | `"MEHL"` |
| `url` | `string` | Canonical announcement detail URL | `"https://www.sharesansar.com/announcementdetail/..."` |
| `date` | `M/D/YYYY` | Normalized announcement date | `"11/13/2026"` |
| `scraped_at` | `ISO-8601 UTC` | Timestamp when collected (blank for historical backfill rows) | `"2026-11-13T10:17:20+00:00"` |

---

## Symbol Calibration

Every newly scraped headline and announcement is calibrated against `data/stocks.json` via a high-performance single-pass matcher (`nepse_news/symbol_matcher.py`):

1. **Resolution Priority**: When companies have multiple listed instruments (e.g., Equity, Debentures, Mutual Funds), the matcher resolves by:
   - Exact `securityName` match first (e.g. *"Nabil Balanced Fund-3"* &rarr; `NBF3`).
   - Active status (`status == "A"`) and `Equity` instrument precedence over secondary instruments (e.g. *"NIC Asia Bank"* &rarr; `NICA` rather than `NICEF`).
   - Ticker token matching (e.g. `\bNICEF\b` &rarr; `NICEF`).
2. **General Market News**: General market commentary, macroeconomic policy updates, or commodity reports without a specific listed entity will have an empty `symbol` field (`""`).

---

## Quick Usage (Python)

```python
import pandas as pd

# Load datasets
headlines = pd.read_csv("data/nepse_headlines.csv")
announcements = pd.read_csv("data/announcements.csv")

# Filter news for a specific stock ticker
nica_news = headlines[headlines["symbol"] == "NICA"]

# Filter announcements for a specific stock ticker
mehl_announcements = announcements[announcements["symbol"] == "MEHL"]
```

---

## Running Scrapers Locally

```bash
# Scrape news headlines
scrapy crawl news

# Scrape corporate announcements
scrapy crawl announcements

# Run symbol backfill on existing CSVs
python -m nepse_news.symbol_matcher --backfill
```
