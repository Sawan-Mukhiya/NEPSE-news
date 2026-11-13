import csv
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import scrapy

DATA_FILE = Path("data/nepse_headlines.csv")
FIELDS = ["title", "published", "published_raw", "tag", "url", "scraped_at"]
DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})")


def clean(text):
    """Collapse newlines/tabs/double spaces so every title is one tidy line."""
    return " ".join((text or "").split())


def parse_date(text):
    """'6 Nov, 2026' -> datetime.date (None if not found)."""
    m = DATE_RE.search(text or "")
    if not m:
        return None
    day, mon, year = m.groups()
    try:
        return datetime.strptime(f"{day} {mon[:3].title()} {year}", "%d %b %Y").date()
    except ValueError:
        return None


def force_english(url):
    p = urlparse(url)
    q = parse_qs(p.query)
    q["lang"] = ["en"]
    return urlunparse(p._replace(query=urlencode(q, doseq=True)))


def load_seen():
    if not DATA_FILE.exists():
        return set()
    with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
        return {row["url"] for row in csv.DictReader(f) if row.get("url")}


class CsvPrependPipeline:
    """Puts this run's new rows on top of the existing CSV (newest first)."""

    def open_spider(self, spider):
        self.new = []

    def process_item(self, item, spider):
        self.new.append(item)
        return item

    def close_spider(self, spider):
        if not self.new:
            return
        old = []
        if DATA_FILE.exists():
            with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
                old = list(csv.DictReader(f))
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(
                f,
                fieldnames=FIELDS,
                extrasaction="ignore",
                quoting=csv.QUOTE_ALL,   # commas/quotes inside titles are safe
                lineterminator="\n",
            )
            w.writeheader()
            w.writerows(self.new + old)
        os.replace(tmp, DATA_FILE)       # atomic: never leaves a half-written file


class NewsSpider(scrapy.Spider):
    name = "news"
    allowed_domains = ["nepsetrading.com"]
    BASE = "https://nepsetrading.com/news/tag/Stock"
    MAX_PAGES = 5  # safety cap per run

    handle_httpstatus_list = [403, 404, 429, 503]

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 1,
        "RETRY_TIMES": 3,
        "USER_AGENT": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "DEFAULT_REQUEST_HEADERS": {"Accept-Language": "en-US,en;q=0.9"},
        "ITEM_PIPELINES": {f"{__name__}.CsvPrependPipeline": 300},
    }

    def __init__(self, since=None, max_pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # since: "YYYY-MM-DD" -> ignore anything published before this day
        self.since = datetime.strptime(since, "%Y-%m-%d").date() if since else None
        self.max_pages = int(max_pages or self.MAX_PAGES)
        self.seen = load_seen()
        self.scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _page_url(self, page):
        return f"{self.BASE}?lang=en" if page == 1 else f"{self.BASE}/p/{page}?lang=en"

    def _request(self, page):
        return scrapy.Request(self._page_url(page), callback=self.parse, meta={"page": page})

    async def start(self):          # Scrapy >= 2.13
        yield self._request(1)

    def start_requests(self):       # Scrapy < 2.13
        yield self._request(1)

    def _dump(self, response, page):
        Path("debug").mkdir(exist_ok=True)
        (Path("debug") / f"page_{page}_status_{response.status}.html").write_bytes(response.body)

    def parse(self, response):
        page = response.meta["page"]

        if response.status != 200:
            self.logger.error("Page %s -> HTTP %s", page, response.status)
            self._dump(response, page)
            return

        cards = response.xpath("//article[.//h3]")
        if not cards:
            self.logger.warning("No cards on page %s", page)
            self._dump(response, page)
            return

        new_count = 0
        for card in cards:
            title = clean(
                card.xpath("normalize-space(.//h3/span[last()])").get()
                or card.xpath("normalize-space(.//h3)").get()
            )
            href = card.xpath(".//a[.//h3]/@href").get()
            if not title or not href:
                continue

            url = force_english(response.urljoin(href))
            if url in self.seen:
                continue

            raw_date = (
                card.xpath("normalize-space(.//time)").get()
                or card.xpath(".//time/@datetime").get()
                or card.xpath("normalize-space(.)").get()
            )
            d = parse_date(raw_date)
            if self.since and d and d < self.since:
                continue

            self.seen.add(url)
            new_count += 1
            yield {
                "title": title,
                "published": f"{d.month}/{d.day}/{d.year}" if d else None,
                "published_raw": raw_date if len(raw_date or "") < 40 else None,
                "tag": card.xpath("normalize-space(.//a[contains(@href,'/news/tag/')][1])").get(),
                "url": url,
                "scraped_at": self.scraped_at,
            }

        self.logger.info("Page %s: %s new headlines", page, new_count)

        # keep paging only while we are still finding new stuff
        if new_count and page < self.max_pages:
            yield self._request(page + 1)