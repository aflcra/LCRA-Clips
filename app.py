#!/usr/bin/env python3
"""
Alerts Digest — Google Alerts RSS → LCRA-style HTML digest
Run locally:  python3 app.py
Deploy:       Render Web Service, start command: python3 app.py
"""

import http.server
import json
import os
import threading
import time
import urllib.request
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── PERSISTENCE ───────────────────────────────────────────────────────────────
DATA_FILE = Path('data.json')

DEFAULT_CATEGORIES = [
    'LCRA',
    'WATER',
    'POWER/GENERAL',
    'POWER/TEXAS AGENCIES/POLICY',
    'POWER/FEDERAL AGENCIES/POLICY',
    'POWER/DATA CENTERS',
    'POWER/RENEWABLES',
]

DEFAULT_FEEDS = [
    # LCRA
    {'id': 'f1',  'label': 'LCRA (1)',                        'url': 'https://www.google.com/alerts/feeds/13511019394945225480/5196916693591774672',  'category': 'LCRA'},
    {'id': 'f2',  'label': 'LCRA (2)',                        'url': 'https://www.google.com/alerts/feeds/13511019394945225480/13384593130295334636', 'category': 'LCRA'},
    {'id': 'f3',  'label': 'LCRA (3)',                        'url': 'https://www.google.com/alerts/feeds/13511019394945225480/14521192268956444991', 'category': 'LCRA'},
    {'id': 'f4',  'label': 'LCRA (4)',                        'url': 'https://www.google.com/alerts/feeds/13511019394945225480/2601092851162468878',  'category': 'LCRA'},
    {'id': 'f5',  'label': 'LCRA (5)',                        'url': 'https://www.google.com/alerts/feeds/13511019394945225480/13657602621270007615', 'category': 'LCRA'},
    {'id': 'f6',  'label': 'LCRA (6)',                        'url': 'https://www.google.com/alerts/feeds/13511019394945225480/9859098899763733085',  'category': 'LCRA'},
    # WATER
    {'id': 'f7',  'label': 'Water (1)',                       'url': 'https://www.google.com/alerts/feeds/13511019394945225480/9024913130796224535',  'category': 'WATER'},
    {'id': 'f8',  'label': 'Water (2)',                       'url': 'https://www.google.com/alerts/feeds/13511019394945225480/4627425023827007235',  'category': 'WATER'},
    # POWER/GENERAL
    {'id': 'f9',  'label': 'Power/General (1)',               'url': 'https://www.google.com/alerts/feeds/13511019394945225480/10002473983532597975', 'category': 'POWER/GENERAL'},
    {'id': 'f10', 'label': 'Power/General (2)',               'url': 'https://www.google.com/alerts/feeds/13511019394945225480/13319106911004620620', 'category': 'POWER/GENERAL'},
    {'id': 'f11', 'label': 'Power/General (3)',               'url': 'https://www.google.com/alerts/feeds/13511019394945225480/10858855206459240367', 'category': 'POWER/GENERAL'},
    # POWER/TEXAS AGENCIES/POLICY
    {'id': 'f12', 'label': 'Power/Texas Agencies/Policy',    'url': 'https://www.google.com/alerts/feeds/13511019394945225480/113139485254667152',   'category': 'POWER/TEXAS AGENCIES/POLICY'},
    # POWER/FEDERAL AGENCIES/POLICY
    {'id': 'f13', 'label': 'Power/Federal Agencies/Policy',  'url': 'https://www.google.com/alerts/feeds/13511019394945225480/5453680920866486539',  'category': 'POWER/FEDERAL AGENCIES/POLICY'},
    # POWER/DATA CENTERS
    {'id': 'f14', 'label': 'Power/Data Centers',             'url': 'https://www.google.com/alerts/feeds/13511019394945225480/5167466528067371434',  'category': 'POWER/DATA CENTERS'},
    # POWER/RENEWABLES
    {'id': 'f15', 'label': 'Power/Renewables',               'url': 'https://www.google.com/alerts/feeds/13511019394945225480/17155108499299171508', 'category': 'POWER/RENEWABLES'},
]

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except Exception:
            pass
    return {
        'categories': DEFAULT_CATEGORIES,
        'feeds': DEFAULT_FEEDS,
    }

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))

# ── RSS PARSING ───────────────────────────────────────────────────────────────

def fetch_feed(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; AlertsDigest/1.0)',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()
    except Exception as e:
        print(f'  [WARN] fetch failed {url}: {e}')
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f'  [WARN] XML parse error {url}: {e}')
        return []

    items = []
    # Google Alerts uses Atom format
    atom_ns = 'http://www.w3.org/2005/Atom'
    entries = root.findall(f'{{{atom_ns}}}entry')
    if entries:
        for entry in entries:
            title_el = entry.find(f'{{{atom_ns}}}title')
            title = title_el.text if title_el is not None else 'Untitled'
            link_el = entry.find(f'{{{atom_ns}}}link')
            link = link_el.get('href', '') if link_el is not None else ''
            # Google Alerts wraps the real URL in a google.com redirect
            link = unwrap_google_url(link)
            updated_el = entry.find(f'{{{atom_ns}}}updated')
            pub = updated_el.text if updated_el is not None else ''
            source_el = entry.find(f'{{{atom_ns}}}source')
            source_title = ''
            if source_el is not None:
                st = source_el.find(f'{{{atom_ns}}}title')
                if st is not None:
                    source_title = st.text or ''
            content_el = entry.find(f'{{{atom_ns}}}content')
            snippet = strip_html(content_el.text if content_el is not None else '')
            items.append({
                'title': strip_html(title),
                'link': link,
                'pubDate': pub,
                'source': source_title,
                'snippet': snippet,
            })
    else:
        # Fallback: RSS 2.0
        channel = root.find('channel') or root
        for item in channel.findall('item'):
            title = _el_text(item, 'title')
            link  = _el_text(item, 'link') or _el_text(item, 'guid')
            pub   = _el_text(item, 'pubDate')
            items.append({
                'title': strip_html(title or ''),
                'link': link or '',
                'pubDate': pub or '',
                'source': '',
            })

    return items

def unwrap_google_url(url):
    """Extract the real URL from a Google redirect URL."""
    if 'google.com/url' in url or 'google.com/alerts' in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if 'url' in qs:
            return qs['url'][0]
        if 'q' in qs:
            return qs['q'][0]
    return url

def _el_text(el, tag):
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else ''

def strip_html(s):
    import re
    return re.sub(r'<[^>]+>', '', s or '').strip()

def parse_date(s):
    if not s:
        return None
    for fmt in (
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S%z',
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%d',
    ):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None

def fmt_date_display(dt):
    if dt is None:
        return ''
    return dt.strftime('%-m/%-d/%y')

# ── HTTP HANDLER ──────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self._send(200, 'text/html; charset=utf-8', get_html().encode())
        elif self.path == '/config':
            data = load_data()
            self._send_json(data)
        else:
            self._send(404, 'text/plain', b'Not found')

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == '/search':
            self._send_json(self._do_search(body))
        elif self.path == '/config/save':
            save_data(body)
            self._send_json({'ok': True})
        else:
            self._send(404, 'text/plain', b'Not found')

    def _do_search(self, body):
        feeds      = body.get('feeds', [])
        categories = body.get('categories', DEFAULT_CATEGORIES)
        date_from  = body.get('date_from')   # ISO date string or None
        date_to    = body.get('date_to')     # ISO date string or None

        # Parse date window
        tz = timezone.utc
        dt_from = None
        dt_to   = None
        if date_from:
            try:
                dt_from = datetime.strptime(date_from, '%Y-%m-%d').replace(tzinfo=tz)
            except Exception:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(tzinfo=tz) + timedelta(days=1)
            except Exception:
                pass

        # Fetch all articles from all feeds
        all_articles = []
        for feed in feeds:
            url      = feed.get('url', '')
            category = feed.get('category', '')
            label    = feed.get('label', url)
            if not url:
                continue
            print(f'  Fetching [{category}] {label}')
            items = fetch_feed(url)
            for item in items:
                item['category'] = category
                item['feedLabel'] = label
                all_articles.append(item)

        print(f'  Total fetched: {len(all_articles)}')

        # Filter by date window
        filtered = []
        for item in all_articles:
            dt = parse_date(item.get('pubDate', ''))
            item['dateObj']   = dt.isoformat() if dt else None
            item['dateDisplay'] = fmt_date_display(dt)
            if dt_from and dt and dt < dt_from:
                continue
            if dt_to and dt and dt >= dt_to:
                continue
            filtered.append(item)

        print(f'  After date filter: {len(filtered)}')

        # Group by category (preserving order)
        cat_map = {c: [] for c in categories}
        uncategorized = []
        for item in filtered:
            cat = item.get('category', '')
            if cat in cat_map:
                cat_map[cat].append(item)
            else:
                uncategorized.append(item)

        # Sort each group newest first
        result = []
        for cat in categories:
            articles = cat_map[cat]
            articles.sort(key=lambda x: x.get('dateObj') or '', reverse=True)
            result.append({
                'catName': cat,
                'articles': [{
                    'title':    a.get('title', 'Untitled'),
                    'link':     a.get('link', '#'),
                    'date':     a.get('dateDisplay', ''),
                    'source':   a.get('source', '') or a.get('feedLabel', ''),
                    'category': a.get('category', ''),
                    'snippet':  a.get('snippet', ''),
                } for a in articles]
            })

        return result

    def _send_json(self, data):
        payload = json.dumps(data).encode()
        self._send(200, 'application/json', payload)

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

# ── HTML FRONTEND ─────────────────────────────────────────────────────────────

def get_html():
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alerts Digest</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root {
  --ink:#0f0f0f; --paper:#f5f0e8; --cream:#ede8de; --rule:#c8bfae;
  --accent:#c1440e; --accent-dark:#8f3209; --muted:#7a7267; --blue:#0073C8;
}
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'IBM Plex Sans',sans-serif; background:var(--paper); color:var(--ink); min-height:100vh; }

header { border-bottom:3px double var(--ink); padding:18px 36px 13px; display:flex; align-items:baseline; gap:16px; background:var(--paper); position:sticky; top:0; z-index:100; }
header h1 { font-family:'Playfair Display',serif; font-size:clamp(1.4rem,2.5vw,1.9rem); font-weight:700; letter-spacing:-0.02em; }
header h1 span { color:var(--accent); }
.tagline { font-family:'IBM Plex Mono',monospace; font-size:0.6rem; color:var(--muted); letter-spacing:0.14em; text-transform:uppercase; margin-left:auto; }

.shell { display:grid; grid-template-columns:300px 1fr; min-height:calc(100vh - 65px); }

/* SIDEBAR */
aside { border-right:1px solid var(--rule); padding:20px 16px; background:var(--cream); display:flex; flex-direction:column; gap:16px; overflow-y:auto; }
.slabel { font-family:'IBM Plex Mono',monospace; font-size:0.58rem; letter-spacing:0.18em; text-transform:uppercase; color:var(--muted); border-bottom:1px solid var(--rule); padding-bottom:3px; margin-bottom:6px; }
.hint { font-size:0.65rem; color:var(--muted); margin-top:3px; line-height:1.5; }

/* Date filter */
.date-row { display:flex; align-items:center; gap:6px; }
.date-row label { font-size:0.72rem; color:var(--muted); white-space:nowrap; }
.date-row input[type=date] { flex:1; background:var(--paper); border:1px solid var(--rule); padding:5px 7px; font-family:'IBM Plex Mono',monospace; font-size:0.68rem; color:var(--ink); outline:none; }
.date-row input[type=date]:focus { border-color:var(--blue); }

/* Category chips */
.cat-chips { display:flex; flex-wrap:wrap; gap:4px; }
.cat-chip { font-family:'IBM Plex Mono',monospace; font-size:0.65rem; padding:3px 8px; background:var(--blue); color:#fff; border-radius:2px; cursor:default; }

/* Buttons */
.btn { border:none; cursor:pointer; font-family:'IBM Plex Mono',monospace; font-size:0.7rem; letter-spacing:0.06em; text-transform:uppercase; padding:8px 12px; transition:background .15s,opacity .15s; }
.btn-primary { background:var(--accent); color:var(--paper); width:100%; padding:12px; font-family:'Playfair Display',serif; font-size:0.95rem; letter-spacing:0.03em; font-weight:700; }
.btn-primary:hover { background:var(--accent-dark); }
.btn-primary:disabled { background:var(--rule); cursor:not-allowed; }
.btn-ink { background:var(--ink); color:var(--paper); }
.btn-ink:hover { background:var(--blue); }
.btn-outline { background:none; border:1px solid var(--rule); color:var(--ink); }
.btn-outline:hover { border-color:var(--ink); }
.btn-dl { width:100%; margin-top:6px; display:none; background:var(--ink); color:var(--paper); padding:10px; font-family:'IBM Plex Mono',monospace; font-size:0.7rem; letter-spacing:0.1em; text-transform:uppercase; border:none; cursor:pointer; }
.btn-dl:hover { background:var(--blue); }
.btn-dl.show { display:block; }

/* Advanced section */
.adv-toggle { background:none; border:none; cursor:pointer; font-family:'IBM Plex Mono',monospace; font-size:0.6rem; color:var(--muted); letter-spacing:0.12em; text-transform:uppercase; display:flex; align-items:center; gap:5px; padding:0; }
.adv-toggle:hover { color:var(--ink); }
.adv-toggle .arrow { transition:transform .2s; display:inline-block; }
.adv-toggle.open .arrow { transform:rotate(90deg); }
.adv-panel { display:none; margin-top:8px; }
.adv-panel.open { display:flex; flex-direction:column; gap:10px; }

/* Feed list */
.feed-list { display:flex; flex-direction:column; gap:5px; max-height:260px; overflow-y:auto; }
.feed-item { background:var(--paper); border:1px solid var(--rule); padding:7px 9px; display:flex; flex-direction:column; gap:2px; }
.feed-item-top { display:flex; align-items:flex-start; gap:6px; }
.feed-label { font-family:'IBM Plex Mono',monospace; font-size:0.65rem; font-weight:500; color:var(--blue); flex:1; word-break:break-word; }
.feed-cat-badge { font-family:'IBM Plex Mono',monospace; font-size:0.55rem; padding:1px 5px; background:var(--ink); color:var(--paper); border-radius:2px; white-space:nowrap; flex-shrink:0; }
.feed-url { font-family:'IBM Plex Mono',monospace; font-size:0.55rem; color:var(--muted); word-break:break-all; }
.feed-rm { background:none; border:none; color:var(--rule); cursor:pointer; font-size:0.9rem; line-height:1; padding:0; flex-shrink:0; }
.feed-rm:hover { color:var(--accent); }

/* Add feed form */
.add-feed-form { display:flex; flex-direction:column; gap:5px; }
.add-feed-form input, .add-feed-form select { background:var(--paper); border:1px solid var(--rule); padding:6px 8px; font-family:'IBM Plex Mono',monospace; font-size:0.68rem; color:var(--ink); outline:none; width:100%; }
.add-feed-form input:focus, .add-feed-form select:focus { border-color:var(--blue); }

/* Category manager */
.cat-mgr { display:flex; flex-direction:column; gap:5px; }
.cat-mgr-item { display:flex; align-items:center; gap:6px; }
.cat-mgr-item span { font-family:'IBM Plex Mono',monospace; font-size:0.68rem; flex:1; }
.cat-mgr-item button { background:none; border:none; color:var(--rule); cursor:pointer; font-size:0.9rem; line-height:1; padding:0; }
.cat-mgr-item button:hover { color:var(--accent); }
.cat-add-row { display:flex; gap:5px; }
.cat-add-row input { flex:1; background:var(--paper); border:1px solid var(--rule); padding:6px 8px; font-family:'IBM Plex Mono',monospace; font-size:0.68rem; color:var(--ink); outline:none; text-transform:uppercase; }
.cat-add-row input::placeholder { text-transform:none; }
.cat-add-row input:focus { border-color:var(--blue); }
.cat-add-row button { background:var(--ink); color:var(--paper); border:none; padding:6px 10px; font-size:0.75rem; cursor:pointer; }
.cat-add-row button:hover { background:var(--blue); }

/* Export/import */
.config-row { display:flex; gap:5px; }
.config-row button { flex:1; }

/* MAIN */
main { padding:24px 28px; overflow-y:auto; }
#status-bar { display:none; align-items:center; gap:10px; padding:9px 13px; background:var(--cream); border:1px solid var(--rule); margin-bottom:16px; font-family:'IBM Plex Mono',monospace; font-size:0.68rem; color:var(--muted); }
#status-bar.show { display:flex; }
.spin { width:12px; height:12px; border:2px solid var(--rule); border-top-color:var(--accent); border-radius:50%; animation:spin .7s linear infinite; flex-shrink:0; }
@keyframes spin { to { transform:rotate(360deg); } }
#sum-bar { display:none; margin-bottom:16px; padding:10px 15px; background:var(--ink); color:var(--paper); font-family:'IBM Plex Mono',monospace; font-size:0.68rem; gap:16px; flex-wrap:wrap; }
#sum-bar.show { display:flex; }
#sum-bar strong { color:#f5c57a; }

/* Results */
.cat-sec { margin-bottom:24px; animation:fadeUp .3s ease forwards; opacity:0; }
@keyframes fadeUp { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
.cat-hdr { display:flex; align-items:baseline; gap:10px; padding-bottom:7px; border-bottom:3px solid var(--blue); margin-bottom:10px; }
.cat-hdr h2 { font-family:'IBM Plex Mono',monospace; font-size:1rem; font-weight:500; letter-spacing:0.12em; color:var(--blue); text-transform:uppercase; }
.cat-hdr .cnt { font-family:'IBM Plex Mono',monospace; font-size:0.62rem; color:var(--muted); }

.art-row { display:grid; grid-template-columns:1fr auto; gap:10px; padding:9px 0; border-bottom:1px solid var(--rule); align-items:start; }
.art-title { font-family:'Playfair Display',serif; font-size:0.9rem; font-weight:700; line-height:1.35; color:var(--blue); text-decoration:none; }
.art-title:hover { text-decoration:underline; }
.art-meta { font-family:'IBM Plex Mono',monospace; font-size:0.61rem; color:var(--muted); margin-top:2px; }
.art-actions { display:flex; flex-direction:column; gap:4px; align-items:flex-end; }
.btn-remove { background:none; border:1px solid var(--rule); color:var(--muted); cursor:pointer; font-family:'IBM Plex Mono',monospace; font-size:0.58rem; padding:2px 7px; transition:all .15s; white-space:nowrap; }
.btn-remove:hover { border-color:var(--accent); color:var(--accent); }
.btn-move { background:none; border:1px solid var(--rule); color:var(--muted); cursor:pointer; font-family:'IBM Plex Mono',monospace; font-size:0.55rem; padding:2px 6px; transition:all .15s; }
.btn-move:hover { border-color:var(--ink); color:var(--ink); }
.btn-paywall { background:none; border:1px solid var(--rule); color:var(--muted); cursor:pointer; font-family:'IBM Plex Mono',monospace; font-size:0.55rem; padding:2px 6px; transition:all .15s; white-space:nowrap; }
.btn-paywall:hover { border-color:#e6a817; color:#e6a817; }
.btn-paywall.active { background:#e6a817; border-color:#e6a817; color:#fff; }

/* Add manual entry */
.add-entry-section { margin-top:10px; border-top:1px dashed var(--rule); padding-top:10px; }
.add-entry-section summary { font-family:'IBM Plex Mono',monospace; font-size:0.62rem; color:var(--muted); cursor:pointer; letter-spacing:0.08em; text-transform:uppercase; }
.add-entry-section summary:hover { color:var(--ink); }
.add-entry-form { display:flex; flex-direction:column; gap:5px; margin-top:8px; }
.add-entry-form input { background:var(--paper); border:1px solid var(--rule); padding:6px 8px; font-family:'IBM Plex Mono',monospace; font-size:0.68rem; color:var(--ink); outline:none; width:100%; }
.add-entry-form input:focus { border-color:var(--blue); }
.add-entry-form button { align-self:flex-start; background:var(--ink); color:var(--paper); border:none; padding:5px 12px; font-family:'IBM Plex Mono',monospace; font-size:0.65rem; cursor:pointer; }
.add-entry-form button:hover { background:var(--blue); }

.empty { text-align:center; padding:55px 28px; color:var(--muted); }
.empty .big { font-family:'Playfair Display',serif; font-size:3.5rem; color:var(--rule); display:block; margin-bottom:10px; }
.empty p { font-size:0.84rem; line-height:1.8; }
.nores { font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:var(--muted); padding:7px 0; font-style:italic; }
.art-snippet { font-size:0.78rem; color:var(--muted); line-height:1.5; margin-top:3px; }
</style>
</head>
<body>
<header>
  <h1>Alerts <span>Digest</span></h1>
  <p class="tagline">Google Alerts → LCRA Digest</p>
</header>

<div class="shell">
<aside>

  <!-- DATE FILTER -->
  <div>
    <p class="slabel">Date Range</p>
    <div class="date-row" style="margin-bottom:5px">
      <label>From</label>
      <input type="date" id="date-from">
    </div>
    <div class="date-row">
      <label>To</label>
      <input type="date" id="date-to">
    </div>
    <p class="hint">Default: today only. Adjust to include more days.</p>
  </div>

  <!-- CATEGORIES PREVIEW -->
  <div>
    <p class="slabel">Active Categories</p>
    <div class="cat-chips" id="cat-chips"></div>
  </div>

  <!-- ACTIONS -->
  <div style="margin-top:auto">
    <button class="btn btn-primary" id="run-btn" type="button">Generate Digest →</button>
    <button class="btn-dl" id="dl-btn" type="button">⬇ Download Digest</button>
  </div>

  <!-- ADVANCED -->
  <div style="border-top:1px solid var(--rule); padding-top:12px;">
    <button class="adv-toggle" id="adv-toggle" type="button">
      <span class="arrow">▶</span> Advanced Settings
    </button>
    <div class="adv-panel" id="adv-panel">

      <!-- FEEDS -->
      <div>
        <p class="slabel">Google Alert RSS Feeds</p>
        <div class="feed-list" id="feed-list"></div>
        <div class="add-feed-form" style="margin-top:8px">
          <input type="text" id="feed-label" placeholder="Label (e.g. LCRA drought)">
          <input type="text" id="feed-url" placeholder="Google Alerts RSS URL">
          <select id="feed-cat"></select>
          <button class="btn btn-ink" type="button" id="add-feed-btn">+ Add Feed</button>
        </div>
      </div>

      <!-- CATEGORIES -->
      <div>
        <p class="slabel">Manage Categories</p>
        <div class="cat-mgr" id="cat-mgr"></div>
        <div class="cat-add-row" style="margin-top:6px">
          <input type="text" id="new-cat-input" placeholder="New category name…">
          <button type="button" id="add-cat-btn">+</button>
        </div>
      </div>

      <!-- MASTHEAD -->
      <div>
        <p class="slabel">Digest Masthead Title</p>
        <input type="text" id="digest-title" value="LCRA" style="width:100%;background:var(--paper);border:1px solid var(--rule);padding:6px 8px;font-family:'IBM Plex Mono',monospace;font-size:0.72rem;color:var(--ink);outline:none;">
      </div>

      <!-- CONFIG BACKUP -->
      <div>
        <p class="slabel">Config Backup</p>
        <div class="config-row">
          <button class="btn btn-outline" type="button" id="export-config-btn">↓ Export Config</button>
          <button class="btn btn-outline" type="button" id="import-config-btn">↑ Import Config</button>
          <input type="file" id="import-file" accept=".json" style="display:none">
        </div>
        <p class="hint">Export your feeds & categories to a JSON file. Import to restore.</p>
      </div>

    </div>
  </div>

</aside>

<main>
  <div class="empty" id="empty-state">
    <span class="big">⌕</span>
    <p>Add your Google Alert RSS feeds in<br><strong>Advanced Settings</strong>, assign them to categories,<br>set your date range, then hit<br><strong>Generate Digest →</strong></p>
  </div>
  <div id="status-bar"><div class="spin"></div><span id="status-txt">Fetching alerts…</span></div>
  <div id="sum-bar"></div>
  <div id="results"></div>
</main>
</div>

<script>
// ── STATE ─────────────────────────────────────────────────────────────────────
let config = { categories: [], feeds: [] };
let digestData = []; // current results, mutable (user can remove entries)

// ── INIT ──────────────────────────────────────────────────────────────────────
async function init() {
  // Set default date to today
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('date-from').value = today;
  document.getElementById('date-to').value   = today;

  const resp = await fetch('/config');
  config = await resp.json();
  renderAll();
}

function renderAll() {
  renderCatChips();
  renderCatMgr();
  renderFeedList();
  renderFeedCatSelect();
}

// ── CATEGORIES ────────────────────────────────────────────────────────────────
function renderCatChips() {
  const el = document.getElementById('cat-chips');
  el.innerHTML = config.categories.map(c =>
    `<span class="cat-chip">${c}</span>`
  ).join('');
}

function renderCatMgr() {
  const el = document.getElementById('cat-mgr');
  el.innerHTML = '';
  config.categories.forEach((cat, i) => {
    const row = document.createElement('div');
    row.className = 'cat-mgr-item';
    row.innerHTML = `<span>${cat}</span><button type="button" title="Remove" data-i="${i}">×</button>`;
    row.querySelector('button').addEventListener('click', () => removeCat(i));
    el.appendChild(row);
  });
}

function renderFeedCatSelect() {
  const sel = document.getElementById('feed-cat');
  const cur = sel.value;
  sel.innerHTML = config.categories.map(c =>
    `<option value="${c}" ${c === cur ? 'selected' : ''}>${c}</option>`
  ).join('');
}

function addCat() {
  const inp = document.getElementById('new-cat-input');
  const name = inp.value.trim().toUpperCase();
  if (!name || config.categories.includes(name)) { inp.select(); return; }
  config.categories.push(name);
  inp.value = '';
  saveConfig();
  renderAll();
}

function removeCat(i) {
  const cat = config.categories[i];
  if (config.feeds.some(f => f.category === cat)) {
    alert(`Cannot remove "${cat}" — it has feeds assigned to it. Remove or reassign those feeds first.`);
    return;
  }
  config.categories.splice(i, 1);
  saveConfig();
  renderAll();
}

document.getElementById('add-cat-btn').addEventListener('click', addCat);
document.getElementById('new-cat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') addCat();
});

// ── FEEDS ─────────────────────────────────────────────────────────────────────
function renderFeedList() {
  const el = document.getElementById('feed-list');
  el.innerHTML = '';
  if (!config.feeds.length) {
    el.innerHTML = '<p class="hint" style="padding:4px 0">No feeds added yet.</p>';
    return;
  }
  config.feeds.forEach((feed, i) => {
    const item = document.createElement('div');
    item.className = 'feed-item';
    item.innerHTML = `
      <div class="feed-item-top">
        <span class="feed-label">${feed.label || feed.url}</span>
        <span class="feed-cat-badge">${feed.category}</span>
        <button type="button" class="feed-rm" data-i="${i}" title="Remove">×</button>
      </div>
      <span class="feed-url">${feed.url}</span>`;
    item.querySelector('.feed-rm').addEventListener('click', () => removeFeed(i));
    el.appendChild(item);
  });
}

function addFeed() {
  const label = document.getElementById('feed-label').value.trim();
  const url   = document.getElementById('feed-url').value.trim();
  const cat   = document.getElementById('feed-cat').value;
  if (!url) { document.getElementById('feed-url').focus(); return; }
  config.feeds.push({ id: 'f' + Date.now(), label: label || url, url, category: cat });
  document.getElementById('feed-label').value = '';
  document.getElementById('feed-url').value   = '';
  saveConfig();
  renderFeedList();
}

function removeFeed(i) {
  config.feeds.splice(i, 1);
  saveConfig();
  renderFeedList();
}

document.getElementById('add-feed-btn').addEventListener('click', addFeed);

// ── ADVANCED TOGGLE ───────────────────────────────────────────────────────────
document.getElementById('adv-toggle').addEventListener('click', () => {
  const toggle = document.getElementById('adv-toggle');
  const panel  = document.getElementById('adv-panel');
  toggle.classList.toggle('open');
  panel.classList.toggle('open');
});

// ── SAVE CONFIG ───────────────────────────────────────────────────────────────
async function saveConfig() {
  await fetch('/config/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

// ── EXPORT / IMPORT CONFIG ────────────────────────────────────────────────────
document.getElementById('export-config-btn').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'alerts-digest-config.json';
  a.click();
});

document.getElementById('import-config-btn').addEventListener('click', () => {
  document.getElementById('import-file').click();
});

document.getElementById('import-file').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async ev => {
    try {
      const imported = JSON.parse(ev.target.result);
      if (!imported.categories || !imported.feeds) throw new Error('Invalid config file');
      config = imported;
      await saveConfig();
      renderAll();
      alert('Config imported successfully.');
    } catch(err) {
      alert('Failed to import config: ' + err.message);
    }
  };
  reader.readAsText(file);
  e.target.value = '';
});

// ── SEARCH ────────────────────────────────────────────────────────────────────
document.getElementById('run-btn').addEventListener('click', runSearch);

async function runSearch() {
  if (!config.feeds.length) {
    alert('Add at least one Google Alert RSS feed in Advanced Settings first.');
    return;
  }

  const dateFrom = document.getElementById('date-from').value;
  const dateTo   = document.getElementById('date-to').value;
  const runBtn   = document.getElementById('run-btn');
  const statusBar = document.getElementById('status-bar');
  const statusTxt = document.getElementById('status-txt');
  const resultsEl = document.getElementById('results');
  const sumBar    = document.getElementById('sum-bar');
  const dlBtn     = document.getElementById('dl-btn');
  const emptyState = document.getElementById('empty-state');

  runBtn.disabled = true;
  emptyState.style.display = 'none';
  resultsEl.innerHTML = '';
  sumBar.innerHTML = ''; sumBar.classList.remove('show');
  dlBtn.classList.remove('show');
  statusBar.classList.add('show');
  statusTxt.textContent = 'Fetching Google Alerts…';
  digestData = [];

  try {
    const resp = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        feeds: config.feeds,
        categories: config.categories,
        date_from: dateFrom,
        date_to: dateTo,
      }),
    });
    digestData = await resp.json();
    renderResults();
  } catch(e) {
    resultsEl.innerHTML = `<div class="empty"><span class="big" style="font-size:2.5rem">!</span><p>Error: ${e.message}</p></div>`;
  }

  statusBar.classList.remove('show');
  runBtn.disabled = false;
}

function renderResults() {
  const resultsEl = document.getElementById('results');
  const sumBar    = document.getElementById('sum-bar');
  const dlBtn     = document.getElementById('dl-btn');

  resultsEl.innerHTML = '';
  let total = 0;
  let delay = 0;

  for (const section of digestData) {
    total += section.articles.length;
    const sec = document.createElement('div');
    sec.className = 'cat-sec';
    sec.dataset.cat = section.catName;
    sec.style.animationDelay = `${delay}ms`;
    delay += 60;
    renderSection(sec, section);
    resultsEl.appendChild(sec);
  }

  // Add Juicer social media section
  const juicerSec = document.createElement('div');
  juicerSec.className = 'cat-sec';
  juicerSec.style.animationDelay = `${delay}ms`;
  juicerSec.innerHTML = `
    <div class="cat-hdr">
      <h2>SOCIAL MEDIA</h2>
      <span class="cnt">@lcra-flood</span>
    </div>
    <div id="juicer-embed">
      <link rel="stylesheet" href="https://www.juicer.io/embed/lcra-flood/stylesheet.css" type="text/css">
      <div class="juicer-feed" data-feed-id="lcra-flood"></div>
      <script src="https://www.juicer.io/embed/lcra-flood/embed-code.js?beta=true" async defer><\/script>
    </div>`;
  resultsEl.appendChild(juicerSec);

  // Add manual entry form at the bottom
  const addSection = document.createElement('div');
  addSection.innerHTML = `
    <details class="add-entry-section">
      <summary>+ Add a manual entry</summary>
      <div class="add-entry-form">
        <input type="text" id="manual-title" placeholder="Article headline">
        <input type="text" id="manual-url" placeholder="Article URL">
        <select id="manual-cat" style="background:var(--paper);border:1px solid var(--rule);padding:6px 8px;font-family:'IBM Plex Mono',monospace;font-size:0.68rem;color:var(--ink);outline:none;width:100%">
          ${config.categories.map(c => `<option value="${c}">${c}</option>`).join('')}
        </select>
        <button type="button" onclick="addManualEntry()">Add to Digest</button>
      </div>
    </details>`;
  resultsEl.appendChild(addSection);

  sumBar.innerHTML = `
    <span><strong>${total}</strong> articles</span>
    <span><strong>${digestData.filter(s => s.articles.length).length}</strong> categories with results</span>`;
  sumBar.classList.add('show');
  if (total > 0) dlBtn.classList.add('show');

  if (total === 0) {
    resultsEl.innerHTML = `<div class="empty"><span class="big" style="font-size:3rem">∅</span><p>No alerts found for this date range.<br>Try widening the date filter or check your feed URLs.</p></div>`;
  }
}

function renderSection(sec, section) {
  const articles = section.articles;
  let html = `
    <div class="cat-hdr">
      <h2>${section.catName}</h2>
      <span class="cnt">${articles.length} article${articles.length !== 1 ? 's' : ''}</span>
    </div>`;

  if (!articles.length) {
    html += `<p class="nores">No alerts in this category for the selected date range.</p>`;
  } else {
    articles.forEach((art, i) => {
      html += `
        <div class="art-row" data-idx="${i}">
          <div>
            <a class="art-title" href="${art.link}" target="_blank" rel="noopener">${art.title}</a>
            <div class="art-meta">${art.date ? art.date + ' · ' : ''}${art.source || ''}</div>
            ${art.snippet ? '<div class="art-snippet">' + art.snippet + '</div>' : ''}
          </div>
          <div class="art-actions">
            <button type="button" class="btn-remove" data-cat="${section.catName}" data-idx="${i}">Remove</button>
            <select class="btn-move" data-cat="${section.catName}" data-idx="${i}" title="Move to category">
              ${config.categories.map(c => `<option value="${c}" ${c === section.catName ? 'selected' : ''}>${c}</option>`).join('')}
            </select>
            <button type="button" class="btn-paywall ${art.paywallBypass ? 'active' : ''}" data-cat="${section.catName}" data-idx="${i}" title="Remove paywall">⚿ ${art.paywallBypass ? 'Bypassed' : 'Paywall'}</button>
          </div>
        </div>`;
    });
  }

  sec.innerHTML = html;

  // Remove buttons
  sec.querySelectorAll('.btn-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      removeArticle(btn.dataset.cat, parseInt(btn.dataset.idx));
    });
  });

  // Move selects
  sec.querySelectorAll('.btn-move').forEach(sel => {
    sel.addEventListener('change', () => {
      moveArticle(sel.dataset.cat, parseInt(sel.dataset.idx), sel.value);
    });
  });

  // Paywall toggle buttons
  sec.querySelectorAll('.btn-paywall').forEach(btn => {
    btn.addEventListener('click', () => {
      togglePaywall(btn.dataset.cat, parseInt(btn.dataset.idx));
    });
  });
}

function removeArticle(catName, idx) {
  const section = digestData.find(s => s.catName === catName);
  if (!section) return;
  section.articles.splice(idx, 1);
  rerenderSection(catName);
  updateSummary();
}

function moveArticle(fromCat, idx, toCat) {
  if (fromCat === toCat) return;
  const fromSection = digestData.find(s => s.catName === fromCat);
  const toSection   = digestData.find(s => s.catName === toCat);
  if (!fromSection || !toSection) return;
  const [art] = fromSection.articles.splice(idx, 1);
  art.category = toCat;
  toSection.articles.unshift(art);
  rerenderSection(fromCat);
  rerenderSection(toCat);
  updateSummary();
}

function togglePaywall(catName, idx) {
  const section = digestData.find(s => s.catName === catName);
  if (!section) return;
  const art = section.articles[idx];
  if (!art) return;
  const PROXY = 'https://removepaywalls.com/';
  if (art.paywallBypass) {
    // Remove bypass — restore original URL
    art.link = art.link.replace(PROXY, '');
    art.paywallBypass = false;
  } else {
    // Apply bypass
    art.link = PROXY + art.link;
    art.paywallBypass = true;
  }
  rerenderSection(catName);
}

function rerenderSection(catName) {
  const sec     = document.querySelector(`.cat-sec[data-cat="${catName}"]`);
  const section = digestData.find(s => s.catName === catName);
  if (sec && section) renderSection(sec, section);
}

function updateSummary() {
  const total = digestData.reduce((t, s) => t + s.articles.length, 0);
  const sumBar = document.getElementById('sum-bar');
  sumBar.innerHTML = `
    <span><strong>${total}</strong> articles</span>
    <span><strong>${digestData.filter(s => s.articles.length).length}</strong> categories with results</span>`;
  document.getElementById('dl-btn').classList.toggle('show', total > 0);
}

function addManualEntry() {
  const title = document.getElementById('manual-title').value.trim();
  const url   = document.getElementById('manual-url').value.trim();
  const cat   = document.getElementById('manual-cat').value;
  if (!title || !url) { alert('Please enter both a headline and a URL.'); return; }

  const section = digestData.find(s => s.catName === cat);
  if (!section) return;

  const today = new Date().toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' });
  section.articles.unshift({ title, link: url, date: today, source: 'Manual entry', category: cat });
  document.getElementById('manual-title').value = '';
  document.getElementById('manual-url').value   = '';
  rerenderSection(cat);
  updateSummary();
}

// ── DOWNLOAD DIGEST ───────────────────────────────────────────────────────────
document.getElementById('dl-btn').addEventListener('click', downloadDigest);

function downloadDigest() {
  const mastheadTitle = document.getElementById('digest-title').value.trim() || 'News Digest';
  const today = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

  let sectionsHtml = '';
  for (const sec of digestData) {
    if (!sec.articles.length) continue;

    sectionsHtml += `
    <table style="min-width:100%;border-collapse:collapse" width="100%" cellspacing="0" cellpadding="0" border="0">
      <tbody><tr><td style="padding-top:9px" valign="top">
        <table style="max-width:100%;min-width:100%;border-collapse:collapse;float:left" width="100%" cellspacing="0" cellpadding="0" border="0" align="left">
          <tbody><tr>
            <td style="padding:0px 18px 9px;text-align:left;word-break:break-word;color:#696969;font-family:Helvetica;font-size:16px;line-height:100%" valign="top">
              <h1 style="display:block;margin:0;padding:0;color:#202020;font-family:Helvetica;font-size:26px;font-style:normal;font-weight:bold;line-height:125%;letter-spacing:normal;text-align:left">
                <span style="color:#0073C8">${sec.catName}</span>
              </h1>
            </td>
          </tr></tbody>
        </table>
      </td></tr></tbody>
    </table>
    <table style="min-width:100%;border-collapse:collapse" width="100%" cellspacing="0" cellpadding="0" border="0">
      <tbody><tr><td style="padding-top:9px" valign="top">
        <table style="max-width:100%;min-width:100%;border-collapse:collapse;float:left" width="100%" cellspacing="0" cellpadding="0" border="0" align="left">
          <tbody><tr>
            <td style="padding:0px 18px 9px;font-style:normal;font-weight:normal;line-height:125%;word-break:break-word;color:#696969;font-family:Helvetica;font-size:16px;text-align:left" valign="top">
              ${sec.articles.map(art => `
                <p style="font-style:normal;font-weight:normal;line-height:125%;margin:10px 0;padding:0;color:#696969;font-family:Helvetica;font-size:16px;text-align:left" dir="ltr">
                  <a style="color:#0073c8;font-weight:normal;text-decoration:underline" href="${art.link}" target="_blank" rel="noopener noreferrer">${art.title}</a>
                </p>
                <p style="font-style:normal;font-weight:normal;line-height:125%;margin:2px 0 4px;padding:0;color:#696969;font-family:Helvetica;font-size:16px;text-align:left" dir="ltr">
                  ${art.date ? art.date + ' ' : ''}${art.source || ''}
                </p>
                ${art.snippet ? '<p style="font-style:normal;font-weight:normal;line-height:125%;margin:2px 0 14px;padding:0;color:#999999;font-family:Helvetica;font-size:14px;text-align:left" dir="ltr">' + art.snippet + '</p>' : '<p style="margin:0 0 14px"></p>'}`).join('')}
            </td>
          </tr></tbody>
        </table>
      </td></tr></tbody>
    </table>`;
  }

  // Juicer section for digest download
  const juicerDigestSection = `
    <table style="min-width:100%;border-collapse:collapse" width="100%" cellspacing="0" cellpadding="0" border="0">
      <tbody><tr><td style="padding-top:9px" valign="top">
        <table style="max-width:100%;min-width:100%;border-collapse:collapse;float:left" width="100%" cellspacing="0" cellpadding="0" border="0" align="left">
          <tbody><tr>
            <td style="padding:0px 18px 9px;text-align:left;word-break:break-word;color:#696969;font-family:Helvetica;font-size:16px;line-height:100%" valign="top">
              <h1 style="display:block;margin:0;padding:0;color:#202020;font-family:Helvetica;font-size:26px;font-style:normal;font-weight:bold;line-height:125%;letter-spacing:normal;text-align:left">
                <span style="color:#0073C8">SOCIAL MEDIA</span>
              </h1>
            </td>
          </tr></tbody>
        </table>
      </td></tr></tbody>
    </table>
    <table style="min-width:100%;border-collapse:collapse" width="100%" cellspacing="0" cellpadding="0" border="0">
      <tbody><tr><td style="padding:9px 18px 18px" valign="top">
        <link rel="stylesheet" href="https://www.juicer.io/embed/lcra-flood/stylesheet.css" type="text/css">
        <div class="juicer-feed" data-feed-id="lcra-flood"></div>
        <script src="https://www.juicer.io/embed/lcra-flood/embed-code.js?beta=true" async defer><\/script>
      </td></tr></tbody>
    </table>`;

  const html = `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>${mastheadTitle} – ${today}</title></head>
<body style="background:#ffffff;margin:0;padding:0;font-family:Helvetica,sans-serif;">
<table style="width:100%;max-width:680px;margin:0 auto;background:#ffffff" cellspacing="0" cellpadding="0" border="0">
  <tbody>
    <tr><td style="padding:28px 18px 4px;border-bottom:2px solid #cccccc;">
      <table width="100%" cellspacing="0" cellpadding="0" border="0"><tbody><tr>
        <td><h1 style="font-family:Helvetica;font-size:26px;font-weight:bold;margin:0;line-height:125%"><span style="color:#0073C8">${mastheadTitle}</span></h1></td>
        <td style="text-align:right;vertical-align:bottom"><span style="font-family:Helvetica;font-size:12px;color:#888">${today}</span></td>
      </tr></tbody></table>
    </td></tr>
    <tr><td valign="top">${sectionsHtml}${juicerDigestSection}</td></tr>
    <tr><td style="padding:16px 18px;border-top:1px solid #ccc">
      <p style="font-family:Helvetica;font-size:11px;color:#aaa;margin:0;text-align:center">Generated by Alerts Digest · ${today}</p>
    </td></tr>
  </tbody>
</table></body></html>`;

  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
  a.download = `${mastheadTitle.replace(/\s+/g,'-').toLowerCase()}-${new Date().toISOString().slice(0,10)}.html`;
  a.click();
}

// ── START ─────────────────────────────────────────────────────────────────────
init();
</script>
</body>
</html>"""

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8765))
    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Alerts Digest starting on port {PORT}...')

    if not os.environ.get('PORT'):
        url = f'http://localhost:{PORT}'
        print(f'Open in browser: {url}')
        def open_browser():
            time.sleep(1.2)
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Stopped.')
