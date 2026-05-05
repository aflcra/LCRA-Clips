# Alerts Digest

Google Alerts RSS → LCRA-style HTML digest builder.

## How it works

1. Set up Google Alerts at [google.com/alerts](https://google.com/alerts)
2. For each alert, click **RSS** to get the feed URL
3. Paste those URLs into **Advanced Settings** in the app
4. Assign each feed to a category (LCRA, WATER, POWER, etc.)
5. Set your date range and hit **Generate Digest**
6. Remove unwanted articles, add manual entries, then **Download Digest**

## Run locally

```bash
python3 app.py
```

Opens automatically at http://localhost:8765. No dependencies required — uses Python standard library only.

## Deploy to Render

1. Push this repo to GitHub
2. Create a new **Web Service** on [render.com](https://render.com)
3. Connect your GitHub repo
4. Set start command: `python3 app.py`
5. Deploy — your app will be live at `https://your-app.onrender.com`

## Persistence note

Feeds and categories are saved to `data.json` on the server. This persists between restarts but **not between redeploys** on Render's free tier. Use **Export Config** in Advanced Settings to back up your feeds before redeploying, then **Import Config** to restore them.

## Categories

Default categories: LCRA, WATER, POWER, CYBERSECURITY, ECONOMY, FINANCIAL MARKETS

Add, remove, or reorder categories in **Advanced Settings**.

## Features

- **Date filter** — show only today's alerts, or widen the range
- **Remove entries** — click Remove on any article before downloading
- **Move entries** — reassign an article to a different category using the dropdown
- **Add manual entry** — paste in a headline + URL to any category
- **Download Digest** — exports an LCRA-style HTML file ready to send
- **Export/Import Config** — back up and restore your feeds and categories
