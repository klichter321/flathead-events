from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from datetime import datetime

app = FastAPI(title="Flathead Live")

events = [
    {
        "title": "Live Music",
        "venue": "Whitefish",
        "category": "Music",
        "date": "Coming soon",
    },
    {
        "title": "Majestic Valley Arena Events",
        "venue": "Majestic Valley Arena",
        "category": "Music & Events",
        "date": "Coming soon",
    },
    {
        "title": "Film Festivals",
        "venue": "Flathead Valley",
        "category": "Film",
        "date": "Coming soon",
    },
]


@app.get("/", response_class=HTMLResponse)
def home():
    cards = ""

    for event in events:
        if event["category"] == "Music":
            icon = "🎵"
        elif event["category"] == "Film":
            icon = "🎬"
        else:
            icon = "🎪"

        cards += f"""
        <div class="event">
            <div class="icon">{icon}</div>
            <div>
                <h2>{event["title"]}</h2>
                <p>{event["venue"]}</p>
                <span>{event["date"]}</span>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Flathead Live</title>

        <style>
            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                padding: 20px;
                background: #101827;
                color: white;
                font-family: -apple-system, BlinkMacSystemFont,
                             "Segoe UI", sans-serif;
            }}

            .container {{
                max-width: 700px;
                margin: auto;
            }}

            h1 {{
                font-size: 34px;
                margin-bottom: 5px;
            }}

            .subtitle {{
                color: #9ca3af;
                margin-bottom: 30px;
            }}

            .event {{
                display: flex;
                gap: 18px;
                padding: 20px;
                margin-bottom: 15px;
                background: #1f2937;
                border-radius: 16px;
            }}

            .icon {{
                font-size: 32px;
            }}

            h2 {{
                margin: 0 0 6px 0;
                font-size: 20px;
            }}

            p {{
                margin: 0 0 6px 0;
                color: #d1d5db;
            }}

            span {{
                color: #60a5fa;
            }}

            .footer {{
                margin-top: 30px;
                color: #6b7280;
                font-size: 13px;
                text-align: center;
            }}
        </style>
    </head>

    <body>
        <div class="container">

            <h1>🎵 Flathead Live</h1>

            <div class="subtitle">
                Live music, concerts, film festivals & local events
            </div>

            {cards}

            <div class="footer">
                Last updated: {datetime.now().strftime("%B %d, %Y %I:%M %p")}
            </div>

        </div>
    </body>
    </html>
    """


@app.get("/health")
def health():
    return {
        "status": "online",
        "message": "Flathead Live is running!"
    }
