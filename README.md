# Global Artist Timeline & Peak Explorer

**CMU 15-113 - HW3: Explore an API**

Global Artist Timeline & Peak Explorer is an interactive Pygame dashboard for exploring artist career trajectories. Users can search Spotify artists, view historical popularity charts, inspect albums and tracks, and compare up to six artists. The project uses the Spotify Web API for live artist discovery and a curated local dataset for historical timelines.

## API

The app uses `spotipy` with Spotify's OAuth 2.0 Client Credentials flow. Artist searches call `sp.search(q=query, type='artist', limit=10)` and parse the JSON response as nested Python dictionaries and lists, including artist IDs, names, genres, and images. Spotify search is live and was tested online with 134 unique artist results from multiple queries. Historical charts and curated track lists come from `timeline_fallback.json` because the current Development Mode access tier may restrict follower, popularity, and top-track fields.

The local dataset contains complete historical data for 13 artists: Taylor Swift, Drake, Bad Bunny, The Weeknd, Michael Jackson, Daft Punk, BTS, Shakira, Karol G, Rosalía, Travis Scott, Beyoncé, and Kendrick Lamar. Artists found by Spotify but missing from the local dataset show `Information Unavailable` rather than invented historical values.

### Endpoints

| Endpoint | Spotipy call | Purpose |
|---|---|---|
| `GET /search` | `sp.search(...)` | Live artist search |
| `GET /artists/{id}` | `sp.artist(...)` | Attempts live follower data |
| `GET /artists/{id}/top-tracks` | `sp.artist_top_tracks(...)` | Attempts live track data; may return `403` in Development Mode |

API failures are caught and the app switches to offline mode using the local dataset.

## Security and setup

Never commit Spotify credentials. The app reads them only from environment variables, and `.env` is excluded by `.gitignore`.

1. Copy `.env.example` to `.env`.
2. Add your own Spotify Developer Dashboard credentials:

```text
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
```

The placeholder values above are examples only. The application also works without credentials in offline mode.

## Installation and launch

Requirements: Python 3.10+.

```bash
pip install spotipy python-dotenv pygame-ce
python main.py
```

To verify compilation:

```bash
python -m py_compile main.py
```

## Controls

- Click the search bar and type an artist name; press `Enter`.
- Click a result to load its timeline.
- Press `P` or use the Pin button to compare artists.
- Hover over chart points for album details.
- Scroll the track list with the mouse wheel.
- Click Spotify arrows to open tracks or artist pages.
- Press `F11` to toggle fullscreen and `Esc` to exit.

## Data and limitations

The historical values are curated release and popularity data stored in `timeline_fallback.json`; they are not presented as a complete live Spotify history. Live Spotify data is overlaid only when the access tier provides it. Missing data is reported honestly instead of being fabricated. The application handles missing credentials, invalid searches, API errors, and offline use without crashing.

## Project files

- `main.py` - Pygame application and Spotify integration.
- `timeline_fallback.json` - Curated historical data for 13 artists.
- `.env.example` - Safe credential template.
- `.gitignore` - Prevents credentials and generated files from being committed.
- `prompt_log.md` - AI tools, prompts, and development reflection.

## HW3 checklist

- Real external API integration: Spotify Web API.
- Interactive visualization: search, charts, comparison, tooltips, scrolling, and links.
- Error handling and offline fallback.
- Credential setup and security documentation.
- AI use disclosed in `prompt_log.md`.
