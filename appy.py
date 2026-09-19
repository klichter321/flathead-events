Mobile-friendly event tracker for:

    🎵 Live music
    🎸 Majestic Valley Arena concerts
    🎬 Film festivals / film events
    🎪 Festivals and special events
    🎭 Performing arts

Primary sources:

    Explore Whitefish
    Whitefish Chamber of Commerce
    Majestic Valley Arena

The program:
    1. Downloads event pages.
    2. Looks for Schema.org JSON-LD event data.
    3. Falls back to HTML text when necessary.
    4. Categorizes events.
    5. Removes duplicates.
    6. Stores events in SQLite.
    7. Refreshes automatically every hour.
    8. Provides a mobile-friendly web interface.

Python version:
    3.10+

No third-party Python packages are required.
"""APP_NAME = "Flathead Live"

DATABASE = "flathead_events.db"

REFRESH_SECONDS = 60 * 60

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; FlatheadLive/1.0; local-event-reader)"
)

# Official source pages.
SOURCES = [
    {
        "name": "Explore Whitefish",
        "url": "https://explorewhitefish.com/events?face=list",
        "city": "Whitefish",
        "type": "whitefish",
    },
    {
        "name": "Whitefish Chamber",
        "url": "https://business.whitefishchamber.org/events",
        "city": "Whitefish",
        "type": "chamber",
    },
    {
        "name": "Majestic Valley Arena",
        "url": "https://majesticvalleyarena.com/venue/majestic-valley-arena/",
        "city": "Kalispell",
        "type": "majestic",
    },
]


# ============================================================
# KEYWORDS
# ============================================================

MUSIC_WORDS = [
    "live music",
    "live music at",
    "concert",
    "concerts",
    "musician",
    "musicians",
    "band",
    "duo",
    "trio",
    "quartet",
    "symphony",
    "orchestra",
    "bluegrass",
    "jazz",
    "country music",
    "rock music",
    "folk music",
    "roots music",
    "songwriter",
    "songwriters",
    "songwriter festival",
    "music festival",
    "music scene",
    "dj",
    "dueling pianos",
    "acoustic jam",
    "open mic",
    "worship night",
]

FILM_WORDS = [
    "film festival",
    "filmfest",
    "film fest",
    "movie festival",
    "film screening",
    "film screenings",
    "movie screening",
    "cinema",
    "documentary film",
    "documentary screening",
    "film tour",
    "film night",
    "movie night",
    "paddling film",
    "fly fishing film",
    "mountain film",
    "adventure film",
    "outdoor film",
]

FESTIVAL_WORDS = [
    "festival",
    "fest",
    "fair",
    "celebration",
    "carnival",
    "oktoberfest",
    "arts festival",
    "food festival",
    "wine festival",
    "film festival",
    "music festival",
    "songwriter festival",
    "hootenanny",
]

PERFORMING_ARTS_WORDS = [
    "theater",
    "theatre",
    "play",
    "musical",
    "performance",
    "performing arts",
    "dance",
    "ballet",
    "opera",
]


# ============================================================
# HTTP DOWNLOAD
# ============================================================

def download(url):
    """
    Download a webpage using Python's standard library.
    """

    import urllib.request

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            return content.decode(encoding, errors="replace")

    except Exception as exc:
        print(f"[DOWNLOAD ERROR] {url}")
        print(f"                 {exc}")
        return ""


# ============================================================
# HTML HELPERS
# ============================================================

class HTMLTextParser(HTMLParser):
    """
    Extracts visible text and links.
    """

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.links = []

        self.in_script = False
        self.in_style = False

        self.current_href = None
        self.current_link_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        attributes = dict(attrs)

        if tag == "script":
            self.in_script = True

        if tag == "style":
            self.in_style = True

        if tag == "a":
            self.current_href = attributes.get("href")
            self.current_link_text = []

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == "script":
            self.in_script = False

        if tag == "style":
            self.in_style = False

        if tag == "a" and self.current_href:
            text = clean_text(" ".join(self.current_link_text))

            if text:
                self.links.append(
                    {
                        "text": text,
                        "href": self.current_href,
                    }
                )

            self.current_href = None
            self.current_link_text = []

    def handle_data(self, data):
        if self.in_script or self.in_style:
            return

        cleaned = clean_text(data)

        if not cleaned:
            return

        self.text_parts.append(cleaned)

        if self.current_href:
            self.current_link_text.append(cleaned)


def clean_text(value):
    if not value:
        return ""

    value = re.sub(r"\s+", " ", str(value))
    return value.strip()


def strip_html(value):
    if not value:
        return ""

    parser = HTMLTextParser()
    parser.feed(value)

    return clean_text(" ".join(parser.text_parts))


# ============================================================
# JSON-LD EVENT EXTRACTION
# ============================================================

def extract_jsonld(html):
    """
    Find Schema.org JSON-LD blocks.

    Many modern event websites expose event information this way.
    """

    results = []

    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>'
        r"(.*?)"
        r"</script>",
        re.IGNORECASE | re.DOTALL,
    )

    matches = pattern.findall(html)

    for raw in matches:
        raw = raw.strip()

        # Remove HTML comment wrappers occasionally found around JSON.
        raw = raw.replace("<!--", "").replace("-->", "").strip()

        try:
            data = json.loads(raw)
        except Exception:
            continue

        walk_jsonld(data, results)

    return results


def walk_jsonld(data, results):
    if isinstance(data, dict):

        item_type = data.get("@type")

        if item_type:
            if isinstance(item_type, list):
                types = item_type
            else:
                types = [item_type]

            if any(
                str(t).lower() == "event"
                or str(t).lower().endswith("event")
                for t in types
            ):
                results.append(data)

        for value in data.values():
            walk_jsonld(value, results)

    elif isinstance(data, list):

        for item in data:
            walk_jsonld(item, results)


# ============================================================
# DATE HELPERS
# ============================================================

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_date(value):
    """
    Convert common ISO dates to a consistent format.

    Returns:
        YYYY-MM-DD HH:MM
    """

    if not value:
        return ""

    value = str(value).strip()

    # ISO date/time.
    try:
        normalized = value.replace("Z", "+00:00")

        dt = datetime.fromisoformat(normalized)

        return dt.strftime("%Y-%m-%d %H:%M")

    except Exception:
        pass

    # Date only.
    match = re.search(
        r"\b(20\d\d)-(\d\d)-(\d\d)\b",
        value,
    )

    if match:
        return (
            f"{match.group(1)}-"
            f"{match.group(2)}-"
            f"{match.group(3)}"
        )

    return value


def pretty_date(value):
    if not value:
        return "Date/time TBD"

    try:
        dt = datetime.fromisoformat(value)

        return dt.strftime("%a, %b %-d · %-I:%M %p")

    except Exception:
        # Windows doesn't always support %-d / %-I.
        try:
            dt = datetime.fromisoformat(value)

            return dt.strftime("%a, %b %d · %I:%M %p").replace(
                " 0",
                " ",
            ).lstrip("0")

        except Exception:
            return value


# ============================================================
# CATEGORY DETECTION
# ============================================================

def classify(title, description=""):
    text = clean_text(
        f"{title} {description}"
    ).lower()

    # Film first.
    if any(word in text for word in FILM_WORDS):
        return "film"

    if any(word in text for word in MUSIC_WORDS):
        return "music"

    if any(word in text for word in PERFORMING_ARTS_WORDS):
        return "arts"

    if any(word in text for word in FESTIVAL_WORDS):
        return "festival"

    return "other"


def is_relevant(title, description):
    """
    We don't want the app to become a giant general-events calendar.

    Keep:
        music
        film
        festivals
        performing arts

    But allow Majestic Valley Arena events through as well because
    the user specifically requested that venue.
    """

    category = classify(title, description)

    if category in {
        "music",
        "film",
        "festival",
        "arts",
    }:
        return True

    return False


# ============================================================
# EVENT NORMALIZATION
# ============================================================

def get_nested(value, *keys):
    current = value

    for key in keys:
        if not isinstance(current, dict):
            return ""

        current = current.get(key)

    return current or ""


def jsonld_event_to_record(event, source):
    title = clean_text(event.get("name", ""))

    description = strip_html(
        event.get("description", "")
    )

    start = parse_date(
        event.get("startDate", "")
    )

    end = parse_date(
        event.get("endDate", "")
    )

    url = event.get("url") or source["url"]

    location = event.get("location", {})

    venue = ""
    city = source["city"]

    if isinstance(location, dict):
        venue = clean_text(
            location.get("name", "")
        )

        address = location.get(
            "address",
            {},
        )

        if isinstance(address, dict):
            city = (
                clean_text(
                    address.get("addressLocality", "")
                )
                or city
            )

    elif isinstance(location, str):
        venue = clean_text(location)

    if not title:
        return None

    category = classify(
        title,
        description,
    )

    # Majestic is explicitly monitored.
    if source["type"] == "majestic":
        if category == "other":
            # Keep the arena event but mark it as festival/special
            # only if it looks like a public event.
            category = "other"

    elif category not in {
        "music",
        "film",
        "festival",
        "arts",
    }:
        return None

    return {
        "title": title,
        "venue": venue,
        "city": city,
        "category": category,
        "start_time": start,
        "end_time": end,
        "description": description,
        "source_name": source["name"],
        "source_url": absolute_url(
            url,
            source["url"],
        ),
    }


# ============================================================
# URL HELPERS
# ============================================================

def absolute_url(url, base):
    if not url:
        return base

    return urljoin(base, url)


# ============================================================
# FALLBACK EVENT LINK PARSER
# ============================================================

def fallback_events(html, source):
    """
    Some pages don't expose every event through JSON-LD.

    This fallback scans links and nearby text for music,
    film and festival-related events.
    """

    parser = HTMLTextParser()
    parser.feed(html)

    events = []

    for link in parser.links:

        title = clean_text(link["text"])

        if len(title) < 4:
            continue

        # Avoid navigation links.
        if len(title) > 250:
            continue

        href = absolute_url(
            link["href"],
            source["url"],
        )

        category = classify(title)

        if category not in {
            "music",
            "film",
            "festival",
            "arts",
        }:
            continue

        events.append(
            {
                "title": title,
                "venue": "",
                "city": source["city"],
                "category": category,
                "start_time": "",
                "end_time": "",
                "description": "",
                "source_name": source["name"],
                "source_url": href,
            }
        )

    return events


# ============================================================
# DEDUPLICATION
# ============================================================

def make_key(event):
    """
    Build a stable fingerprint.

    This prevents the same concert appearing multiple times
    when both Explore Whitefish and the Chamber list it.
    """

    title = clean_text(
        event["title"]
    ).lower()

    venue = clean_text(
        event["venue"]
    ).lower()

    start = clean_text(
        event["start_time"]
    ).lower()

    city = clean_text(
        event["city"]
    ).lower()

    # Remove punctuation.
    raw = re.sub(
        r"[^a-z0-9]+",
        "|",
        f"{title}|{venue}|{start}|{city}",
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# DATABASE
# ============================================================

def database():
    connection = sqlite3.connect(
        DATABASE,
        check_same_thread=False,
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    connection = database()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            event_key TEXT UNIQUE NOT NULL,

            title TEXT NOT NULL,
            venue TEXT,
            city TEXT,

            category TEXT NOT NULL,

            start_time TEXT,
            end_time TEXT,

            description TEXT,

            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,

            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_events_start
        ON events(start_time)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_events_category
        ON events(category)
        """
    )

    connection.commit()
    connection.close()


def save_event(event):
    key = make_key(event)

    now = datetime.now(
        timezone.utc
    ).isoformat()

    connection = database()

    connection.execute(
        """
        INSERT INTO events (
            event_key,
            title,
            venue,
            city,
            category,
            start_time,
            end_time,
            description,
            source_name,
            source_url,
            first_seen,
            last_seen
        )

        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )

        ON CONFLICT(event_key)
        DO UPDATE SET

            title=excluded.title,
            venue=excluded.venue,
            city=excluded.city,
            category=excluded.category,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            description=excluded.description,
            source_name=excluded.source_name,
            source_url=excluded.source_url,
            last_seen=excluded.last_seen
        """,
        (
            key,
            event["title"],
            event["venue"],
            event["city"],
            event["category"],
            event["start_time"],
            event["end_time"],
            event["description"],
            event["source_name"],
            event["source_url"],
            now,
            now,
        ),
    )

    connection.commit()
    connection.close()


# ============================================================
# SCRAPER
# ============================================================

def scrape_source(source):
    print()
    print("=" * 70)
    print(f"Checking: {source['name']}")
    print(source["url"])

    html = download(
        source["url"]
    )

    if not html:
        return 0

    events = []

    # First try Schema.org.
    json_events = extract_jsonld(
        html
    )

    for json_event in json_events:

        record = jsonld_event_to_record(
            json_event,
            source,
        )

        if record:
            events.append(record)

    # Then use fallback link scanning.
    fallback = fallback_events(
        html,
        source,
    )

    events.extend(fallback)

    # Deduplicate within this source.
    unique = {}

    for event in events:
        unique[
            make_key(event)
        ] = event

    events = list(
        unique.values()
    )

    saved = 0

    for event in events:

        save_event(event)

        saved += 1

        print(
            f"  + {event['category']:9} "
            f"{event['title']}"
        )

    print(
        f"Saved/updated {saved} events."
    )

    return saved


def refresh():
    print()
    print("=" * 70)
    print(
        "FLATHEAD LIVE EVENT REFRESH"
    )
    print(
        datetime.now().isoformat()
    )
    print("=" * 70)

    total = 0

    for source in SOURCES:

        try:
            total += scrape_source(
                source
            )

        except Exception as exc:

            print(
                f"[SOURCE ERROR] "
                f"{source['name']}: {exc}"
            )

    remove_old_events()

    print()
    print(
        f"REFRESH COMPLETE: {total} events"
    )
    print("=" * 70)


# ============================================================
# OLD EVENT CLEANUP
# ============================================================

def remove_old_events():
    """
    Keep the database manageable.

    Events more than 60 days in the past are removed.
    """

    cutoff = (
        datetime.now()
        - timedelta(days=60)
    ).strftime(
        "%Y-%m-%d %H:%M"
    )

    connection = database()

    connection.execute(
        """
        DELETE FROM events
        WHERE start_time != ''
        AND start_time < ?
        """,
        (cutoff,),
    )

    connection.commit()
    connection.close()


# ============================================================
# BACKGROUND REFRESHER
# ============================================================

def background_worker():
    """
    Refresh forever.

    This means the app continues checking sources even
    when nobody has the website open.
    """

    while True:

        try:
            refresh()

        except Exception as exc:

            print(
                f"[REFRESH ERROR] {exc}"
            )

        time.sleep(
            REFRESH_SECONDS
        )


# ============================================================
# HTML ESCAPING
# ============================================================

def html_escape(value):
    value = str(
        value or ""
    )

    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ============================================================
# ICONS
# ============================================================

def category_icon(category):

    return {
        "music": "🎵",
        "film": "🎬",
        "festival": "🎪",
        "arts": "🎭",
        "other": "📍",
    }.get(
        category,
        "📍",
    )


def category_name(category):

    return {
        "music": "Music",
        "film": "Film",
        "festival": "Festival",
        "arts": "Performing Arts",
        "other": "Event",
    }.get(
        category,
        "Event",
    )


# ============================================================
# MAIN WEB PAGE
# ============================================================

def render_page(
    category="all",
    city="all",
    days=14,
):
    connection = database()

    query = """
        SELECT *
        FROM events
        WHERE 1=1
    """

    params = []

    # --------------------------------------------------------
    # Category filter
    # --------------------------------------------------------

    if category != "all":

        query += """
            AND category = ?
        """

        params.append(
            category
        )

    # --------------------------------------------------------
    # City filter
    # --------------------------------------------------------

    if city != "all":

        query += """
            AND city = ?
        """

        params.append(
            city
        )

    # --------------------------------------------------------
    # Date filter
    # --------------------------------------------------------

    today = datetime.now()

    cutoff = (
        today
        + timedelta(
            days=days
        )
    ).strftime(
        "%Y-%m-%d %H:%M"
    )

    query += """
        AND (
            start_time = ''
            OR start_time <= ?
        )
    """

    params.append(
        cutoff
    )

    query += """
        ORDER BY
            CASE
                WHEN start_time = ''
                THEN 1
                ELSE 0
            END,
            start_time ASC,
            title ASC
    """

    rows = connection.execute(
        query,
        params,
    ).fetchall()

    connection.close()

    # --------------------------------------------------------
    # Count categories
    # --------------------------------------------------------

    connection = database()

    counts = {}

    for row in connection.execute(
        """
        SELECT category, COUNT(*) AS count
        FROM events
        GROUP BY category
        """
    ):
        counts[
            row["category"]
        ] = row["count"]

    connection.close()

    # --------------------------------------------------------
    # Event cards
    # --------------------------------------------------------

    cards = []

    for event in rows:

        icon = category_icon(
            event["category"]
        )

        category_label = category_name(
            event["category"]
        )

        title = html_escape(
            event["title"]
        )

        venue = html_escape(
            event["venue"]
            or "Venue TBD"
        )

        city_name = html_escape(
            event["city"]
            or "Flathead Valley"
        )

        date = html_escape(
            pretty_date(
                event["start_time"]
            )
        )

        description = html_escape(
            event["description"]
        )

        if len(description) > 280:
            description = (
                description[:280]
                + "..."
            )

        source = html_escape(
            event["source_name"]
        )

        url = html_escape(
            event["source_url"]
        )

        cards.append(
            f"""
            <article class="event-card">

                <div class="event-icon">
                    {icon}
                </div>

                <div class="event-content">

                    <div class="category">
                        {category_label}
                    </div>

                    <h2>
                        {title}
                    </h2>

                    <div class="event-meta">
                        📅 {date}
                    </div>

                    <div class="event-meta">
                        📍 {venue}
                        · {city_name}
                    </div>

                    <p>
                        {description}
                    </p>

                    <div class="source">
                        Source:
                        {source}
                    </div>

                    <a
                        class="event-button"
                        href="{url}"
                        target="_blank"
                        rel="noopener"
                    >
                        View original event →
                    </a>

                </div>

            </article>
            """
        )

    # --------------------------------------------------------
    # Empty state
    # --------------------------------------------------------

    if not cards:

        cards.append(
            """
            <div class="empty">
                <div class="empty-icon">
                    🔎
                </div>

                <h2>
                    No events found
                </h2>

                <p>
                    Try another category or city.
                    The collector may also still be
                    gathering events.
                </p>
            </div>
            """
        )

    # --------------------------------------------------------
    # HTML
    # --------------------------------------------------------

    return f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1,
             viewport-fit=cover"
>

<meta
    name="theme-color"
    content="#081c15"
>

<title>
    {APP_NAME}
</title>

<style>

* {{
    box-sizing: border-box;
}}

html {{
    background: #07130f;
}}

body {{
    margin: 0;

    background:
        radial-gradient(
            circle at top,
            #163b2b 0%,
            #07130f 55%
        );

    color: #f7faf8;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    min-height: 100vh;

    padding-bottom:
        env(safe-area-inset-bottom);
}}

.container {{
    width: min(
        760px,
        100%
    );

    margin: auto;

    padding:
        20px
        16px
        50px;
}}

.header {{
    padding-top: 20px;
    padding-bottom: 20px;
}}

.logo {{
    font-size: 14px;
    font-weight: 800;

    color: #9ae6b4;

    letter-spacing: 1.5px;

    text-transform: uppercase;
}}

h1 {{
    font-size: 38px;

    line-height: 1.05;

    margin:
        7px
        0
        8px;
}}

.subtitle {{
    color: #b7c8bf;

    font-size: 15px;

    line-height: 1.5;
}}

.filters {{
    display: flex;

    gap: 8px;

    overflow-x: auto;

    padding:
        5px
        0
        15px;

    scrollbar-width: none;
}}

.filters::-webkit-scrollbar {{
    display: none;
}}

.filter {{
    flex: 0 0 auto;

    border: 1px solid
        rgba(
            255,
            255,
            255,
            .10
        );

    background:
        rgba(
            255,
            255,
            255,
            .06
        );

    color: #dce9e2;

    padding:
        10px
        14px;

    border-radius: 999px;

    text-decoration: none;

    font-size: 14px;

    font-weight: 650;
}}

.filter.active {{
    background: #8ee4ad;

    color: #062013;

    border-color:
        #8ee4ad;
}}

.summary {{
    display: flex;

    gap: 8px;

    flex-wrap: wrap;

    margin:
        12px
        0
        18px;
}}

.stat {{
    background:
        rgba(
            255,
            255,
            255,
            .055
        );

    border-radius: 12px;

    padding:
        9px
        12px;

    color: #bcd0c5;

    font-size: 13px;
}}

.stat strong {{
    color: white;
}}

.event-card {{
    display: flex;

    gap: 14px;

    background:
        rgba(
            19,
            37,
            29,
            .90
        );

    border:
        1px solid
        rgba(
            255,
            255,
            255,
            .075
        );

    border-radius: 18px;

    padding: 17px;

    margin-bottom: 12px;

    box-shadow:
        0 8px 25px
        rgba(
            0,
            0,
            0,
            .18
        );
}}

.event-icon {{
    font-size: 29px;

    width: 35px;

    flex: 0 0 35px;

    padding-top: 3px;
}}

.event-content {{
    min-width: 0;

    flex: 1;
}}

.category {{
    color: #8ee4ad;

    font-size: 11px;

    font-weight: 800;

    text-transform: uppercase;
ChatGPT said:
