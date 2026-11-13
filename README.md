# NEPSE-news

A continuously maintained dataset of **Nepal Stock Exchange (NEPSE)** stock market news headlines and listed-company corporate announcements.

**The dataset is updated daily** (at 22:00 NPT), with new entries added to the top of each file.

---

## Datasets

| File | Description | Source | Coverage | Records |
| :--- | :--- | :--- | :--- | :--- |
| [`data/nepse_headlines.csv`](data/nepse_headlines.csv) | English-language NEPSE stock & market news headlines | `nepsetrading.com` | `4/18/2024` – `11/13/2026`+ | 3,256+ |
| [`data/announcements.csv`](data/announcements.csv) | Listed company corporate announcements (financials, AGMs, dividends, book closures, auctions, etc.) | `sharesansar.com` | `3/16/2011` – `11/13/2026`+ | 41,810+ |

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
| `title` | `string` | Single-line news headline | `"Stock Market Reopens Today After Tihar Holidays..."` |
| `published` | `M/D/YYYY` | Normalized publication date | `"11/13/2026"` |
| `published_raw` | `string` | Original date text from the source | `"13 Nov, 2026"` |
| `tag` | `string` | News category tag (e.g. `Stock`, `Economy`) | `"Stock"` |
| `url` | `string` | Canonical English article URL (`?lang=en`) | `"https://nepsetrading.com/news/...?lang=en"` |
| `scraped_at` | `ISO-8601 UTC` | Timestamp when collected (blank for historical backfill rows) | `"2026-11-13T05:51:44+00:00"` |

### 2. `data/announcements.csv`

| Column | Type / Format | Description | Example |
| :--- | :--- | :--- | :--- |
| `title` | `string` | Single-line corporate announcement title | `"Ganapati Laghubitta Bittiya Sanstha Limited has posted..."` |
| `url` | `string` | Canonical announcement detail URL | `"https://www.sharesansar.com/announcementdetail/..."` |
| `date` | `M/D/YYYY` | Normalized announcement date | `"11/13/2026"` |
| `scraped_at` | `ISO-8601 UTC` | Timestamp when collected (blank for historical backfill rows) | `"2026-11-13T10:17:20+00:00"` |

---

## Quick Usage (Python)

```python
import pandas as pd

headlines = pd.read_csv("data/nepse_headlines.csv")
announcements = pd.read_csv("data/announcements.csv")
```
