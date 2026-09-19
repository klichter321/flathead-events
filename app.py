import sqlite3
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse


app = FastAPI(title="Flathead Live")

DATABASE = "events.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            venue TEXT,
            city TEXT NOT NULL,
            category TEXT NOT NULL,
            event_date TEXT,
            event_time TEXT,
            description TEXT,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(title, city, event_date, event_time)
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# EVENT CLASSIFICATION
# ============================================================

def classify(title, text):
    combined = f"{title} {text}".lower()

    film_terms = [
        "film festival",
        "filmfest",
        "film screening",
        "film tour",
        "movie festival",
        "mountain film",
        "adventure film",
        "cinema",
    ]

    music_terms = [
        "live music",
        "concert",
        "music",
        "musician",
        "songwriter",
        "songwriters",
        "bluegrass",
        "jazz",
        "acoustic",
        "band",
        "dj",
        "symphony",
        "piano",
    ]

    festival_terms = [
        "festival",
        "fest",
        "fair",
        "rodeo",
        "celebration",
    ]

    if any(term in combined for term in film_terms):
        return "film"

    if any(term in combined for term in music_terms):
        return "music"

    if any(term in combined for term in festival_terms):
        return "festival"

    return "other"


# ============================================================
# TEXT HELPERS
# ============================================================

def clean(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def extract_date(text):
    patterns = [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,\s*\d{4})?",
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


def extract_time(text):
    pattern = (
        r"\b\d{1,2}(?::\d{2})?\s*"
        r"(?:AM|PM)\b"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(0)

    return ""


# ============================================================
# SAVE EVENT
# ============================================================

def save_event(
    title,
    venue,
    city,
    category,
    event_date,
    event_time,
    description,
    source,
    source_url,
):
    title = clean(title)

    if len(title) < 3:
        return

    conn = db()

    conn.execute("""
        INSERT OR IGNORE INTO events (
            title,
            venue,
            city,
            category,
            event_date,
            event_time,
            description,
            source,
            source_url,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title,
        clean(venue),
        clean(city),
        category,
        clean(event_date),
        clean(event_time),
        clean(description),
        source,
        source_url,
        datetime.now(timezone.utc).isoformat(),
    ))

    conn.commit()
    conn.close()


# ============================================================
# EXPLORE WHITEFISH
# ============================================================

def scrape_explore_whitefish():
    url = "https://explorewhitefish.com/events?face=list"

    print("Checking Explore Whitefish...")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()

    except Exception as error:
        print("Explore Whitefish error:", error)
        return 0

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    count = 0

    for link in soup.find_all("a", href=True):
        title = clean(
            link.get_text(
                " ",
                strip=True
            )
        )

        href = link.get("href", "")

        if not title or not href:
            continue

        event_url = urljoin(
            url,
            href
        )

        parent = link.parent

        if parent:
            context = clean(
                parent.get_text(
                    " ",
                    strip=True
                )
            )
        else:
            context = title

        if len(context) < len(title) + 10:
            if parent and parent.parent:
                context = clean(
                    parent.parent.get_text(
                        " ",
                        strip=True
                    )
                )

        category = classify(
            title,
            context
        )

        if category == "other":
            continue

        event_date = extract_date(context)
        event_time = extract_time(context)

        if not event_date:
            continue

        save_event(
            title=title,
            venue="",
            city="Whitefish",
            category=category,
            event_date=event_date,
            event_time=event_time,
            description=context,
            source="Explore Whitefish",
            source_url=event_url,
        )

        count += 1

    print(
        "Explore Whitefish events processed:",
        count
    )

    return count


# ============================================================
# WHITEFISH CHAMBER MUSIC
# ============================================================

def scrape_whitefish_music():
    url = "https://business.whitefishchamber.org/events"

    print("Checking Whitefish Chamber music...")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()

    except Exception as error:
        print(
            "Whitefish Chamber error:",
            error
        )
        return 0

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    count = 0

    for link in soup.find_all("a", href=True):
        title = clean(
            link.get_text(
                " ",
                strip=True
            )
        )

        href = link.get("href", "")

        if not title:
            continue

        if "/events/details/" not in href:
            continue

        event_url = urljoin(
            url,
            href
        )

        container = link

        for _ in range(5):
            if not container.parent:
                break

            container = container.parent

            context = clean(
                container.get_text(
                    " ",
                    strip=True
                )
            )

            if len(context) > len(title) + 20:
                break

        category = classify(
            title,
            context
        )

        if category != "music":
            continue

        event_date = extract_date(context)
        event_time = extract_time(context)

        if not event_date:
            continue

        venue = ""

        venue_names = [
            "Thirty Eight",
            "The Boat Club",
            "Tupelo",
            "Firebrand",
            "Great Northern",
            "Craggy Range",
            "Sacred Waters",
            "O'Shaughnessy's",
        ]

        for possible_venue in venue_names:
            if possible_venue.lower() in context.lower():
                venue = possible_venue
                break

        save_event(
            title=title,
            venue=venue,
            city="Whitefish",
            category="music",
            event_date=event_date,
            event_time=event_time,
            description=context,
            source="Whitefish Chamber",
            source_url=event_url,
        )

        count += 1

        print(
            "MUSIC:",
            title,
            "|",
            event_date,
            "|",
            event_time,
            "|",
            venue
        )

    print(
        "Whitefish Chamber music processed:",
        count
    )

    return count


# ============================================================
# MAJESTIC VALLEY ARENA
# ============================================================

def scrape_majestic():
    url = (
        "https://majesticvalleyarena.com/"
        "venue/majestic-valley-arena/"
    )

    print("Checking Majestic Valley Arena...")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()

    except Exception as error:
        print(
            "Majestic Valley Arena error:",
            error
        )
        return 0

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    count = 0

    containers = soup.select(
        "article, "
        ".tribe-events-calendar-list__event-row"
    )

    for container in containers:

        title_element = container.select_one(
            ".tribe-events-calendar-list__event-title a, "
            "h2 a, "
            "h3 a, "
            "h2, "
            "h3"
        )

        if not title_element:
            continue

        title = clean(
            title_element.get_text(
                " ",
                strip=True
            )
        )

        if not title:
            continue

        if title_element.name == "a":
            event_url = urljoin(
                url,
                title_element.get(
                    "href",
                    ""
                )
            )
        else:
            anchor = container.select_one(
                "a[href]"
            )

            if anchor:
                event_url = urljoin(
                    url,
                    anchor.get("href")
                )
            else:
                event_url = url

        context = clean(
            container.get_text(
                " ",
                strip=True
            )
        )

        category = classify(
            title,
            context
        )

        event_date = extract_date(context)
        event_time = extract_time(context)

        if not event_date:
            continue

        save_event(
            title=title,
            venue="Majestic Valley Arena",
            city="Kalispell",
            category=category,
            event_date=event_date,
            event_time=event_time,
            description=context,
            source="Majestic Valley Arena",
            source_url=event_url,
        )

        count += 1

    print(
        "Majestic events processed:",
        count
    )

    return count
# ============================================================
# FLATHEAD EVENTS.NET
# ============================================================

def scrape_flathead_events():

    url = "https://www.flatheadevents.net/"

    print("Checking FlatheadEvents.net...")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

    except Exception as error:

        print(
            "FlatheadEvents.net error:",
            error
        )

        return 0

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    count = 0

    # FlatheadEvents has event links and displays
    # the date, time, venue, and category around
    # each listing.
    for link in soup.find_all("a", href=True):

        title = clean(
            link.get_text(
                " ",
                strip=True
            )
        )

        href = link.get("href", "")

        if not title:
            continue

        # We want actual event "VIEW" links.
        if title.upper() != "VIEW":
            continue

        event_url = urljoin(
            url,
            href
        )

        # Walk upward to find the event listing.
        container = link

        context = ""

        for _ in range(6):

            if not container.parent:
                break

            container = container.parent

            context = clean(
                container.get_text(
                    " ",
                    strip=True
                )
            )

            # A real event block should contain
            # more information than just VIEW.
            if len(context) > 50:
                break

        if not context:
            continue

        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

        category = classify(
            "",
            context
        )

        if category == "other":
            continue

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        date_patterns = [
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{1,2}(?:,\s*\d{4})?",

            r"\b(?:January|February|March|April|May|June|July|"
            r"August|September|October|November|December)"
            r"\s+\d{1,2}(?:,\s*\d{4})?",
        ]

        event_date = ""

        for pattern in date_patterns:

            match = re.search(
                pattern,
                context,
                re.IGNORECASE
            )

            if match:

                event_date = match.group(0)

                break

        if not event_date:
            continue

        # ----------------------------------------------------
        # TIME
        # ----------------------------------------------------

        time_match = re.search(
            r"\b\d{1,2}(?::\d{2})?\s*(?:AM|PM)\b",
            context,
            re.IGNORECASE
        )

        event_time = ""

        if time_match:
            event_time = time_match.group(0)

        # ----------------------------------------------------
        # VENUES
        # ----------------------------------------------------

        venue_names = [
            "Majestic Valley Arena",
            "Wachholz College Center",
            "Thirty Eight Central",
            "The Boat Club",
            "The Lodge at Whitefish Lake",
            "Great Northern Bar",
            "The Raven",
            "The Firebrand Hotel & Restaurant",
            "Firebrand",
            "Abayance Bay Marina",
            "River View Bar",
            "Water's Edge Winery and Bistro",
            "Patriotic American Brewery",
            "Flathead County Fairgrounds",
            "Rebecca Farm",
            "Blue Moon Arena",
        ]

        venue = ""

        for possible_venue in venue_names:

            if possible_venue.lower() in context.lower():

                venue = possible_venue

                break

        # ----------------------------------------------------
        # FIND EVENT TITLE
        # ----------------------------------------------------

        title = ""

        # Look for headings inside the event block.
        title_element = container.select_one(
            "h1, h2, h3, h4, h5, "
            ".event-title, "
            "[class*='title']"
        )

        if title_element:

            title = clean(
                title_element.get_text(
                    " ",
                    strip=True
                )
            )

        # If no heading was found, try links other than
        # the VIEW link.
        if not title:

            for other_link in container.find_all(
                "a",
                href=True
            ):

                possible_title = clean(
                    other_link.get_text(
                        " ",
                        strip=True
                    )
                )

                if (
                    possible_title
                    and possible_title.upper() != "VIEW"
                    and len(possible_title) >= 5
                ):

                    title = possible_title

                    break

        if not title:
            continue

        # Don't accidentally save navigation links.
        bad_titles = [
            "home",
            "music",
            "art",
            "sports",
            "food",
            "education",
            "government",
            "business",
            "special events",
            "search events",
            "submit an event",
        ]

        if title.lower() in bad_titles:
            continue

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        save_event(
            title=title,
            venue=venue,
            city="Flathead Valley",
            category=category,
            event_date=event_date,
            event_time=event_time,
            description=context,
            source="FlatheadEvents.net",
            source_url=event_url,
        )

        count += 1

        print(
            "FLATHEAD EVENTS:",
            title,
            "|",
            event_date,
            "|",
            event_time,
            "|",
            venue,
            "|",
            category
        )

    print(
        "FlatheadEvents.net events processed:",
        count
    )

    return count


# ============================================================
# REFRESH ALL EVENTS
# ============================================================

def refresh_events():
    print("")
    print("========================================")
    print("FLATHEAD LIVE REFRESH")
    print("========================================")

    conn = db()

    conn.execute("DELETE FROM events")

    conn.commit()
    conn.close()

    total = 0

    total += scrape_explore_whitefish()

    total += scrape_whitefish_music()

    total += scrape_majestic()

    print("")
    print(
        "TOTAL EVENTS:",
        total
    )

    return total


# ============================================================
# REFRESH ENDPOINT
# ============================================================

@app.get("/refresh")
def refresh():
    total = refresh_events()

    return {
        "status": "success",
        "events_processed": total
    }


# ============================================================
# HOME PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def home(
    category: str = Query("all")
):
    conn = db()

    if category == "all":
        rows = conn.execute("""
            SELECT *
            FROM events
            ORDER BY
                event_date,
                event_time,
                title
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT *
            FROM events
            WHERE category = ?
            ORDER BY
                event_date,
                event_time,
                title
        """, (
            category,
        )).fetchall()

    conn.close()

    cards = []

    for event in rows:

        if event["category"] == "music":
            icon = "🎵"
        elif event["category"] == "film":
            icon = "🎬"
        elif event["category"] == "festival":
            icon = "🎪"
        else:
            icon = "📍"

        date_text = event["event_date"]

        if event["event_time"]:
            date_text += (
                " · " +
                event["event_time"]
            )

        venue = event["venue"]

        if not venue:
            venue = event["city"]

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
                    {venue}
                </div>

                <div class="date">
                    {date_text}
                </div>

                <p>
                    {event["description"][:300]}
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
            <div style="font-size:42px">
                🔎
            </div>

            <h2>
                No events found yet
            </h2>

            <p>
                Open /refresh to collect events.
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
    max-width: 760px;
    margin: auto;
    padding: 25px 18px 60px;
}}

h1 {{
    font-size: 38px;
    margin: 0;
}}

.subtitle {{
    color: #94a3b8;
    margin: 4px 0 22px;
}}

.filters {{
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 18px;
}}

.filters a {{
    background: #263449;
    color: white;
    text-decoration: none;
    padding: 9px 15px;
    border-radius: 999px;
    white-space: nowrap;
}}

.event {{
    display: flex;
    gap: 16px;
    background: #1c2838;
    border: 1px solid #2c3b4f;
    border-radius: 17px;
    padding: 18px;
    margin-bottom: 14px;
}}

.icon {{
    font-size: 30px;
}}

.content {{
    min-width: 0;
}}

h2 {{
    font-size: 19px;
    margin: 0 0 6px;
}}

.location {{
    color: #cbd5e1;
}}

.date {{
    color: #60a5fa;
    font-weight: 600;
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
    padding: 60px 20px;
    color: #94a3b8;
}}

</style>

</head>

<body>

<div class="container">

<h1>
🎵 Flathead Live
</h1>

<div class="subtitle">
Whitefish · Kalispell · Flathead Valley
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
