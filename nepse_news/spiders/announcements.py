import csv
import os
import shutil
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

import scrapy

DATA_FILE = Path("data/announcements.csv")
FIELDS = ["title", "url", "date", "scraped_at"]
DATE_FORMATS = ("%A, %B %d, %Y", "%B %d, %Y", "%d %b, %Y", "%Y-%m-%d")


def clean(text):
    """Collapse newlines/tabs/double spaces so every title is one tidy line."""
    return " ".join((text or "").split())


def parse_date(text):
    text = clean(text)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def load_seen(limit=500):
    # ponytail: top 500 rows only, raise limit if backfilling >500 items
    if not DATA_FILE.exists():
        return set()
    with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
        return {row["url"] for row in islice(csv.DictReader(f), limit) if row.get("url")}


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
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8-sig") as out_f:
            w = csv.DictWriter(
                out_f,
                fieldnames=FIELDS,
                extrasaction="ignore",
                quoting=csv.QUOTE_ALL,   # commas/quotes inside titles are safe
                lineterminator="\n",
            )
            w.writeheader()
            w.writerows(self.new)
            if DATA_FILE.exists():
                with open(DATA_FILE, "r", newline="", encoding="utf-8-sig") as in_f:
                    next(in_f, None)     # skip existing header
                    shutil.copyfileobj(in_f, out_f)
        os.replace(tmp, DATA_FILE)       # atomic: never leaves a half-written file


class AnnouncementsSpider(scrapy.Spider):
    name = "announcements"
    allowed_domains = ["sharesansar.com"]
    START_URL = "https://www.sharesansar.com/announcement"
    MAX_PAGES = 5  # safety cap per run

    handle_httpstatus_list = [403, 404, 429, 503]

    LIST_XPATH = "/html/body/div[2]/div/section[2]/div[3]/div/div/div/div/div[1]/div[4]/div"
    NEXT_XPATHS = (
        '//ul[contains(@class,"pagination")]//a[@rel="next"]/@href',
        "/html/body/div[2]/div/section[2]/div[3]/div/div/div/div/div[1]/div[4]/ul/li[2]/a/@href",
    )

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
        # since: "YYYY-MM-DD" -> ignore anything dated before that day
        self.since = datetime.strptime(since, "%Y-%m-%d").date() if since else None
        self.max_pages = int(max_pages or self.MAX_PAGES)
        self.seen = load_seen()
        self.scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _first_request(self):
        return scrapy.Request(self.START_URL, callback=self.parse, meta={"page": 1})

    async def start(self):          # Scrapy >= 2.13
        yield self._first_request()

    def start_requests(self):       # Scrapy < 2.13
        yield self._first_request()

    def _dump(self, response, page):
        Path("debug").mkdir(exist_ok=True)
        name = f"announcements_page_{page}_status_{response.status}.html"
        (Path("debug") / name).write_bytes(response.body)

    def parse(self, response):
        page = response.meta["page"]

        if response.status != 200:
            self.logger.error("Page %s -> HTTP %s", page, response.status)
            self._dump(response, page)
            return

        rows = response.xpath(self.LIST_XPATH)
        if not rows:
            self.logger.warning("No announcements found on page %s", page)
            self._dump(response, page)
            return

        new_count = 0
        for item in rows:
            title = clean(
                item.xpath("./div[2]/a/@title").get()
                or item.xpath("normalize-space(./div[2]/a)").get()
            )
            href = item.xpath("./div[2]/a/@href").get()
            if not title or not href:
                continue

            url = response.urljoin(href)
            if url in self.seen:
                continue

            raw_date = clean(item.xpath("./div[2]/p/span/text()").get())
            d = parse_date(raw_date)
            if self.since and d and d < self.since:
                continue

            self.seen.add(url)
            new_count += 1
            yield {
                "title": title,
                "url": url,
                "date": f"{d.month}/{d.day}/{d.year}" if d else (raw_date or None),
                "scraped_at": self.scraped_at,
            }

        self.logger.info("Page %s: %s new announcements", page, new_count)

        # keep paging only while we're still finding new items
        if new_count and page < self.max_pages:
            next_page = None
            for xp in self.NEXT_XPATHS:
                next_page = response.xpath(xp).get()
                if next_page:
                    break
            if next_page:
                yield response.follow(
                    next_page, callback=self.parse, meta={"page": page + 1}
                )