import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse


# ============================================================
# FLATHEAD LIVE
# ============================================================

app = FastAPI(title="Flathead Live")

DATABASE = "events.db"

SOURCES = {
    "Explore Whitefish": {
        "url": "https://explorewhitefish.com/events?face=list",
        "city": "Whitefish",
    },
    "Whitefish Chamber": {
        "url": "https://business.whitefishchamber.org/events",
        "city": "Whitefish",
    },
}


# ============================================================
# DATABASE
# ============================================================

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            venue TEXT,
            city TEXT,
            category TEXT NOT NULL,
            event_date TEXT,
            description TEXT,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(title, event_date, source_url)
        )
    """)

    connection.commit()
    connection.close()


# ============================================================
# EVENT CLASSIFICATION
# ============================================================

MUSIC_WORDS = [
    "live music",
    "concert",
    "songwriter",
    "songwriters",
    "bluegrass",
    "jazz",
    "music",
    "musician",
    "symphony",
    "piano",
    "dueling pianos",
    "dj ",
    "acoustic",
    "band",
]

FILM_WORDS = [
    "film festival",
    "filmfest",
    "film screening",
    "movie festival",
    "film tour",
    "documentary",
    "cinema",
    "paddling film",
    "fly fishing film",
]

FESTIVAL_WORDS = [
    "festival",
    "fest",
    "fair",
    "celebration",
    "rodeo",
]


def classify_event(title, description=""):
    text = f"{title} {description}".lower()

    if any(word in text for word in FILM_WORDS):
        return "film"

    if any(word in text for word in MUSIC_WORDS):
        return "music"

    if any(word in text for word in FESTIVAL_WORDS):
        return "festival"

    return "other"


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(value):
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


# ============================================================
# SAVE EVENT
# ============================================================

def save_event(
    title,
    venue,
    city,
    category,
    event_date,
    description,
    source,
    source_url,
):
    connection = get_db()

    connection.execute("""
        INSERT OR IGNORE INTO events (
            title,
            venue,
            city,
            category,
            event_date,
            description,
            source,
            source_url,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title,
        venue,
        city,
        category,
        event_date,
        description,
        source,
        source_url,
        datetime.now(timezone.utc).isoformat(),
    ))

    connection.commit()
    connection.close()


# ============================================================
# GENERIC EVENT SCRAPER
# ============================================================

def scrape_source(source_name, source_info):
    url = source_info["url"]
    city = source_info["city"]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(compatible; FlatheadLive/1.0)"
        )
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=20,
        )

        response.raise_for_status()

    except Exception as error:
        print(f"Could not download {source_name}: {error}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # Try common event-card formats.
    cards = soup.select(
        "article, "
        ".event, "
        ".event-card, "
        ".event-item, "
        "[class*='event-card'], "
        "[class*='event-item']"
    )

    print(
        f"{source_name}: found {len(cards)} possible event cards"
    )

    for card in cards:

        text = clean_text(
            card.get_text(" ", strip=True)
        )

        if len(text) < 10:
            continue

        # Try to identify the event title.
        title_element = card.select_one(
            "h1, h2, h3, h4, "
            ".event-title, "
            ".title, "
            "[class*='title']"
        )

        if title_element:
            title = clean_text(
                title_element.get_text(
                    " ",
                    strip=True
                )
            )
        else:
            title = text[:150]

        if not title:
            continue

        # Find event URL.
        link = card.select_one("a[href]")

        if link:
            event_url = urljoin(
                url,
                link.get("href")
            )
        else:
            event_url = url

        category = classify_event(
            title,
            text
        )

        # Look for a date/time in the event text.
        date_match = re.search(
            r"""
            (?:
                Jan|Feb|Mar|Apr|May|Jun|
                Jul|Aug|Sep|Oct|Nov|Dec
            )
            \s+
            \d{1,2}
            (?:,\s*\d{4})?
            """,
            text,
            re.IGNORECASE | re.VERBOSE
        )

        event_date = (
            date_match.group(0)
            if date_match
            else ""
        )

        save_event(
            title=title,
            venue="",
            city=city,
            category=category,
            event_date=event_date,
            description=text,
            source=source_name,
            source_url=event_url,
        )


# ============================================================
# REFRESH EVENTS
# ============================================================

def refresh_events():

    print("================================")
    print("Refreshing Flathead events...")
    print("================================")

    for source_name, source_info in SOURCES.items():

        scrape_source(
            source_name,
            source_info
        )

    print("Refresh complete.")


# ============================================================
# HOME PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def home(
    category: str = Query("all"),
):

    connection = get_db()

    if category == "all":

        events = connection.execute("""
            SELECT *
            FROM events
            ORDER BY event_date, title
        """).fetchall()

    else:

        events = connection.execute("""
            SELECT *
            FROM events
            WHERE category = ?
            ORDER BY event_date, title
        """, (
            category,
        )).fetchall()

    connection.close()

    cards = []

    for event in events:

        if event["category"] == "music":
            icon = "🎵"

        elif event["category"] == "film":
            icon = "🎬"

        elif event["category"] == "festival":
            icon = "🎪"

        else:
            icon = "📍"

        cards.append(f"""
        <div class="event">

            <div class="icon">
                {icon}
            </div>

            <div class="event-content">

                <h2>
                    {event["title"]}
                </h2>

                <div class="location">
                    {event["city"] or "Flathead Valley"}
                    {(" · " + event["venue"])
                     if event["venue"] else ""}
                </div>

                <div class="date">
                    {event["event_date"] or "Date TBD"}
                </div>

                <p>
                    {event["description"][:300]}
                </p>

                <a
                    href="{event["source_url"]}"
                    target="_blank"
                    rel="noopener"
                >
                    Original event →
                </a>

            </div>

        </div>
        """)

    event_html = "".join(cards)

    if not event_html:
        event_html = """
        <div class="empty">
            No events found yet.
        </div>
        """

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>Flathead Live</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{

    margin: 0;

    background:
        linear-gradient(
            180deg,
            #07111f,
            #111827
        );

    color: white;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

}}

.container {{

    max-width: 750px;

    margin: auto;

    padding: 24px 18px 50px;

}}

h1 {{

    font-size: 36px;

    margin-bottom: 4px;

}}

.subtitle {{

    color: #9ca3af;

    margin-bottom: 25px;

}}

.filters {{

    display: flex;

    gap: 8px;

    overflow-x: auto;

    padding-bottom: 15px;

}}

.filters a {{

    flex-shrink: 0;

    text-decoration: none;

    color: white;

    background: #263449;

    padding: 9px 15px;

    border-radius: 999px;

}}

.event {{

    display: flex;

    gap: 15px;

    background: #1c2838;

    border-radius: 16px;

    padding: 18px;

    margin-bottom: 14px;

}}

.icon {{

    font-size: 30px;

}}

.event-content {{

    min-width: 0;

}}

h2 {{

    font-size: 19px;

    margin:
        0
        0
        5px;

}}

.location {{

    color: #cbd5e1;

}}

.date {{

    color: #60a5fa;

    margin-top: 5px;

}}

p {{

    color: #cbd5e1;

    line-height: 1.45;

}}

a {{

    color: #60a5fa;

}}

.empty {{

    text-align: center;

    padding: 50px;

    color: #9ca3af;

}}

</style>

</head>

<body>

<div class="container">

<h1>
    🎵 Flathead Live
</h1>

<div class="subtitle">
    Music · concerts · film · festivals
</div>

<div class="filters">

<a href="/">
    All
</a>

<a href="/?category=music">
    🎵 Music
</a>

<a href="/?category=film">
    🎬 Film
</a>

<a href="/?category=festival">
    🎪 Festivals
</a>

</div>

{event_html}

</div>

</body>

</html>
"""


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "online",
        "app": "Flathead Live",
        "time": datetime.now(
            timezone.utc
        ).isoformat()
    }


# ============================================================
# STARTUP
# ============================================================

initialize_database()
