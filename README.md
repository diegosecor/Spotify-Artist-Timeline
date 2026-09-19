# Global Artist Timeline & Peak Explorer

**CMU 15-113 — HW3: Explore an API**

![Python](https://img.shields.io/badge/Python-3.10%2B-green) ![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5.8-red) ![Spotify Web API](https://img.shields.io/badge/Spotify-Web%20API-1DB954)

---

## 1. Project Overview

**Global Artist Timeline & Peak Explorer** is a full-screen desktop data-visualization dashboard, built with `pygame-ce`, that lets you search for a music artist and explore their career trajectory as an interactive "mountain" chart of global peak rank over time. It integrates the **Spotify Web API** (through the `spotipy` Python wrapper) for live artist search and discovery, and pairs it with a curated local historical dataset so up to six artists can be pinned and compared side by side.

---

## 2. API Integration Details

The application talks to the **Spotify Web API** using the `spotipy` Python wrapper, authenticating with the OAuth 2.0 **Client Credentials** flow via `SpotifyClientCredentials` (an app-level flow that requires no end-user login). Live artist search is performed with `sp.search(q=<query>, type='artist', limit=10)`, where `q` is the user's typed query, `type` restricts results to artists, and `limit` caps the page size at 10 (the current maximum for this API access tier). Spotify returns **JSON payloads that deserialize into nested Python dictionaries and lists** — for example `results['artists']['items']` is a list of artist objects, each containing keys such as `id`, `name`, `genres`, `images`, and (depending on access tier) `followers.total`; the app reads every field defensively with `.get()` so a missing or renamed key can never raise a `KeyError`. Because Spotify's February/March 2026 Developer Mode changes removed the `/artists/{id}/top-tracks` endpoint and stripped the `popularity` and `followers` fields from Artist objects for this tier, the project uses a **hybrid fallback architecture**: live search supplies artist identity and discovery, while popularity timelines, album milestones and top-track listings are served from a curated local dataset, `timeline_fallback.json`. The app still *attempts* the live calls (`sp.artist()` for follower totals and `sp.artist_top_tracks()` for exact track names and URLs) and transparently overlays that real data whenever the call succeeds, falling back to the local dataset on any failure — so the same code path works correctly on both restricted and fully-privileged credentials.

### HTTP endpoints used

| Endpoint | `spotipy` call | Purpose | Status on Development Mode |
|---|---|---|---|
| `GET /search` | `sp.search(q=..., type='artist', limit=10)` | Live artist search / autocomplete | Works |
| `GET /artists/{id}` | `sp.artist(artist_id)` | Real follower total | `followers` field absent |
| `GET /artists/{id}/top-tracks` | `sp.artist_top_tracks(artist_id)` | Exact track names + Spotify URLs | `403 Forbidden` |

> **Note on the API restriction:** the two "restricted" rows above were verified directly against this project's own credentials during development. Both calls are fully implemented and will start returning live data automatically if the app is granted Extended Quota Mode — no code change required.

---

## 3. API Key Instructions & Security

### Obtaining credentials

1. Sign in at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
2. Click **Create App**. Any name and description are fine (e.g. "Timeline Explorer" / "CMU 15-113 HW3"). For **Redirect URI** enter `http://localhost` — this app never uses it, but the form requires a value.
3. Open the new app's **Settings** and copy the **Client ID** and **Client Secret**.

### Configuring them safely

Credentials are read **only** from environment variables, loaded from a local `.env` file by `python-dotenv`. Copy the provided template and fill in your own values:

```bash
cp .env.example .env
```

```text
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
```

### Security guarantees

- **No key is ever hardcoded.** `main.py` reads credentials exclusively via `os.getenv('SPOTIPY_CLIENT_ID')` / `os.getenv('SPOTIPY_CLIENT_SECRET')`.
- **`.env` is git-ignored** by the committed `.gitignore`, alongside `__pycache__/`, `*.cache`, `.vscode/` and `.DS_Store`. Only the placeholder `.env.example` is tracked.
- **No secrets are printed.** Error messages report *that* authentication failed, never the credential values.
- **Token cache is in-memory only.** The app uses `spotipy.cache_handler.MemoryCacheHandler()` instead of spotipy's default on-disk `.cache` file, so no token is ever written to disk (and a stale cached token can never mask a genuine credential failure on a later run).
- **Least privilege.** The Client Credentials flow requests no OAuth scopes and accesses no user account data.

### Running without any API keys

**The app is built to run gracefully with no credentials at all.** If `.env` is missing, empty, or contains invalid keys, startup does **not** fail: `SpotifyManager` catches the error, switches to `offline_mode`, and the dashboard displays a red **"OFFLINE MODE"** banner. Search then falls back to substring matching against the local curated dataset, and all 13 curated artists remain fully explorable — charts, rankings, top tracks and comparison pinning all work identically. This means the project can be graded end-to-end without the grader needing to obtain Spotify credentials.

---

## 4. Installation & Execution

### Prerequisites

- Python **3.10 or newer** (developed and verified on 3.14.7)

### Step 1 — Install dependencies

```bash
pip install spotipy python-dotenv pygame-ce
```

| Package | Purpose |
|---|---|
| `pygame-ce` | Rendering, full-screen display, event handling, anti-aliased drawing |
| `spotipy` | Spotify Web API client wrapper |
| `python-dotenv` | Loads credentials from the local `.env` file |

> Install `pygame-ce` (Community Edition), **not** the legacy `pygame` package — the code uses pygame-ce APIs such as `pygame.MOUSEWHEEL` and `pygame.gfxdraw`.

### Step 2 — (Optional) Add API credentials

Follow [section 3](#3-api-key-instructions--security). Skip this step to run in offline/fallback mode.

### Step 3 — Launch

```bash
python main.py
```

### Step 4 — (Optional) Verify the source compiles

```bash
python -m py_compile main.py
```

---

## 5. How To Use

| Action | Control |
|---|---|
| See 10 recommended artists | Click the search bar while it is empty |
| Search for any artist | Type a name, press `Enter` |
| Clear the query | Click the **✕** inside the search bar |
| Delete quickly | Hold `Backspace` (key repeat enabled) |
| Load an artist | Click a row in the results dropdown |
| Pin for comparison | Press `P`, or click the **Pin** button on the details card |
| Focus a pinned artist | Click its chip in the Pinned Artists panel |
| Unpin | Click the **✕** on its chip |
| Inspect a milestone | Hover a node on the chart |
| Scroll the song list | Mouse wheel over the details card tracklist |
| Open a track / artist on Spotify | Click the **↗** arrow |
| Toggle full screen | `F11` |
| Exit | `Esc` |

### Reading the chart

The vertical axis is **Global Peak Rank**, using standard chart convention where **#1 is the best and sits at the very top**; larger (worse) rank numbers descend toward the bottom. Bands are shaded:

- `#1–#20` — Global Superstar / Top Charts
- `#21–#50` — Mainstream / Major Artist
- `#51–#101` — Emerging / Niche / Early Era

---

## 6. Data Sources & Honesty About Data

### Live Spotify Web API
Artist search and discovery (`id`, `name`, `genres`, `images`), plus real follower totals and exact top-track names/URLs whenever the access tier permits.

### Curated local dataset — `timeline_fallback.json`
Real historical release data for **13 artists** across several decades and genres: Taylor Swift, Drake, Bad Bunny, The Weeknd, Michael Jackson, Daft Punk, BTS, Shakira, Karol G, Rosalía, Travis Scott, Beyoncé, and Kendrick Lamar. Each entry holds an album/release timeline with popularity scores, two notable tracks per album, and a ranked artist-level top-tracks list.

### Artists with no available data
Nothing is fabricated. If an artist is found by live search but has no curated entry and the API returns nothing usable, the app renders an explicit **"Sin acceso a información"** state on both the chart and the details card. No dummy chart points, no invented song titles, and no synthesized follower counts are ever displayed.

---

## 7. Architecture

```text
SpotifyManager          Live API access (search; follower + top-track attempts)
build_no_data_payload() Explicit empty payload for artists with no data
DataManager             Orchestrates live search -> curated lookup -> normalization
  _normalize_artist_data()  Single choke point guaranteeing UI-safe shapes
  _overlay_live_metrics()   Overlays real live values when available
SearchBar               Search input, focus glow, clear (X) button
SearchResultsDropdown   Search results + default recommendations list
PinnedArtistsPanel      Up to 6 comparison chips, each a unique color
TrajectoryChart         Multi-series rank chart, zones, legend, tooltips
ArtistStatsCard         Metrics, profile link, scrollable tracklist
DashboardApp            Responsive layout, event loop, render order
```

### Reliability & error handling

- Every event handler (`MOUSEBUTTONDOWN`, `MOUSEMOTION`, `MOUSEBUTTONUP`, `MOUSEWHEEL`, `KEYDOWN`, `VIDEORESIZE`) is individually wrapped in `try/except` and logs to the console, so a single fault can never crash the main loop.
- All dictionary reads use `.get()` with defaults to prevent `KeyError` on changed API payloads.
- Every value passed to `font.render()` goes through a `safe_str()` helper to prevent `TypeError`.
- API failures (bad credentials, no network, removed endpoints, rate limits) route into offline/fallback mode rather than surfacing as errors.

---

## 8. Project Files

```text
Spotify timeline picks/
├── main.py                  # Complete pygame-ce application
├── timeline_fallback.json   # Curated historical dataset (13 artists)
├── .env.example             # Credential template (safe to commit)
├── .env                     # Your real keys (git-ignored, never committed)
├── .gitignore               # Excludes .env, __pycache__/, *.cache, .vscode/, .DS_Store
├── README.md                # This document
└── prompt_log.md            # AI tools and prompts used
```

---

## 9. Troubleshooting

**Red "OFFLINE MODE" banner although I have internet**
Check that `.env` exists (not just `.env.example`) and holds real, non-placeholder values. This is a normal, fully-functional mode — all 13 curated artists still work.

**An artist shows "Sin acceso a información"**
Expected for any artist outside the curated dataset: because the Developer Mode tier no longer exposes popularity or top-track data, there is genuinely nothing to plot, and the app says so instead of inventing numbers. Click the empty search bar to jump to a curated artist.

**`ModuleNotFoundError`**
```bash
pip install spotipy python-dotenv pygame-ce
```

**Full screen misbehaves**
The app automatically falls back to a resizable 1440×900 window if `pygame.FULLSCREEN` cannot initialize. `F11` toggles at any time.

---

## 10. HW3 Requirement Checklist

| Requirement | Where it is satisfied |
|---|---|
| Integrates a real external API | Spotify Web API via `spotipy` (section 2) |
| Explains how the API is called + parameters | `sp.search(q, type, limit)` (section 2) |
| Describes returned data types/formats | Nested JSON dicts/lists (section 2) |
| API key acquisition documented | Spotify Developer Dashboard steps (section 3) |
| Keys kept out of source control | `os.getenv` + `.env` + `.gitignore` (section 3) |
| Install + run instructions | `pip install ...` / `python main.py` (section 4) |
| Graceful handling of API failure | `offline_mode` + curated fallback (sections 3, 6) |
| Robust error handling | Per-handler `try/except`, `.get()`, `safe_str()` (section 7) |
| Interactive user experience | Search, pin/compare, hover, scroll, links (section 5) |
| AI usage disclosed | `prompt_log.md` |

---

**Course:** CMU 15-113 — Effective Coding with AI
**Assignment:** HW3 — Explore an API
**Data sources:** Spotify Web API (live search) + curated historical release research
