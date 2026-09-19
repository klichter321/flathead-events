import re
import sqlite3
from datetime import datetime, timedelta, timezone
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 "
        "Chrome/140.0 Safari/537.36"
    )
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
# CLASSIFICATION
# ============================================================

MUSIC_TERMS = [
    "live music",
    "live music at",
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
    "dj",
    "acoustic",
    "band",
    "worship",
    "country music",
]

FILM_TERMS = [
    "film festival",
    "filmfest",
    "film screening",
    "movie festival",
    "film tour",
    "documentary",
    "cinema",
    "paddling film",
    "fly fishing film",
    "mountain film",
    "adventure film",
]

FESTIVAL_TERMS = [
    "festival",
    "fest",
    "fair",
    "celebration",
    "rodeo",
]


def classify_event(title, description=""):

    text = f"{title} {description}".lower()

    if any(term in text for term in FILM_TERMS):
        return "film"

    if any(term in text for term in MUSIC_TERMS):
        return "music"

    if any(term in text for term in FESTIVAL_TERMS):
        return "festival"

    return "other"


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):

    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def is_probably_event_title(title):

    if not title:
        return False

    title = title.strip()

    if len(title) < 4:
        return False

    if len(title) > 180:
        return False

    bad_words = [
        "login",
        "sign in",
        "register",
        "contact us",
        "privacy policy",
        "terms of use",
        "learn more",
        "read more",
        "directions",
        "get directions",
    ]

    lower = title.lower()

    if any(word in lower for word in bad_words):
        return False

    return True


def extract_date(text):

    patterns = [

        # September 19, 2026
        r"\b(?:January|February|March|April|May|June|July|"
        r"August|September|October|November|December)"
        r"\s+\d{1,2}(?:,\s*\d{4})?",

        # Sep 19, 2026
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{1,2}(?:,\s*\d{4})?",

        # 9/19/2026
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(0)

    return ""


# ============================================================
# DATABASE SAVE
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

    title = clean_text(title)

    if not is_probably_event_title(title):
        return

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
        clean_text(venue),
        clean_text(city),
        category,
        clean_text(event_date),
        clean_text(description),
        source,
        source_url,
        datetime.now(timezone.utc).isoformat(),
    ))

    connection.commit()
    connection.close()


# ============================================================
# GENERIC LINK-BASED SCRAPER
# ============================================================

def scrape_links(
    source_name,
    url,
    city,
    default_venue="",
):

    print("")
    print("========================================")
    print(f"Checking: {source_name}")
    print(url)
    print("========================================")

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

    except Exception as error:

        print(
            f"ERROR downloading {source_name}: "
            f"{error}"
        )

        return 0

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    found = 0

    # Look at every link on the page.
    # This works better with the event-calendar
    # structures used by several local sites.
    for link in soup.find_all("a", href=True):

        title = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if not is_probably_event_title(title):
            continue

        href = link.get("href")

        if not href:
            continue

        event_url = urljoin(
            url,
            href
        )

        # Get text surrounding the link.
        parent = link.parent

        if parent:
            context = clean_text(
                parent.get_text(
                    " ",
                    strip=True
                )
            )
        else:
            context = title

        # Sometimes the event's date is in a nearby
        # parent element rather than in the link.
        if len(context) < len(title) + 10:

            grandparent = (
                parent.parent
                if parent
                else None
            )

            if grandparent:

                context = clean_text(
                    grandparent.get_text(
                        " ",
                        strip=True
                    )
                )

        event_date = extract_date(context)

        category = classify_event(
            title,
            context
        )

        # Only collect things we're interested in.
        if category == "other":
            continue

        save_event(
            title=title,
            venue=default_venue,
            city=city,
            category=category,
            event_date=event_date,
            description=context,
            source=source_name,
            source_url=event_url,
        )

        found += 1

    print(
        f"{source_name}: {found} events identified"
    )

    return found


# ============================================================
# WHITEFISH CHAMBER
# ============================================================

def scrape_whitefish_chamber():

    today = datetime.now().date()

    end_date = today + timedelta(days=120)

    url = (
        "https://business.whitefishchamber.org/events"
        f"?from={today.month}/{today.day}/{today.year}"
        f"&o=alpha"
        f"&to={end_date.month}/{end_date.day}/{end_date.year}"
    )

    return scrape_links(
        source_name="Whitefish Chamber",
        url=url,
        city="Whitefish",
    )


# ============================================================
# EXPLORE WHITEFISH
# ============================================================

def scrape_explore_whitefish():

    url = (
        "https://explorewhitefish.com/events"
        "?face=list"
    )

    return scrape_links(
        source_name="Explore Whitefish",
        url=url,
        city="Whitefish",
    )


# ============================================================
# MAJESTIC VALLEY ARENA
# ============================================================

def scrape_majestic():

    url = (
        "https://majesticvalleyarena.com/"
        "venue/majestic-valley-arena/"
    )

    return scrape_links(
        source_name="Majestic Valley Arena",
        url=url,
        city="Kalispell",
        default_venue="Majestic Valley Arena",
    )


# ============================================================
# REFRESH EVERYTHING
# ============================================================

def refresh_events():

    print("")
    print("########################################")
    print("# FLATHEAD LIVE EVENT REFRESH")
    print("########################################")

    total = 0

    total += scrape_whitefish_chamber()

    total += scrape_explore_whitefish()

    total += scrape_majestic()

    print("")
    print(
        f"REFRESH FINISHED: {total} event listings processed"
    )

    return total


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
            ORDER BY
                CASE
                    WHEN event_date = '' THEN 1
                    ELSE 0
                END,
                event_date,
                title
        """).fetchall()

    else:

        events = connection.execute("""
            SELECT *
            FROM events
            WHERE category = ?
            ORDER BY
                CASE
                    WHEN event_date = '' THEN 1
                    ELSE 0
                END,
                event_date,
                title
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

        venue_text = ""

        if event["venue"]:
            venue_text = (
                f" · {event['venue']}"
            )

        cards.append(f"""
        <div class="event">

            <div class="icon">
                {icon}
            </div>

            <div class="content">

                <h2>
                    {event["title"]}
                </h2>

                <div class="location">
                    {event["city"]}
                    {venue_text}
                </div>

                <div class="date">
                    {event["event_date"] or "Date TBD"}
                </div>

                <p>
                    {event["description"][:350]}
                </p>

                <a
                    href="{event["source_url"]}"
                    target="_blank"
                    rel="noopener"
                >
                    View original listing →
                </a>

            </div>

        </div>
        """)

    if cards:

        event_html = "".join(cards)

    else:

        event_html = """
        <div class="empty">

            <div style="font-size:40px">
                🔎
            </div>

            <h2>
                No events found yet
            </h2>

            <p>
                Try refreshing the event database.
            </p>

        </div>
        """

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<meta name="theme-color"
      content="#08111f">

<title>
    Flathead Live
</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{

    margin: 0;

    background:
        linear-gradient(
            180deg,
            #07111f 0%,
            #111827 100%
        );

    color: white;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    min-height: 100vh;
}}

.container {{

    max-width: 760px;

    margin: auto;

    padding:
        24px
        18px
        60px;

}}

h1 {{

    font-size: 38px;

    margin:
        0
        0
        5px;

}}

.subtitle {{

    color: #94a3b8;

    margin-bottom: 24px;

}}

.filters {{

    display: flex;

    gap: 8px;

    overflow-x: auto;

    padding-bottom: 18px;

}}

.filters a {{

    color: white;

    text-decoration: none;

    background: #263449;

    padding:
        9px
        15px;

    border-radius: 999px;

    white-space: nowrap;

}}

.event {{

    display: flex;

    gap: 16px;

    background: #1c2838;

    border:
        1px solid
        #29384c;

    border-radius: 17px;

    padding: 18px;

    margin-bottom: 14px;

    box-shadow:
        0 4px 15px
        rgba(0,0,0,.15);

}}

.icon {{

    font-size: 30px;

    min-width: 34px;

}}

.content {{

    min-width: 0;

}}

h2 {{

    font-size: 19px;

    line-height: 1.25;

    margin:
        0
        0
        6px;

}}

.location {{

    color: #cbd5e1;

}}

.date {{

    color: #60a5fa;

    margin-top: 5px;

    font-weight: 600;

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

    padding: 60px 20px;

    color: #94a3b8;

}}

.refresh {{

    display: inline-block;

    margin-top: 10px;

    padding:
        10px
        16px;

    border-radius: 10px;

    background: #2563eb;

    color: white;

    text-decoration: none;

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
# MANUAL REFRESH ENDPOINT
# ============================================================

@app.get("/refresh")
def manual_refresh():

    total = refresh_events()

    return {
        "status": "success",
        "events_processed": total,
        "message": "Event sources refreshed."
    }


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
        ).isoformat(),
    }


# ============================================================
# STARTUP
# ============================================================

initialize_database()

# Collect events when the server starts.
try:
    refresh_events()
except Exception as error:
    print(
        f"Initial event refresh failed: {error}"
    )
