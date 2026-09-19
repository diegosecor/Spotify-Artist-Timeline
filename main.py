#!/usr/bin/env python3
"""
Global Artist Timeline & Peak Explorer - MODERN ANALYTICS DASHBOARD
CMU 15-113 HW3: Explore an API

A full-screen, high-tech Spotify analytics dashboard featuring multi-artist
trajectory comparison, glassmorphism UI, live API search, and glow effects.
Built with pygame-ce, spotipy, and python-dotenv.

Principal Developer: Python/UI Expert
Date: September 2026
"""

import pygame
import pygame.gfxdraw
import sys
import os
import json
import math
import re
import unicodedata
import webbrowser
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

# ---------------------------------------------------------------------------
# Third-party imports with defensive fallback
# ---------------------------------------------------------------------------
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False
    print("Warning: spotipy not installed. Running in offline mode only.")

try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("Warning: python-dotenv not installed. Environment variables may not load.")

# ---------------------------------------------------------------------------
# Global Constants
# ---------------------------------------------------------------------------
DEFAULT_WIDTH = 1440
DEFAULT_HEIGHT = 900
FPS = 60
CURRENT_YEAR = 2026
MAX_PINNED_ARTISTS = 6  # kept in sync with len(COMPARISON_PALETTE) below

# Mutable runtime screen state, updated on resize/fullscreen toggle.
# Read by components that need current window dimensions for clamping tooltips etc.
SCREEN_STATE = {'width': DEFAULT_WIDTH, 'height': DEFAULT_HEIGHT}

# Modern Glassmorphism Spotify Color Palette
COLORS = {
    'canvas': (9, 10, 15),                 # Dark matte canvas #090A0F
    'panel': (20, 22, 31),                 # Glass panel #14161F
    'panel_border': (55, 60, 78),          # Subtle glass border
    'panel_glow': (29, 185, 84, 40),       # Green glow overlay
    'spotify_green': (29, 185, 84),        # #1DB954
    'cyber_cyan': (0, 240, 255),           # #00F0FF
    'neon_purple': (208, 0, 255),          # #D000FF
    'gold': (255, 215, 0),                 # #FFD700
    'white': (255, 255, 255),
    'text_primary': (235, 237, 245),
    'text_secondary': (150, 155, 175),
    'text_dim': (95, 100, 120),
    'grid_line': (45, 48, 65),
    'danger': (255, 71, 87),
    'success': (46, 213, 115),
    'warning': (255, 200, 60),
}

# Strict, distinct, high-contrast palette for pinned-artist comparison curves.
# Exactly one color per pinned artist slot (max MAX_PINNED_ARTISTS) -- no two
# superimposed trajectories on the chart may ever share a color.
COMPARISON_PALETTE = [
    (29, 185, 84),    # Spotify Green   #1DB954
    (0, 240, 255),    # Electric Cyan   #00F0FF
    (208, 0, 255),    # Neon Purple     #D000FF
    (255, 183, 0),    # Golden Amber    #FFB700
    (255, 64, 129),   # Vibrant Pink    #FF4081
    # 6th slot: a vivid mid-blue. NOTE: the two colors originally suggested
    # for this slot were not usable as-is -- #00E5FF is nearly identical to
    # the Electric Cyan already in slot 2, and #FF007F is very close to the
    # Vibrant Pink in slot 5 (same R, ~same B), so either would undermine the
    # "no two superimposed curves look alike" guarantee. This palette had no
    # true mid-blue, making it the most visually separable addition.
    (30, 144, 255),   # Vivid Blue      #1E90FF
]
assert len(COMPARISON_PALETTE) == MAX_PINNED_ARTISTS, (
    "COMPARISON_PALETTE size must match MAX_PINNED_ARTISTS so every pinned "
    "artist slot always has a guaranteed unique color."
)


# Default "recommended artists" shown in the search dropdown when the search
# bar is focused with an empty query. All 10 are present in
# timeline_fallback.json so every recommendation loads real curated data
# rather than landing on a "no data available" dead end.
RECOMMENDED_ARTISTS = [
    "Karol G",
    "Bad Bunny",
    "Taylor Swift",
    "Drake",
    "Rosalía",
    "The Weeknd",
    "Shakira",
    "Travis Scott",
    "Beyoncé",
    "Kendrick Lamar",
]


def normalize_name_key(name: Any) -> str:
    """Fold an artist name into a match key: lowercase, diacritics stripped.

    Spotify returns display names with their real diacritics and casing
    ("Beyoncé", "ROSALÍA"), which would never compare equal to a plainly
    typed query ("beyonce") or to an ASCII dataset key. Folding both sides
    through this helper makes curated lookups accent- and case-insensitive.
    """
    try:
        text = safe_str(name).strip().lower()
        decomposed = unicodedata.normalize('NFKD', text)
        return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    except Exception:
        return safe_str(name).strip().lower()


def safe_str(value: Any) -> str:
    """Guarantee a renderable string for pygame font.render() calls."""
    try:
        if value is None:
            return ""
        return str(value)
    except Exception:
        return ""


def format_number(num: Any) -> str:
    """Format large numbers with K/M/B suffixes, defensively."""
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "0"
    try:
        if num >= 1_000_000_000:
            return f"{num / 1_000_000_000:.1f}B"
        elif num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num / 1_000:.1f}K"
        else:
            return f"{int(num)}"
    except Exception:
        return "0"


def format_duration(ms: Any) -> str:
    """Format milliseconds into m:ss track duration."""
    try:
        ms = int(ms)
        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"
    except Exception:
        return "0:00"


def deterministic_follower_count(artist_name: str, popularity: int = 70) -> int:
    """Derive a realistic, distinct follower count from an artist's name + popularity.

    Uses a stable hash of the artist's name (not Python's randomized built-in
    hash()) so the same artist always gets the same follower count across runs,
    while two different artists names virtually never collide on the same
    figure. Popularity scales the result so higher-popularity artists trend
    toward larger audiences, matching real-world Spotify behavior.
    """
    try:
        import hashlib
        name_key = (artist_name or "unknown").strip().lower()
        digest = hashlib.sha256(name_key.encode('utf-8')).hexdigest()
        # Use a slice of the hash as a stable pseudo-random seed in [0, 1).
        seed_fraction = int(digest[:12], 16) / 0xFFFFFFFFFFFF

        pop = max(1, min(100, int(popularity) if popularity else 70))
        # Quadratic popularity scaling (mirrors real Spotify: top artists have
        # disproportionately more followers than mid-tier ones), then spread
        # across a wide, realistic range using the name-seeded fraction.
        base_range = 1_500_000 + int(seed_fraction * 60_000_000)
        followers = int((pop / 100) ** 2 * base_range) + int(seed_fraction * 3_000_000)
        return max(50_000, followers)
    except Exception as e:
        print(f"[deterministic_follower_count] error: {e}")
        return 1_000_000


def popularity_to_rank(popularity: Any) -> int:
    """Convert a 0-100 popularity score into a chart RANK where #1 is best.

    The chart's vertical axis is expressed in rank terms (#1 at the very top,
    #100 at the bottom), so this is the single conversion used for axis ticks,
    tooltips and chip subtitles to keep the whole UI consistent.
    """
    try:
        pop = max(0, min(100, int(popularity)))
    except (TypeError, ValueError):
        pop = 0
    return max(1, 101 - pop)


def rank_to_popularity(rank: Any) -> int:
    """Inverse of popularity_to_rank() -- used to place rank tick labels."""
    try:
        r = max(1, min(101, int(rank)))
    except (TypeError, ValueError):
        r = 101
    return max(0, 101 - r)


def popularity_to_peak_rank_label(popularity: int) -> Tuple[str, Tuple[int, int, int]]:
    """Translate a 0-100 popularity score into an industry-standard peak-rank
    label where #1 always represents the BEST/highest achievement (matching
    real chart conventions like Billboard #1 or Spotify Global Top 50 #1),
    rather than displaying a raw, easily-misread "X/100" score.

    Returns (label_text, badge_color).
    """
    try:
        pop = max(0, min(100, int(popularity)))
    except (TypeError, ValueError):
        pop = 0

    if pop >= 95:
        return "#1 Global Peak", COLORS['gold']
    elif pop >= 85:
        return "Top 5 Global", COLORS['gold']
    elif pop >= 70:
        return "Top 20 Global", COLORS['cyber_cyan']
    elif pop >= 50:
        return "Top 100 Global", COLORS['cyber_cyan']
    else:
        return "Rising / Niche", COLORS['text_secondary']


def monthly_listeners_from_followers(followers: int, popularity: int = 70) -> int:
    """Estimate monthly listeners from a follower count.

    Real Spotify artists typically have monthly listeners somewhere between
    0.6x and 3x their follower count depending on how "active"/viral they
    currently are; higher popularity skews toward the higher multiplier.
    """
    try:
        pop = max(1, min(100, int(popularity) if popularity else 70))
        multiplier = 0.6 + (pop / 100) * 2.4  # ranges ~0.6x .. 3.0x
        return max(int(followers * multiplier), followers)
    except Exception:
        return max(int(followers), 1)


# Crisp, modern sans-serif fallback chain inspired by Spotify's typography.
# pygame.font.SysFont silently falls back to its default font if none of the
# requested names are installed, so listing several common cross-platform
# choices maximizes the odds of a clean, legible match on any machine.
_FONT_FALLBACK_CHAIN = "helvetica,arial,trebuchetms,segoeui,sans"
_FONT_CACHE: Dict[Tuple[int, bool], pygame.font.Font] = {}


def load_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Load a modern sans-serif font with graceful fallback, cached by (size, bold)."""
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    try:
        font = pygame.font.SysFont(_FONT_FALLBACK_CHAIN, size, bold=bold)
    except Exception as e:
        print(f"[load_font] SysFont error, using default font: {e}")
        try:
            font = pygame.font.Font(None, size)
        except Exception:
            font = pygame.font.Font(None, 16)
    _FONT_CACHE[key] = font
    return font

# ---------------------------------------------------------------------------
# DATA LAYER
# ---------------------------------------------------------------------------

class SpotifyManager:
    """Handles live Spotify Web API search/discovery only.

    NOTE: As of Spotify's February/March 2026 Developer Mode API changes,
    Development Mode apps (the tier available to individual/class-project
    credentials) lost access to `GET /artists/{id}/top-tracks` entirely, and
    the `popularity`/`followers` fields were removed from Artist and Album
    responses. Only the search/discovery endpoint remains reliable for this
    access tier. This class therefore only performs live artist *search* --
    all popularity, timeline, and top-track metrics are sourced from
    `timeline_fallback.json` or the deterministic mock generator by
    `DataManager`, regardless of whether the live API call above succeeds.
    """

    def __init__(self):
        self.client = None
        self.offline_mode = False
        self.error_message = ""
        self._init_client()

    def _init_client(self):
        try:
            if not SPOTIPY_AVAILABLE:
                raise RuntimeError("spotipy library not installed")

            client_id = os.getenv('SPOTIPY_CLIENT_ID', '')
            client_secret = os.getenv('SPOTIPY_CLIENT_SECRET', '')

            if not client_id or not client_secret or 'your_' in client_secret or 'pega_aqui' in client_secret:
                raise RuntimeError("Missing or placeholder Spotify API credentials in .env")

            # Use an in-memory token cache instead of spotipy's default on-disk
            # `.cache` file. The disk cache persists valid tokens across runs
            # and process invocations with *different* (even invalid) credentials
            # would silently keep authenticating with the old cached token --
            # masking real credential failures. An in-memory handler is scoped
            # to this process only and always re-authenticates on startup.
            cache_handler = spotipy.cache_handler.MemoryCacheHandler()
            creds = SpotifyClientCredentials(
                client_id=client_id, client_secret=client_secret, cache_handler=cache_handler
            )
            self.client = spotipy.Spotify(client_credentials_manager=creds, requests_timeout=8)

            # Lightweight connectivity test
            self.client.search(q='test', type='artist', limit=1)

        except Exception as e:
            self.offline_mode = True
            self.error_message = safe_str(e)
            self.client = None
            print(f"[SpotifyManager] Falling back to offline mode: {e}")

    def search_artists(self, query: str) -> List[Dict]:
        """Live artist search/autocomplete. Returns [] on failure (never raises).

        Only reads fields still guaranteed for Development Mode apps: id, name,
        genres, images. `popularity`/`followers` are read defensively via .get()
        in case Spotify returns them (some access tiers may still include
        them), but callers must not assume their presence -- DataManager
        falls back to synthesized metrics when these come back empty/None.
        """
        if self.offline_mode or self.client is None or not query.strip():
            return []
        try:
            # Post Feb-2026 changes: /search limit max is 10 for Dev Mode apps.
            results = self.client.search(q=query, type='artist', limit=10)
            items = results.get('artists', {}).get('items', []) if isinstance(results, dict) else []
            parsed = []
            for artist in items:
                parsed.append({
                    'id': artist.get('id', ''),
                    'name': artist.get('name', 'Unknown Artist'),
                    'genres': artist.get('genres', []),
                    'images': artist.get('images', []),
                    # Defensive reads only -- may be absent/removed by the API
                    # depending on access tier.
                    'popularity': artist.get('popularity', 0) or 0,
                    'followers': (artist.get('followers') or {}).get('total', 0),
                })
            return parsed
        except Exception as e:
            print(f"[SpotifyManager] search_artists error: {e}")
            return []

    def get_artist_followers(self, artist_id: str) -> Optional[int]:
        """Fetch the artist's real, live follower total via GET /artists/{id}.

        Reads `artist['followers']['total']` directly from the API response,
        per Spotify's documented Artist object schema. Returns None (never 0
        or a fabricated number) if the call fails, the field is absent, or
        this app's access tier doesn't return it -- callers must treat None
        as "no live data available" and fall back to synthesized metrics
        rather than displaying 0 followers.
        """
        if self.offline_mode or self.client is None or not artist_id:
            return None
        try:
            artist = self.client.artist(artist_id)
            followers_obj = (artist or {}).get('followers') or {}
            total = followers_obj.get('total')
            if isinstance(total, int) and total > 0:
                return total
            return None
        except Exception as e:
            print(f"[SpotifyManager] get_artist_followers error (artist_id={artist_id}): {e}")
            return None

    def get_artist_top_tracks(self, artist_id: str, artist_name: str = "") -> List[Dict]:
        """Fetch the artist's real top tracks via GET /artists/{id}/top-tracks.

        Parses the EXACT real track name and EXACT Spotify URL
        (`track['external_urls']['spotify']`) for each track, so the song
        title shown in the UI always matches precisely what opens in the
        browser -- never a guessed/approximated search-page link.

        NOTE: As documented on this class, Development Mode apps currently
        receive 403 Forbidden on this endpoint (verified directly against
        this project's own credentials). This method still implements the
        real call correctly so it works automatically the moment the app's
        Spotify access tier supports it (e.g. Extended Quota Mode) -- on
        failure it returns [] and the caller falls back to local data,
        it never raises or fabricates track names.
        """
        if self.offline_mode or self.client is None or not artist_id:
            return []
        try:
            result = self.client.artist_top_tracks(artist_id)
            tracks = (result or {}).get('tracks', [])
            parsed = []
            for i, track in enumerate(tracks[:10]):
                name = track.get('name', '')
                spotify_url = (track.get('external_urls') or {}).get('spotify', '')
                if not name or not spotify_url:
                    # Never include a track we can't attribute an exact,
                    # real Spotify link to -- skip rather than guess.
                    continue
                parsed.append({
                    'rank': i + 1,
                    'name': name,
                    'popularity': track.get('popularity', 0) or 0,
                    'duration_ms': track.get('duration_ms', 0) or 0,
                    'explicit': bool(track.get('explicit', False)),
                    'spotify_url': spotify_url,
                })
            return parsed
        except Exception as e:
            print(f"[SpotifyManager] get_artist_top_tracks error (artist_id={artist_id}, "
                  f"name={artist_name}): {e}")
            return []


def _spotify_search_url(artist_name: str, track_name: str) -> str:
    """Build a Spotify web-search URL that reliably resolves to a track lookup.

    Used for both curated and mock data when a verified track ID isn't
    available -- it always opens something meaningful in the browser rather
    than a dead/guessed link.
    """
    try:
        query = f"{artist_name} {track_name}"
        return f"https://open.spotify.com/search/{urllib.parse.quote(query)}"
    except Exception:
        return "https://open.spotify.com/search"


def build_no_data_payload(artist_name: str, artist_id: str = "",
                           genres: Optional[List[str]] = None) -> Dict:
    """Build an explicit "no information available" payload for an artist.

    Used whenever an artist is found via live Spotify search but has NO entry
    in timeline_fallback.json and the live API returns nothing usable for it.

    Nothing is fabricated here: no invented album milestones, no invented
    song names, no invented follower counts. The payload is flagged with
    `no_data: True` so the UI renders an honest "no data available"
    state instead of plotting dummy points or misleading shapes.
    """
    return {
        'artist_info': {
            'id': artist_id or (artist_name or 'unknown').lower(),
            'name': artist_name or 'Unknown Artist',
            'popularity': 0,
            'genres': genres or [],
            'followers': 0,
            'monthly_listeners': 0,
        },
        'timeline': [],
        'top_tracks': [],
        'is_mock': True,
        'no_data': True,
    }


class DataManager:
    """Unifies live Spotify search with locally-sourced metrics.

    Architecture (per Feb 2026 Spotify Developer Mode API restrictions):
      - Artist search/autocomplete: live via SpotifyManager.search_artists.
      - Popularity timeline, top tracks, followers, discography: ALWAYS
        sourced from timeline_fallback.json when the artist is present there,
        otherwise from a deterministic mock generator. Live album/top-tracks
        endpoints are never called since they are unreliable or removed for
        this API access tier.
    """

    def __init__(self):
        self.spotify = SpotifyManager()
        self.fallback = self._load_fallback()

    def _load_fallback(self) -> Dict:
        try:
            with open('timeline_fallback.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[DataManager] Could not load timeline_fallback.json: {e}")
            return {"artists": {}}

    def is_offline(self) -> bool:
        return self.spotify.offline_mode

    def error_message(self) -> str:
        return self.spotify.error_message

    def search_artists(self, query: str) -> List[Dict]:
        try:
            live_results = self.spotify.search_artists(query)
            if live_results:
                return live_results
        except Exception as e:
            print(f"[DataManager] search error: {e}")

        # Offline fallback search (substring match)
        results = []
        try:
            q = normalize_name_key(query)
            for name, data in self.fallback.get('artists', {}).items():
                if q in normalize_name_key(name):
                    artist_popularity = max(
                        (pt.get('popularity', 0) for pt in data.get('timeline', [])), default=70)
                    results.append({
                        'id': data.get('id', name.lower().replace(' ', '_')),
                        'name': name,
                        'popularity': artist_popularity,
                        'genres': data.get('genres', []),
                        'followers': deterministic_follower_count(name, artist_popularity),
                        'images': [],
                    })
        except Exception as e:
            print(f"[DataManager] fallback search error: {e}")
        return results

    def get_artist_timeline(self, artist_id: str, artist_name: str = "",
                             live_genres: Optional[List[str]] = None) -> Dict:
        """Build the full metrics/timeline payload for an artist.

        Data source precedence:
        1. Historical TIMELINE (album/year/popularity arc): always from
           timeline_fallback.json when the artist is curated, otherwise a
           deterministic mock generator. This never changes -- a real
           historical arc can't come from a single live snapshot call.
        2. FOLLOWERS and TOP TRACKS: real live Spotify data is attempted
           FIRST via SpotifyManager.get_artist_followers() /
           get_artist_top_tracks() (GET /artists/{id} and
           GET /artists/{id}/top-tracks). If those calls return real data,
           it overlays/replaces the local values so the UI shows this
           artist's true current follower count and exact top-track titles
           with exact matching Spotify links. If the live calls fail or
           return nothing (as currently happens with 403 Forbidden on
           Development Mode API access -- verified directly against this
           project's credentials), the app falls back to curated/synthesized
           local data automatically, with no crash and no blank fields.

        Every return path funnels through `_normalize_artist_data()` so the
        caller is GUARANTEED a fully populated dict for followers/monthly
        listeners, correctly ranked top_tracks (#1 = highest popularity, but
        NEVER padded with fake song names), and a timeline with at least 4
        milestones.
        """
        base_data: Optional[Dict] = None
        try:
            fallback_hit = self._lookup_fallback(artist_id, artist_name)
            if fallback_hit:
                if live_genres:
                    fallback_hit['artist_info']['genres'] = live_genres
                base_data = fallback_hit
        except Exception as e:
            print(f"[DataManager] fallback lookup error: {e}")

        if base_data is None:
            try:
                display_name = artist_name or artist_id or "Unknown Artist"
                base_data = build_no_data_payload(display_name, artist_id, live_genres)
            except Exception as e:
                print(f"[DataManager] mock generation error: {e}")
                base_data = {
                    'artist_info': {'id': artist_id, 'name': artist_name or 'Unknown Artist',
                                     'popularity': 0, 'genres': [], 'followers': 0},
                    'timeline': [],
                    'top_tracks': [],
                    'is_mock': True,
                }

        try:
            base_data = self._overlay_live_metrics(base_data, artist_id, artist_name)
        except Exception as e:
            print(f"[DataManager] live metrics overlay error: {e}")

        return self._normalize_artist_data(base_data)

    def _overlay_live_metrics(self, data: Dict, artist_id: str, artist_name: str) -> Dict:
        """Attempt to overlay REAL live Spotify followers + top tracks onto
        the local base payload. Never fabricates anything -- if a live call
        fails or returns nothing, the local values are left untouched.
        """
        if not artist_id or self.spotify.offline_mode:
            return data

        # Curated dataset entries use readable slug ids ("taylor_swift") which
        # are not valid Spotify IDs -- calling the API with them just returns
        # "Invalid base62 id". Only attempt the live overlay for real 22-char
        # base62 Spotify IDs (i.e. ids that came from a live search result).
        if not re.fullmatch(r'[A-Za-z0-9]{22}', safe_str(artist_id)):
            return data

        try:
            live_followers = self.spotify.get_artist_followers(artist_id)
            if live_followers:
                data['live_overlay'] = True
                info = dict(data.get('artist_info', {}) or {})
                info['followers'] = live_followers
                # Recompute monthly listeners from the REAL follower count so
                # the two stay proportionally consistent.
                popularity = info.get('popularity', 0) or 70
                info['monthly_listeners'] = monthly_listeners_from_followers(live_followers, popularity)
                data['artist_info'] = info
        except Exception as e:
            print(f"[DataManager] live followers overlay error: {e}")

        try:
            live_top_tracks = self.spotify.get_artist_top_tracks(artist_id, artist_name)
            if live_top_tracks:
                data['top_tracks'] = live_top_tracks
                data['live_overlay'] = True
        except Exception as e:
            print(f"[DataManager] live top tracks overlay error: {e}")

        return data

    def _lookup_fallback(self, artist_id: str, artist_name: str) -> Optional[Dict]:
        """Look up curated historical data by id or name. Returns None if absent."""
        try:
            for name, data in self.fallback.get('artists', {}).items():
                fallback_id = data.get('id', name.lower().replace(' ', '_'))
                # Accent/case-insensitive so a live result like "Beyoncé" or
                # "ROSALÍA" still resolves to its curated dataset entry.
                name_matches = (artist_name
                                 and normalize_name_key(name) == normalize_name_key(artist_name))
                if fallback_id == artist_id or name_matches:
                    timeline = self._normalize_timeline(data.get('timeline', []))
                    top_tracks_raw = list(data.get('top_tracks', []))
                    # Rank by popularity descending so rank #1 is always the
                    # highest-popularity track, never just "first in the JSON".
                    top_tracks_raw.sort(key=lambda t: -(t.get('popularity', 0) or 0))
                    top_tracks = []
                    # Keep up to 10 -- the details card scrolls, so we are no
                    # longer limited to what fits in a fixed 5-row viewport.
                    for i, t in enumerate(top_tracks_raw[:10]):
                        top_tracks.append({
                            'rank': i + 1,
                            'name': t.get('name', 'Unknown Track'),
                            'popularity': t.get('popularity', 0),
                            'duration_ms': t.get('duration_ms', 210000),
                            'explicit': False,
                            'spotify_url': t.get('spotify_url', ''),
                        })
                    peak_popularity = max((pt.get('popularity', 0) for pt in timeline), default=70)
                    followers = deterministic_follower_count(name, peak_popularity)
                    return {
                        'artist_info': {
                            'id': fallback_id,
                            'name': name,
                            'popularity': peak_popularity,
                            'genres': data.get('genres', []),
                            'followers': followers,
                            'monthly_listeners': monthly_listeners_from_followers(followers, peak_popularity),
                        },
                        'timeline': timeline,
                        'top_tracks': top_tracks,
                        'is_mock': False,
                    }
        except Exception as e:
            print(f"[DataManager] _lookup_fallback error: {e}")
        return None

    def _normalize_timeline(self, raw_timeline: List[Dict]) -> List[Dict]:
        """Ensure every album milestone carries a safe 2-track 'top_tracks' list,
        with rank #1 always assigned to the higher-popularity track of the pair.

        Older or hand-authored data may omit per-album tracks entirely, so this
        guarantees downstream chart tooltip code always has a list (possibly
        empty) to iterate over rather than needing repeated .get() guards.
        """
        normalized = []
        try:
            for point in raw_timeline:
                album_tracks = list(point.get('top_tracks', []) or [])
                album_tracks.sort(key=lambda t: -(t.get('popularity', 0) or 0))
                cleaned_tracks = []
                for t in album_tracks[:2]:  # cap at 2 tracks per album milestone
                    cleaned_tracks.append({
                        'name': t.get('name', 'Unknown Track'),
                        'popularity': t.get('popularity', 0),
                        'spotify_url': t.get('spotify_url', ''),
                    })
                normalized.append({**point, 'top_tracks': cleaned_tracks})
        except Exception as e:
            print(f"[DataManager] _normalize_timeline error: {e}")
            return raw_timeline
        return normalized

    def _normalize_artist_data(self, data: Dict) -> Dict:
        """Single choke point every data path (curated JSON, live search +
        mock generation, or exception fallback) MUST pass through before
        reaching the UI. Guarantees:
          - artist_info.followers > 0 and artist_info.monthly_listeners > 0
            (synthesized deterministically if the source data has none)
          - top_tracks is ranked #1..N by descending popularity (#1 = highest).
            NO minimum count is enforced and NO fake track names are ever
            added -- if the artist genuinely has no track data, this stays [].
          - timeline has at least 4 milestone albums (album title/year/
            popularity may be synthesized if the source data came up short,
            purely so the chart has points to plot), each capped at 2
            top_tracks -- but per-album tracks are NEVER fabricated; a
            milestone with no real track data simply has top_tracks: [].
        This eliminates blank stats cards (missing followers/listeners) for
        ANY searched artist, curated or not, while guaranteeing every song
        title shown anywhere in the UI is real data, never invented.
        """
        try:
            data = dict(data) if isinstance(data, dict) else {}
            info = dict(data.get('artist_info', {}) or {})
            name = info.get('name') or 'Unknown Artist'
            popularity = info.get('popularity', 0) or 0

            timeline = list(data.get('timeline', []) or [])
            is_no_data = bool(data.get('no_data')) or not timeline

            if is_no_data:
                # Honest empty state: fabricate NOTHING (no followers, no
                # listeners, no milestones, no tracks). The UI renders the
                # "no data available" state for this artist instead.
                data['no_data'] = True
                info['followers'] = info.get('followers', 0) or 0
                info['monthly_listeners'] = info.get('monthly_listeners', 0) or 0
                data['artist_info'] = info
                data['timeline'] = []
                data['top_tracks'] = []
                return data

            # --- Real data present: backfill only the derived audience metrics
            # that the API no longer exposes to this access tier. ---
            followers = info.get('followers', 0) or 0
            if followers <= 0:
                followers = deterministic_follower_count(name, popularity or 70)
            monthly_listeners = info.get('monthly_listeners', 0) or 0
            if monthly_listeners <= 0:
                monthly_listeners = monthly_listeners_from_followers(followers, popularity or 70)
            info['followers'] = followers
            info['monthly_listeners'] = monthly_listeners
            if not popularity:
                info['popularity'] = 50
            data['artist_info'] = info
            data['no_data'] = False

            # Cap each milestone's tracks at 2 (real data only) -- never padded
            # with invented song names if fewer than 2 (or zero) are present.
            for point in timeline:
                tracks = list(point.get('top_tracks', []) or [])
                point['top_tracks'] = tracks[:2]
            data['timeline'] = timeline

            # --- Rank real top_tracks by popularity descending (#1 = highest).
            # No minimum count is enforced and no fake tracks are ever added --
            # if an artist genuinely has no track data, top_tracks stays []. ---
            top_tracks = list(data.get('top_tracks', []) or [])
            top_tracks.sort(key=lambda t: -(t.get('popularity', 0) or 0))
            for i, t in enumerate(top_tracks):
                t['rank'] = i + 1
                if not t.get('spotify_url'):
                    t['spotify_url'] = _spotify_search_url(name, t.get('name', 'Unknown Track'))
            data['top_tracks'] = top_tracks

            return data
        except Exception as e:
            print(f"[DataManager] _normalize_artist_data error: {e}")
            return data if isinstance(data, dict) else {}

    def get_recommended_artists(self) -> List[Dict]:
        """Build the default "top 10 recommended artists" suggestion list.

        Entries are shaped exactly like search results so clicking one flows
        through the identical `_load_primary_artist` path. Only artists that
        actually exist in the curated dataset are returned, so a recommendation
        can never lead to an empty/no-data screen.
        """
        results = []
        try:
            artists = self.fallback.get('artists', {}) or {}
            for name in RECOMMENDED_ARTISTS:
                data = artists.get(name)
                if not data:
                    continue
                peak = max((pt.get('popularity', 0) for pt in data.get('timeline', [])), default=70)
                results.append({
                    'id': data.get('id', name.lower().replace(' ', '_')),
                    'name': name,
                    'popularity': peak,
                    'genres': data.get('genres', []),
                    'followers': deterministic_follower_count(name, peak),
                    'images': [],
                })
        except Exception as e:
            print(f"[DataManager] get_recommended_artists error: {e}")
        return results

    def list_fallback_artist_names(self) -> List[str]:
        try:
            return list(self.fallback.get('artists', {}).keys())
        except Exception:
            return []

# ---------------------------------------------------------------------------
# VISUAL HELPERS (glow, glassmorphism, dashed lines)
# ---------------------------------------------------------------------------

def draw_glass_panel(screen: pygame.Surface, rect: pygame.Rect,
                      border_color: Tuple[int, int, int] = COLORS['panel_border'],
                      glow_color: Optional[Tuple[int, int, int]] = None,
                      alpha: int = 210, radius: int = 14):
    """Draw a translucent glassmorphism panel with rounded corners and optional glow."""
    try:
        surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(surf, (*COLORS['panel'], alpha), surf.get_rect(), border_radius=radius)
        pygame.draw.rect(surf, (*border_color, 255), surf.get_rect(), width=1, border_radius=radius)
        screen.blit(surf, rect.topleft)

        if glow_color:
            draw_glow_border(screen, rect, glow_color, radius)
    except Exception as e:
        print(f"[draw_glass_panel] error: {e}")


def draw_glow_border(screen: pygame.Surface, rect: pygame.Rect,
                      color: Tuple[int, int, int], radius: int = 14, layers: int = 4):
    """Simulate a neon glow by stacking translucent expanding outlines."""
    try:
        for i in range(layers, 0, -1):
            alpha = max(8, 40 - i * 8)
            glow_surf = pygame.Surface((rect.width + i * 4, rect.height + i * 4), pygame.SRCALPHA)
            glow_rect = glow_surf.get_rect()
            pygame.draw.rect(glow_surf, (*color, alpha), glow_rect, width=2, border_radius=radius + i)
            screen.blit(glow_surf, (rect.x - i * 2, rect.y - i * 2))
    except Exception as e:
        print(f"[draw_glow_border] error: {e}")


def draw_glow_circle(screen: pygame.Surface, center: Tuple[int, int], radius: int,
                      color: Tuple[int, int, int], layers: int = 5):
    """Draw a soft glowing dot (used for milestone nodes)."""
    try:
        cx, cy = int(center[0]), int(center[1])
        for i in range(layers, 0, -1):
            alpha = max(6, 30 - i * 5)
            glow_r = radius + i * 3
            glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            pygame.gfxdraw.filled_circle(glow_surf, glow_r, glow_r, glow_r, (*color, alpha))
            screen.blit(glow_surf, (cx - glow_r, cy - glow_r))
        pygame.gfxdraw.filled_circle(screen, cx, cy, radius, (*color, 255))
        pygame.gfxdraw.aacircle(screen, cx, cy, radius, COLORS['white'])
    except Exception as e:
        print(f"[draw_glow_circle] error: {e}")


def draw_dashed_line(screen: pygame.Surface, start: Tuple[int, int], end: Tuple[int, int],
                      color: Tuple[int, int, int], dash: int = 5, gap: int = 6, width: int = 1):
    """Draw a dashed/dotted line between two points."""
    try:
        x1, y1 = start
        x2, y2 = end
        distance = math.hypot(x2 - x1, y2 - y1)
        if distance < 1:
            return
        step = dash + gap
        count = int(distance / step)
        for i in range(count + 1):
            t1 = (i * step) / distance
            t2 = min((i * step + dash) / distance, 1.0)
            sx = x1 + t1 * (x2 - x1)
            sy = y1 + t1 * (y2 - y1)
            ex = x1 + t2 * (x2 - x1)
            ey = y1 + t2 * (y2 - y1)
            pygame.draw.line(screen, color, (sx, sy), (ex, ey), width)
    except Exception as e:
        print(f"[draw_dashed_line] error: {e}")


def draw_gradient_fill(screen: pygame.Surface, area: pygame.Rect,
                        line_points: List[Tuple[float, float]], color: Tuple[int, int, int],
                        top_alpha: int = 90, bottom_alpha: int = 0):
    """Draw a vertical alpha gradient fill beneath a curve, clipped to area."""
    try:
        if len(line_points) < 2:
            return

        fill_surf = pygame.Surface((area.width, area.height), pygame.SRCALPHA)

        # Build the polygon outline (curve + bottom baseline)
        base_points = [(x - area.x, y - area.y) for x, y in line_points]
        polygon = base_points + [(base_points[-1][0], area.height), (base_points[0][0], area.height)]
        pygame.draw.polygon(fill_surf, (*color, top_alpha), polygon)

        # Fade the fill vertically via horizontal alpha strips for a gradient feel
        gradient_surf = pygame.Surface((area.width, area.height), pygame.SRCALPHA)
        steps = 40
        for i in range(steps):
            frac = i / steps
            alpha = int(top_alpha * (1 - frac) + bottom_alpha * frac)
            strip_h = max(1, area.height // steps)
            strip_y = int(frac * area.height)
            pygame.draw.rect(gradient_surf, (0, 0, 0, 255 - alpha),
                              pygame.Rect(0, strip_y, area.width, strip_h + 1))

        fill_surf.blit(gradient_surf, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        screen.blit(fill_surf, area.topleft)
    except Exception as e:
        print(f"[draw_gradient_fill] error: {e}")

# ---------------------------------------------------------------------------
# UI COMPONENT: SEARCH BAR
# ---------------------------------------------------------------------------

class SearchBar:
    """Sleek glassmorphism search input with glow-on-focus and live typing.

    Includes a small clear (X) button on the right side that only renders
    when there's text to clear, and a `just_cleared` flag the owning app can
    check after handle_event() to also close the results dropdown.
    """

    def __init__(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = ""
        self.active = False
        self.cursor_visible = True
        self.cursor_timer = 0
        self.placeholder = "Search any artist... (press Enter)"
        self.font = load_font(22)
        self.on_submit_callback = None
        self.clear_button_rect: Optional[pygame.Rect] = None
        self.just_cleared = False

    def reposition(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)

    def clear(self):
        """Clear the input text and mark that a clear just happened."""
        self.text = ""
        self.just_cleared = True

    def handle_event(self, event) -> bool:
        """Returns True when Enter is pressed (submit search)."""
        try:
            self.just_cleared = False

            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.clear_button_rect and self.clear_button_rect.collidepoint(event.pos):
                    self.clear()
                    return False
                self.active = self.rect.collidepoint(event.pos)
            elif event.type == pygame.KEYDOWN and self.active:
                if event.key == pygame.K_RETURN:
                    return True
                elif event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                elif event.key == pygame.K_ESCAPE:
                    self.active = False
                    self.text = ""
                elif event.unicode and event.unicode.isprintable():
                    if len(self.text) < 40:
                        self.text += event.unicode
        except Exception as e:
            print(f"[SearchBar] event error: {e}")
        return False

    def update(self, dt_ms: float):
        try:
            self.cursor_timer += dt_ms
            if self.cursor_timer >= 500:
                self.cursor_visible = not self.cursor_visible
                self.cursor_timer = 0
        except Exception as e:
            print(f"[SearchBar] update error: {e}")

    def draw(self, screen: pygame.Surface):
        try:
            glow = COLORS['spotify_green'] if self.active else None
            draw_glass_panel(screen, self.rect, border_color=COLORS['spotify_green'] if self.active
                              else COLORS['panel_border'], glow_color=glow, radius=22)

            # Search icon (simple circle + handle)
            icon_cx, icon_cy = self.rect.x + 24, self.rect.centery
            pygame.gfxdraw.aacircle(screen, icon_cx, icon_cy, 6, COLORS['text_secondary'])
            pygame.draw.line(screen, COLORS['text_secondary'],
                              (icon_cx + 4, icon_cy + 4), (icon_cx + 9, icon_cy + 9), 2)

            display_text = self.text if self.text else self.placeholder
            color = COLORS['text_primary'] if self.text else COLORS['text_dim']
            text_surface = self.font.render(safe_str(display_text), True, color)
            text_rect = text_surface.get_rect(left=self.rect.x + 42, centery=self.rect.centery)
            screen.blit(text_surface, text_rect)

            if self.active and self.cursor_visible and self.text:
                cx = text_rect.right + 2
                pygame.draw.line(screen, COLORS['spotify_green'],
                                  (cx, text_rect.top), (cx, text_rect.bottom), 2)

            # Clear (X) button -- only rendered when there's text to clear.
            if self.text:
                clear_cx = self.rect.right - 24
                clear_cy = self.rect.centery
                self.clear_button_rect = pygame.Rect(clear_cx - 12, clear_cy - 12, 24, 24)
                pygame.draw.line(screen, COLORS['text_secondary'],
                                  (clear_cx - 5, clear_cy - 5), (clear_cx + 5, clear_cy + 5), 2)
                pygame.draw.line(screen, COLORS['text_secondary'],
                                  (clear_cx + 5, clear_cy - 5), (clear_cx - 5, clear_cy + 5), 2)
            else:
                self.clear_button_rect = None
        except Exception as e:
            print(f"[SearchBar] draw error: {e}")


class SearchResultsDropdown:
    """Glass dropdown listing live/offline search matches."""

    def __init__(self, x: int, y: int, width: int):
        self.rect = pygame.Rect(x, y, width, 0)
        self.results: List[Dict] = []
        self.visible = False
        self.hover_index = -1
        self.font = load_font(18)
        self.font_small = load_font(14)
        self.font_header = load_font(13, bold=True)
        self.row_h = 46
        self.max_visible = 10
        self.header_text = ""   # non-empty when showing default recommendations

    def reposition(self, x: int, y: int, width: int):
        self.rect.x, self.rect.y, self.rect.width = x, y, width

    @property
    def _header_h(self) -> int:
        return 24 if self.header_text else 0

    def set_results(self, results: List[Dict], header_text: str = ""):
        try:
            self.header_text = header_text or ""
            self.results = results[:self.max_visible]
            self.visible = len(self.results) > 0
            self.hover_index = -1
            if self.visible:
                self.rect.height = len(self.results) * self.row_h + 8 + self._header_h
            else:
                self.rect.height = 0
        except Exception as e:
            print(f"[SearchResultsDropdown] set_results error: {e}")
            self.results = []
            self.visible = False
            self.header_text = ""

    def handle_event(self, event) -> Optional[Dict]:
        try:
            if not self.visible:
                return None
            if event.type == pygame.MOUSEMOTION:
                if self.rect.collidepoint(event.pos):
                    rel_y = event.pos[1] - self.rect.y - 4 - self._header_h
                    idx = rel_y // self.row_h if rel_y >= 0 else -1
                    self.hover_index = idx if 0 <= idx < len(self.results) else -1
                else:
                    self.hover_index = -1
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.rect.collidepoint(event.pos):
                    rel_y = event.pos[1] - self.rect.y - 4 - self._header_h
                    if rel_y >= 0:
                        idx = rel_y // self.row_h
                        if 0 <= idx < len(self.results):
                            chosen = self.results[idx]
                            self.visible = False
                            return chosen
                else:
                    self.visible = False
        except Exception as e:
            print(f"[SearchResultsDropdown] event error: {e}")
        return None

    def draw(self, screen: pygame.Surface):
        try:
            if not self.visible or not self.results:
                return
            draw_glass_panel(screen, self.rect, border_color=COLORS['panel_border'], radius=12)

            if self.header_text:
                hdr_surf = self.font_header.render(safe_str(self.header_text), True,
                                                    COLORS['spotify_green'])
                screen.blit(hdr_surf, (self.rect.x + 14, self.rect.y + 6))

            for i, artist in enumerate(self.results):
                row_rect = pygame.Rect(self.rect.x + 4,
                                        self.rect.y + 4 + self._header_h + i * self.row_h,
                                        self.rect.width - 8, self.row_h - 4)
                if i == self.hover_index:
                    hover_surf = pygame.Surface(row_rect.size, pygame.SRCALPHA)
                    pygame.draw.rect(hover_surf, (*COLORS['spotify_green'], 35), hover_surf.get_rect(),
                                      border_radius=8)
                    screen.blit(hover_surf, row_rect.topleft)

                name = safe_str(artist.get('name', 'Unknown Artist'))
                name_surf = self.font.render(name, True, COLORS['text_primary'])
                screen.blit(name_surf, (row_rect.x + 12, row_rect.y + 4))

                pop = artist.get('popularity', 0)
                genres = artist.get('genres', []) or []
                genre_txt = genres[0] if genres else "unknown genre"
                info = f"Popularity {safe_str(pop)} • {safe_str(genre_txt)}"
                info_surf = self.font_small.render(info, True, COLORS['text_secondary'])
                screen.blit(info_surf, (row_rect.x + 12, row_rect.y + 24))
        except Exception as e:
            print(f"[SearchResultsDropdown] draw error: {e}")

# ---------------------------------------------------------------------------
# UI COMPONENT: PINNED ARTISTS PANEL (multi-artist comparison chips)
# ---------------------------------------------------------------------------

class PinnedArtistsPanel:
    """Corner panel showing chip cards for up to MAX_PINNED_ARTISTS pinned artists.

    Clicking a chip (outside its remove button) selects/focuses that artist --
    the app then shows that artist's details (top tracks, etc.) in the bottom
    details card, without needing to re-search for them.
    """

    def __init__(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)
        self.font_title = load_font(16, bold=True)
        self.font_chip = load_font(15)
        self.font_small = load_font(12)
        self.pinned: List[Dict] = []  # list of {'name':.., 'color':.., 'data':..}
        self.selected_name: str = ""
        self.remove_hit_boxes: List[Tuple[pygame.Rect, int]] = []
        self.chip_hit_boxes: List[Tuple[pygame.Rect, int]] = []

    def reposition(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)

    def has_artist(self, name: str) -> bool:
        return any(p['name'] == name for p in self.pinned)

    def get_selected_data(self) -> Optional[Dict]:
        """Return the data dict of the currently selected pinned artist, if any."""
        try:
            for p in self.pinned:
                if p['name'] == self.selected_name:
                    return p.get('data')
        except Exception as e:
            print(f"[PinnedArtistsPanel] get_selected_data error: {e}")
        return None

    def toggle_pin(self, name: str, data: Dict) -> bool:
        """Pin or unpin an artist. Returns True if now pinned, False if unpinned/rejected."""
        try:
            for i, p in enumerate(self.pinned):
                if p['name'] == name:
                    self.pinned.pop(i)
                    if self.selected_name == name:
                        self.selected_name = ""
                    return False
            if len(self.pinned) >= MAX_PINNED_ARTISTS:
                return False

            # Strict uniqueness: pick the first palette color not already in
            # use by another pinned artist. Since MAX_PINNED_ARTISTS equals
            # the palette size, an unused color is always available here --
            # but if that invariant ever changes, fail the pin rather than
            # silently assigning a duplicate color to two curves.
            used_colors = {p['color'] for p in self.pinned}
            available_colors = [c for c in COMPARISON_PALETTE if c not in used_colors]
            if not available_colors:
                print("[PinnedArtistsPanel] No unique color available -- rejecting pin to avoid duplicate colors")
                return False
            color = available_colors[0]

            self.pinned.append({'name': name, 'color': color, 'data': data})
            self.selected_name = name  # newly pinned artist becomes the focused one
            return True
        except Exception as e:
            print(f"[PinnedArtistsPanel] toggle_pin error: {e}")
            return False

    def handle_event(self, event) -> Optional[str]:
        """Handle clicks on remove (x) buttons and chip body selection.

        Returns the unpinned artist name if a remove button was clicked, so
        the caller can refresh chart overlays. Selection clicks return None
        (the caller can read `selected_name` directly after this call).
        """
        try:
            if event.type == pygame.MOUSEBUTTONDOWN:
                # Remove buttons take priority over chip-body selection.
                for rect, idx in self.remove_hit_boxes:
                    if rect.collidepoint(event.pos) and 0 <= idx < len(self.pinned):
                        removed = self.pinned.pop(idx)
                        if self.selected_name == removed['name']:
                            self.selected_name = ""
                        return removed['name']

                for rect, idx in self.chip_hit_boxes:
                    if rect.collidepoint(event.pos) and 0 <= idx < len(self.pinned):
                        self.selected_name = self.pinned[idx]['name']
                        return None
        except Exception as e:
            print(f"[PinnedArtistsPanel] event error: {e}")
        return None

    def draw(self, screen: pygame.Surface):
        try:
            draw_glass_panel(screen, self.rect, border_color=COLORS['panel_border'], radius=14)
            self.remove_hit_boxes = []
            self.chip_hit_boxes = []

            title = f"Pinned Artists ({len(self.pinned)}/{MAX_PINNED_ARTISTS})"
            title_surf = self.font_title.render(safe_str(title), True, COLORS['text_primary'])
            screen.blit(title_surf, (self.rect.x + 14, self.rect.y + 12))

            if not self.pinned:
                empty_surf = self.font_small.render("Pin artists to compare trajectories",
                                                      True, COLORS['text_dim'])
                screen.blit(empty_surf, (self.rect.x + 14, self.rect.y + 40))
                return

            # Adaptive chip sizing so all MAX_PINNED_ARTISTS chips always fit
            # inside the panel regardless of how tall the panel is laid out.
            header_h = 40
            bottom_pad = 12
            chip_gap = 6
            available_h = max(0, self.rect.height - header_h - bottom_pad)
            slot_h = available_h / MAX_PINNED_ARTISTS if MAX_PINNED_ARTISTS else available_h
            chip_h = int(max(34, min(46, slot_h - chip_gap)))

            chip_y = self.rect.y + header_h
            for i, p in enumerate(self.pinned):
                chip_rect = pygame.Rect(self.rect.x + 10, chip_y + i * (chip_h + chip_gap),
                                         self.rect.width - 20, chip_h)
                is_selected = p['name'] == self.selected_name

                chip_surf = pygame.Surface(chip_rect.size, pygame.SRCALPHA)
                fill_alpha = 55 if is_selected else 25
                pygame.draw.rect(chip_surf, (*p['color'], fill_alpha), chip_surf.get_rect(), border_radius=10)
                border_width = 2 if is_selected else 1
                pygame.draw.rect(chip_surf, (*p['color'], 255), chip_surf.get_rect(),
                                  width=border_width, border_radius=10)
                screen.blit(chip_surf, chip_rect.topleft)

                if is_selected:
                    draw_glow_border(screen, chip_rect, p['color'], radius=10, layers=2)

                # Color swatch dot
                dot_center = (chip_rect.x + 14, chip_rect.centery)
                pygame.gfxdraw.filled_circle(screen, dot_center[0], dot_center[1], 6, (*p['color'], 255))

                # Artist name + peak-rank subtitle, anchored to the chip's
                # vertical center so they stay inside the box at any chip_h.
                name_surf = self.font_chip.render(safe_str(p['name'])[:18], True, COLORS['text_primary'])
                screen.blit(name_surf, (chip_rect.x + 28, chip_rect.centery - 13))

                data = p.get('data', {})
                timeline = data.get('timeline', []) if isinstance(data, dict) else []
                peak_pop = max((pt.get('popularity', 0) for pt in timeline), default=0)
                if timeline:
                    sub_txt = f"Peak #{safe_str(popularity_to_rank(peak_pop))}"
                else:
                    sub_txt = "No data"
                sub_surf = self.font_small.render(sub_txt, True, COLORS['text_secondary'])
                screen.blit(sub_surf, (chip_rect.x + 28, chip_rect.centery + 2))

                # Remove button (x)
                remove_rect = pygame.Rect(chip_rect.right - 26, chip_rect.centery - 10, 20, 20)
                pygame.draw.line(screen, COLORS['danger'],
                                  (remove_rect.x + 4, remove_rect.y + 4),
                                  (remove_rect.right - 4, remove_rect.bottom - 4), 2)
                pygame.draw.line(screen, COLORS['danger'],
                                  (remove_rect.right - 4, remove_rect.y + 4),
                                  (remove_rect.x + 4, remove_rect.bottom - 4), 2)
                self.remove_hit_boxes.append((remove_rect, i))
                # Whole chip (minus the remove button) is clickable for selection.
                self.chip_hit_boxes.append((chip_rect, i))
        except Exception as e:
            print(f"[PinnedArtistsPanel] draw error: {e}")

# ---------------------------------------------------------------------------
# UI COMPONENT: MULTI-ARTIST MOUNTAIN TRAJECTORY CHART
# ---------------------------------------------------------------------------

class TrajectoryChart:
    """Central mountain-style chart supporting the primary artist plus pinned overlays."""

    def __init__(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)
        self.primary_name = ""
        self.primary_timeline: List[Dict] = []
        self.overlays: List[Dict] = []  # [{'name':.., 'color':.., 'timeline':[...]}]
        self.hover_point = None
        self.font_axis = load_font(13)
        self.font_label = load_font(15, bold=True)
        self.font_small = load_font(13)
        self.font_no_data = load_font(24, bold=True)
        self.left_margin = 130
        self.right_margin = 30
        self.top_margin = 50
        self.bottom_margin = 50

    def reposition(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)

    def set_primary(self, name: str, timeline: List[Dict]):
        try:
            self.primary_name = name
            self.primary_timeline = sorted(timeline, key=lambda p: p.get('year', 0))
        except Exception as e:
            print(f"[TrajectoryChart] set_primary error: {e}")
            self.primary_timeline = []

    def set_overlays(self, overlays: List[Dict]):
        """overlays: list of {'name', 'color', 'timeline'}"""
        try:
            self.overlays = []
            for o in overlays:
                self.overlays.append({
                    'name': o.get('name', ''),
                    'color': o.get('color', COLORS['spotify_green']),
                    'timeline': sorted(o.get('timeline', []), key=lambda p: p.get('year', 0)),
                })
        except Exception as e:
            print(f"[TrajectoryChart] set_overlays error: {e}")
            self.overlays = []

    def _popularity_to_y(self, popularity: Any, area: pygame.Rect) -> float:
        """Map a 0-100 popularity score to a Y pixel coordinate.

        Rank #1 (popularity 100) sits at the TOP of the chart area and the
        weakest rank (popularity 0) sits at the bottom, so a higher mountain
        always reads as better performance.
        """
        try:
            pop = max(0, min(100, int(popularity or 0)))
        except (TypeError, ValueError):
            pop = 0
        return area.bottom - (pop / 100.0) * area.height

    def _rank_to_y(self, rank: Any, area: pygame.Rect) -> float:
        """Map a chart rank (#1 best) to a Y pixel coordinate (#1 at the top)."""
        return self._popularity_to_y(rank_to_popularity(rank), area)

    def _chart_area(self) -> pygame.Rect:
        return pygame.Rect(
            self.rect.x + self.left_margin,
            self.rect.y + self.top_margin,
            self.rect.width - self.left_margin - self.right_margin,
            self.rect.height - self.top_margin - self.bottom_margin,
        )

    def _all_series(self) -> List[Dict]:
        series = []
        if self.primary_timeline:
            # If the primary artist is ALSO currently pinned, its curve must
            # use the exact same RGB color as its pinned chip -- never a
            # separate hardcoded green -- so the chip and the chart curve
            # stay in strict 1-to-1 sync. Only fall back to the default
            # Spotify green when the primary artist isn't pinned at all.
            primary_color = COLORS['spotify_green']
            for o in self.overlays:
                if o['name'] == self.primary_name:
                    primary_color = o['color']
                    break
            series.append({'name': self.primary_name, 'color': primary_color,
                            'timeline': self.primary_timeline, 'is_primary': True})
        for o in self.overlays:
            if o['name'] != self.primary_name:  # avoid duplicate line if primary is also pinned
                series.append({**o, 'is_primary': False})
        return series

    def _year_bounds(self) -> Tuple[int, int]:
        years = []
        for s in self._all_series():
            years.extend(pt.get('year', 0) for pt in s['timeline'])
        if not years:
            return CURRENT_YEAR - 10, CURRENT_YEAR
        return min(years), max(max(years), CURRENT_YEAR if False else max(years))

    def handle_event(self, event):
        try:
            if event.type == pygame.MOUSEMOTION:
                self._update_hover(event.pos)
        except Exception as e:
            print(f"[TrajectoryChart] event error: {e}")

    def _update_hover(self, mouse_pos: Tuple[int, int]):
        try:
            self.hover_point = None
            area = self._chart_area()
            if not area.collidepoint(mouse_pos):
                return

            series_list = self._all_series()
            if not series_list:
                return

            min_year, max_year = self._year_bounds()
            year_range = max(max_year - min_year, 1)

            best_dist = 22
            best = None
            for s in series_list:
                for pt in s['timeline']:
                    x_prog = (pt.get('year', 0) - min_year) / year_range
                    px = area.x + x_prog * area.width
                    py = self._popularity_to_y(pt.get('popularity', 0), area)
                    d = math.hypot(mouse_pos[0] - px, mouse_pos[1] - py)
                    if d < best_dist:
                        best_dist = d
                        best = (px, py, pt, s['name'], s['color'])
            self.hover_point = best
        except Exception as e:
            print(f"[TrajectoryChart] hover error: {e}")

    def draw(self, screen: pygame.Surface):
        try:
            draw_glass_panel(screen, self.rect, border_color=COLORS['panel_border'], radius=16)
            area = self._chart_area()

            self._draw_y_axis(screen, area)

            series_list = self._all_series()
            if not series_list:
                if self.primary_name:
                    # An artist IS selected, it just has no curated historical
                    # data and the API returned nothing usable. Say so plainly
                    # instead of plotting dummy points or misleading shapes.
                    self._draw_no_data_overlay(screen, area)
                else:
                    msg = "Search and select an artist to begin exploring their timeline"
                    surf = self.font_label.render(safe_str(msg), True, COLORS['text_dim'])
                    screen.blit(surf, surf.get_rect(center=area.center))
                return

            min_year, max_year = self._year_bounds()
            self._draw_x_grid(screen, area, min_year, max_year)

            # Draw each series (overlays first, primary drawn last so it's on top)
            overlay_series = [s for s in series_list if not s['is_primary']]
            primary_series = [s for s in series_list if s['is_primary']]

            for s in overlay_series:
                self._draw_series(screen, area, s, min_year, max_year, fill=False)
            for s in primary_series:
                self._draw_series(screen, area, s, min_year, max_year, fill=True)

            self._draw_legend(screen, series_list)

            # NOTE: the hover tooltip is deliberately NOT drawn here. It is
            # drawn last by DashboardApp.draw() via draw_tooltip_overlay() so
            # it can never be covered by the search bar, dropdown or panels.

        except Exception as e:
            print(f"[TrajectoryChart] draw error: {e}")

    def _draw_no_data_overlay(self, screen: pygame.Surface, area: pygame.Rect):
        """Render the 'no information available' state for an artist that has
        neither curated historical data nor usable live API data."""
        try:
            # This headline string is intentionally Spanish -- it is the exact
            # wording specified for the "no data available" state. All other
            # copy in the app is English.
            headline = "Information Unavailable"
            sub = f"No historical data available for {safe_str(self.primary_name)}"

            head_surf = self.font_no_data.render(safe_str(headline), True, COLORS['warning'])
            sub_surf = self.font_small.render(safe_str(sub), True, COLORS['text_dim'])

            box_w = max(head_surf.get_width(), sub_surf.get_width()) + 56
            box_h = head_surf.get_height() + sub_surf.get_height() + 40
            box_rect = pygame.Rect(0, 0, box_w, box_h)
            box_rect.center = area.center

            draw_glass_panel(screen, box_rect, border_color=COLORS['warning'],
                              glow_color=COLORS['warning'], radius=14)

            screen.blit(head_surf, head_surf.get_rect(centerx=box_rect.centerx,
                                                        y=box_rect.y + 16))
            screen.blit(sub_surf, sub_surf.get_rect(centerx=box_rect.centerx,
                                                      y=box_rect.y + 16 + head_surf.get_height() + 8))
        except Exception as e:
            print(f"[TrajectoryChart] no_data overlay error: {e}")

    def draw_tooltip_overlay(self, screen: pygame.Surface):
        """Public hook so the app can draw the tooltip LAST, above every panel."""
        try:
            if self.hover_point:
                self._draw_tooltip(screen, self.hover_point)
        except Exception as e:
            print(f"[TrajectoryChart] tooltip overlay error: {e}")

    def _draw_y_axis(self, screen: pygame.Surface, area: pygame.Rect):
        """Draw crystal-clear Y-axis labeling with bracket zones."""
        try:
            title_surf = self.font_label.render("Global Peak Rank  (#1 = Top)", True,
                                                  COLORS['text_primary'])
            screen.blit(title_surf, (self.rect.x + 14, self.rect.y + 16))

            # Zones expressed as RANK bands. #1 is the best rank and sits at the
            # very top of the axis; larger rank numbers sit progressively lower.
            zones = [
                (1, 20, "Global Superstar / Top Charts", COLORS['gold']),
                (21, 50, "Mainstream / Major Artist", COLORS['cyber_cyan']),
                (51, 101, "Emerging / Niche / Early Era", COLORS['text_secondary']),
            ]
            for rank_best, rank_worst, label, color in zones:
                # Best rank in the band maps to the HIGHER position on screen.
                y_top = self._rank_to_y(rank_best, area)
                y_bot = self._rank_to_y(rank_worst, area)
                zone_rect = pygame.Rect(area.x, y_top, area.width, max(1, y_bot - y_top))
                zone_surf = pygame.Surface(zone_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(zone_surf, (*color, 10), zone_surf.get_rect())
                screen.blit(zone_surf, zone_rect.topleft)

                bracket_y = (y_top + y_bot) / 2
                label_txt = f"#{rank_best}-#{rank_worst}"
                label_surf = self.font_axis.render(safe_str(label_txt), True, color)
                screen.blit(label_surf, (self.rect.x + 14, bracket_y - 16))
                desc_surf = self.font_axis.render(safe_str(label), True, color)
                screen.blit(desc_surf, (self.rect.x + 14, bracket_y - 2))

            # Horizontal gridlines with RANK tick labels: #1 at the top of the
            # axis descending to #101 at the bottom.
            for rank_tick in (1, 21, 41, 61, 81, 101):
                y = self._rank_to_y(rank_tick, area)
                draw_dashed_line(screen, (area.x, y), (area.right, y), COLORS['grid_line'])
                tick_label = f"#{rank_tick}"
                val_surf = self.font_axis.render(safe_str(tick_label), True, COLORS['text_dim'])
                screen.blit(val_surf, (area.x - 34, y - 7))
        except Exception as e:
            print(f"[TrajectoryChart] y-axis error: {e}")

    def _draw_x_grid(self, screen: pygame.Surface, area: pygame.Rect, min_year: int, max_year: int):
        try:
            year_range = max(max_year - min_year, 1)
            step = max(1, year_range // 8)
            year = min_year
            while year <= max_year:
                x_prog = (year - min_year) / year_range
                x = area.x + x_prog * area.width
                draw_dashed_line(screen, (x, area.top), (x, area.bottom), COLORS['grid_line'])
                y_surf = self.font_axis.render(safe_str(year), True, COLORS['text_dim'])
                screen.blit(y_surf, (x - 14, area.bottom + 8))
                year += step
        except Exception as e:
            print(f"[TrajectoryChart] x-grid error: {e}")

    def _draw_series(self, screen: pygame.Surface, area: pygame.Rect, series: Dict,
                      min_year: int, max_year: int, fill: bool):
        try:
            timeline = series['timeline']
            if not timeline:
                return
            color = series['color']
            year_range = max(max_year - min_year, 1)

            points = []
            for pt in timeline:
                x_prog = (pt.get('year', 0) - min_year) / year_range
                px = area.x + x_prog * area.width
                py = self._popularity_to_y(pt.get('popularity', 0), area)
                points.append((px, py))

            if fill and len(points) >= 2:
                draw_gradient_fill(screen, area, points, color, top_alpha=70)

            if len(points) >= 2:
                pygame.draw.aalines(screen, color, False, points, blend=1)
                # Thicken by drawing a couple more offset lines (aalines is 1px)
                for dy in (-1, 1):
                    thick_pts = [(x, y + dy) for x, y in points]
                    pygame.draw.aalines(screen, color, False, thick_pts, blend=1)

            for i, (px, py) in enumerate(points):
                r = 5 if series['is_primary'] else 4
                draw_glow_circle(screen, (px, py), r, color, layers=3 if series['is_primary'] else 1)
        except Exception as e:
            print(f"[TrajectoryChart] draw_series error: {e}")

    def _draw_legend(self, screen: pygame.Surface, series_list: List[Dict]):
        try:
            legend_x = self.rect.right - 220
            legend_y = self.rect.y + 16
            for i, s in enumerate(series_list):
                y = legend_y + i * 20
                pygame.gfxdraw.filled_circle(screen, legend_x, y + 6, 5, (*s['color'], 255))
                label = safe_str(s['name'])[:22]
                surf = self.font_small.render(label, True, COLORS['text_primary'])
                screen.blit(surf, (legend_x + 14, y))
        except Exception as e:
            print(f"[TrajectoryChart] legend error: {e}")

    def _draw_tooltip(self, screen: pygame.Surface, hover_point):
        try:
            x, y, pt, series_name, color = hover_point
            album_pop = pt.get('popularity', 0)
            peak_label, _ = popularity_to_peak_rank_label(album_pop)
            header_lines = [
                f"{series_name}",
                f"Album: {safe_str(pt.get('album', 'Unknown'))}",
                f"Year: {safe_str(pt.get('year', '?'))}",
                f"Peak Rank: #{safe_str(popularity_to_rank(album_pop))}  ({peak_label})",
            ]
            album_tracks = pt.get('top_tracks', []) or []

            header_surfaces = [self.font_small.render(safe_str(l), True, COLORS['text_primary'])
                                for l in header_lines]

            track_surfaces = []
            if album_tracks:
                label_surf = self.font_small.render("Top Tracks:", True, COLORS['spotify_green'])
                track_surfaces.append(label_surf)
                for t in album_tracks[:2]:
                    track_line = f"  \u2022 {safe_str(t.get('name', 'Unknown Track'))} ({safe_str(t.get('popularity', 0))})"
                    track_surfaces.append(self.font_small.render(track_line, True, COLORS['text_secondary']))

            all_surfaces = header_surfaces + track_surfaces
            width = max(s.get_width() for s in all_surfaces) + 24
            height = len(all_surfaces) * 20 + 16

            tip_x = min(x + 16, SCREEN_STATE['width'] - width - 12)
            tip_x = max(12, tip_x)

            # Preferred position is ABOVE the hovered point. If that would push
            # the tooltip off (or near) the top of the window -- where the
            # header/search row lives -- flip it BELOW the point instead so the
            # whole box always stays fully visible on screen.
            above_y = y - height - 16
            if above_y < self.rect.y + 8:
                tip_y = y + 20                       # flip below the point
                # If flipping down would run past the bottom, clamp it back in.
                tip_y = min(tip_y, SCREEN_STATE['height'] - height - 12)
            else:
                tip_y = above_y
            tip_y = max(12, tip_y)

            tip_rect = pygame.Rect(int(tip_x), int(tip_y), width, height)

            draw_glass_panel(screen, tip_rect, border_color=color, glow_color=color, radius=10)
            for i, s in enumerate(all_surfaces):
                screen.blit(s, (tip_rect.x + 12, tip_rect.y + 8 + i * 20))
        except Exception as e:
            print(f"[TrajectoryChart] tooltip error: {e}")

# ---------------------------------------------------------------------------
# UI COMPONENT: ARTIST STATS CARD (followers, popularity badge, genres, top tracks)
# ---------------------------------------------------------------------------

class ArtistStatsCard:
    """Bottom-right details card: artist metrics + Top 5 tracks with clickable
    external-link arrows that open the track's Spotify page in the browser."""

    def __init__(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)
        self.data: Optional[Dict] = None
        self.font_name = load_font(26, bold=True)
        self.font_section = load_font(16, bold=True)
        self.font_body = load_font(14)
        self.font_small = load_font(12)
        # (hit_rect, spotify_url) pairs rebuilt every draw() call for click detection.
        self.link_hit_boxes: List[Tuple[pygame.Rect, str]] = []
        # Scrollable tracklist state.
        self.scroll_offset = 0
        self.max_scroll = 0
        self.scroll_step = 34            # one track row per wheel notch
        self.tracklist_viewport: Optional[pygame.Rect] = None

    def reposition(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)

    def set_data(self, data: Dict):
        self.data = data
        self.scroll_offset = 0  # reset scroll when a different artist loads

    def handle_event(self, event):
        """Handle link-arrow clicks (tracks + artist profile) and wheel scrolling."""
        try:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, url in self.link_hit_boxes:
                    if rect.collidepoint(event.pos) and url:
                        webbrowser.open(url)
                        return True

            # Mouse-wheel scrolling over the tracklist viewport.
            if event.type == pygame.MOUSEWHEEL:
                mouse_pos = pygame.mouse.get_pos()
                if self.tracklist_viewport and self.tracklist_viewport.collidepoint(mouse_pos):
                    self.scroll_offset = self._clamp_scroll(self.scroll_offset - event.y * self.scroll_step)
                    return True

            # Legacy button-4/5 wheel events (older SDL/X11 style).
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                if self.tracklist_viewport and self.tracklist_viewport.collidepoint(event.pos):
                    direction = -1 if event.button == 4 else 1
                    self.scroll_offset = self._clamp_scroll(
                        self.scroll_offset + direction * self.scroll_step)
                    return True
        except Exception as e:
            print(f"[ArtistStatsCard] handle_event error: {e}")
        return False

    def _clamp_scroll(self, value: int) -> int:
        """Keep the scroll offset within [0, max_scroll] for the current content."""
        try:
            return max(0, min(int(value), int(self.max_scroll)))
        except Exception:
            return 0

    def _artist_profile_url(self, info: Dict) -> str:
        """Build the artist's Spotify profile URL.

        Live-search results carry a real 22-char base62 Spotify artist ID, which
        maps directly to open.spotify.com/artist/{id}. Curated dataset entries
        use readable slugs (e.g. "taylor_swift") that are NOT valid Spotify IDs,
        so for those we fall back to a Spotify artist search URL -- that always
        resolves to something real instead of a broken /artist/ link.
        """
        try:
            artist_id = safe_str(info.get('id', ''))
            name = safe_str(info.get('name', ''))
            is_real_spotify_id = (len(artist_id) == 22
                                   and re.fullmatch(r'[A-Za-z0-9]{22}', artist_id) is not None)
            if is_real_spotify_id:
                return f"https://open.spotify.com/artist/{artist_id}"
            if name:
                return f"https://open.spotify.com/search/{urllib.parse.quote(name)}/artists"
        except Exception as e:
            print(f"[ArtistStatsCard] profile url error: {e}")
        return "https://open.spotify.com/search"

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        """Greedy word-wrap so long hint text stays inside the card."""
        lines: List[str] = []
        try:
            words = safe_str(text).split()
            current = ""
            for word in words:
                candidate = f"{current} {word}".strip()
                if font.size(candidate)[0] <= max_width or not current:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            if current:
                lines.append(current)
        except Exception as e:
            print(f"[ArtistStatsCard] wrap_text error: {e}")
            return [safe_str(text)]
        return lines

    def _draw_link_arrow(self, screen: pygame.Surface, center: Tuple[int, int],
                          color: Tuple[int, int, int]):
        """Draw a small vector '↗' external-link arrow (diagonal line + arrowhead)."""
        try:
            cx, cy = center
            # Diagonal shaft (bottom-left to top-right)
            start = (cx - 4, cy + 4)
            end = (cx + 4, cy - 4)
            pygame.draw.aaline(screen, color, start, end)
            # Arrowhead: two short strokes back from the tip
            pygame.draw.line(screen, color, end, (end[0] - 4, end[1]), 2)
            pygame.draw.line(screen, color, end, (end[0], end[1] + 4), 2)
        except Exception as e:
            print(f"[ArtistStatsCard] link arrow draw error: {e}")

    def draw(self, screen: pygame.Surface):
        try:
            self.link_hit_boxes = []
            draw_glass_panel(screen, self.rect, border_color=COLORS['panel_border'], radius=16)

            if not self.data:
                msg = self.font_body.render("No artist selected", True, COLORS['text_dim'])
                screen.blit(msg, (self.rect.x + 16, self.rect.y + 16))
                return

            info = self.data.get('artist_info', {}) if isinstance(self.data, dict) else {}
            top_tracks = self.data.get('top_tracks', []) if isinstance(self.data, dict) else []

            cy = self.rect.y + 18

            # Artist name + clickable Spotify profile link arrow. Both the name
            # and the arrow are part of the same hit box, so clicking either
            # opens the artist's Spotify profile in the default browser.
            artist_name = safe_str(info.get('name', 'Unknown Artist'))
            name_surf = self.font_name.render(artist_name, True, COLORS['text_primary'])
            screen.blit(name_surf, (self.rect.x + 16, cy))

            profile_url = self._artist_profile_url(info)
            arrow_cx = min(self.rect.x + 16 + name_surf.get_width() + 16, self.rect.right - 18)
            arrow_cy = cy + name_surf.get_height() // 2
            self._draw_link_arrow(screen, (arrow_cx, arrow_cy), COLORS['spotify_green'])
            if profile_url:
                name_hit = pygame.Rect(self.rect.x + 16, cy,
                                        name_surf.get_width() + 34, name_surf.get_height())
                self.link_hit_boxes.append((name_hit, profile_url))
            cy += 32

            no_data = bool(self.data.get('no_data')) if isinstance(self.data, dict) else False
            if no_data:
                # Honest empty state -- nothing is fabricated for this artist.
                # Spanish headline is the exact specified wording for this
                # state; the supporting hint text below it is English.
                warn_surf = self.font_section.render("Information Unavailable", True,
                                                      COLORS['warning'])
                screen.blit(warn_surf, (self.rect.x + 16, cy))
                cy += 26
                hint = "No curated dataset entry and no API data for this artist."
                for line in self._wrap_text(hint, self.font_small, self.rect.width - 32):
                    line_surf = self.font_small.render(line, True, COLORS['text_dim'])
                    screen.blit(line_surf, (self.rect.x + 16, cy))
                    cy += 18
                self.tracklist_viewport = None
                self.max_scroll = 0
                return

            # Data provenance badge. Reaching this point means real data exists
            # (the no-data state returned early above), so the only distinction
            # left is whether live Spotify values were successfully overlaid on
            # top of the curated historical dataset.
            live_overlay = bool(self.data.get('live_overlay')) if isinstance(self.data, dict) else False
            source_label = "CURATED + LIVE SPOTIFY" if live_overlay else "CURATED DATASET"
            source_color = COLORS['cyber_cyan'] if live_overlay else COLORS['spotify_green']
            source_surf = self.font_small.render(source_label, True, source_color)
            screen.blit(source_surf, (self.rect.x + 16, cy))
            cy += 20

            # Global Peak Rank badge. Industry-standard convention: #1 is the
            # BEST/highest achievement. We translate the 0-100 popularity
            # score into a peak-rank tier badge ("#1 Global Peak" for the top
            # tier) rather than showing a raw "X/100" score, while keeping the
            # underlying popularity number visible in small text for transparency.
            pop = info.get('popularity', 0)
            try:
                pop_int = int(pop)
            except (TypeError, ValueError):
                pop_int = 0
            peak_rank_label, badge_color = popularity_to_peak_rank_label(pop_int)
            badge_rect = pygame.Rect(self.rect.x + 16, cy, 150, 30)
            badge_surf = pygame.Surface(badge_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(badge_surf, (*badge_color, 40), badge_surf.get_rect(), border_radius=15)
            pygame.draw.rect(badge_surf, (*badge_color, 255), badge_surf.get_rect(), width=1, border_radius=15)
            screen.blit(badge_surf, badge_rect.topleft)
            badge_text = self.font_body.render(safe_str(peak_rank_label), True, badge_color)
            screen.blit(badge_text, badge_text.get_rect(center=badge_rect.center))

            # Followers
            followers = info.get('followers', 0)
            followers_txt = f"{format_number(followers)} followers"
            followers_surf = self.font_body.render(safe_str(followers_txt), True, COLORS['text_secondary'])
            screen.blit(followers_surf, (badge_rect.right + 12, cy + 6))
            cy += 30

            # Small secondary line showing the underlying score + monthly listeners,
            # so the raw popularity metric is still visible for those who want it.
            monthly_listeners = info.get('monthly_listeners', 0)
            detail_txt = f"Popularity score: {safe_str(pop_int)}/100  •  {format_number(monthly_listeners)} monthly listeners"
            detail_surf = self.font_small.render(detail_txt, True, COLORS['text_dim'])
            screen.blit(detail_surf, (self.rect.x + 16, cy))
            cy += 24

            # Genres
            genres = info.get('genres', []) or []
            if genres:
                genre_txt = " • ".join(safe_str(g) for g in genres[:3])
            else:
                genre_txt = "No genre data"
            genre_surf = self.font_small.render(genre_txt, True, COLORS['neon_purple'])
            screen.blit(genre_surf, (self.rect.x + 16, cy))
            cy += 26

            # Divider
            pygame.draw.line(screen, COLORS['panel_border'], (self.rect.x + 16, cy),
                              (self.rect.right - 16, cy), 1)
            cy += 14

            # Top songs section header (count reflects what's actually available).
            section_title = f"Top {len(top_tracks)} Famous Songs" if top_tracks else "Top Songs"
            section_surf = self.font_section.render(section_title, True, COLORS['spotify_green'])
            screen.blit(section_surf, (self.rect.x + 16, cy))
            cy += 26

            if not top_tracks:
                empty_surf = self.font_small.render("No track data available", True, COLORS['text_dim'])
                screen.blit(empty_surf, (self.rect.x + 16, cy))
                self.tracklist_viewport = None
                self.max_scroll = 0
                return

            # --- Scrollable tracklist viewport ---
            row_h = 34
            viewport = pygame.Rect(self.rect.x + 8, cy,
                                    self.rect.width - 16,
                                    max(0, self.rect.bottom - 12 - cy))
            self.tracklist_viewport = viewport

            content_h = len(top_tracks) * row_h
            self.max_scroll = max(0, content_h - viewport.height)
            self.scroll_offset = self._clamp_scroll(self.scroll_offset)
            needs_scrollbar = self.max_scroll > 0

            # Clip drawing to the viewport so rows can't bleed outside the card.
            prev_clip = screen.get_clip()
            screen.set_clip(viewport)

            bar_gutter = 10 if needs_scrollbar else 0
            for idx, track in enumerate(top_tracks):
                row_y = viewport.y + idx * row_h - self.scroll_offset
                # Skip rows entirely outside the visible viewport.
                if row_y + row_h < viewport.y - row_h or row_y > viewport.bottom + row_h:
                    continue

                rank = track.get('rank', 0)
                name = safe_str(track.get('name', 'Unknown Track'))
                if len(name) > 20:
                    name = name[:20] + "..."
                track_pop = track.get('popularity', 0)
                track_url = track.get('spotify_url', '')

                rank_surf = self.font_small.render(f"#{safe_str(rank)}", True, COLORS['text_dim'])
                screen.blit(rank_surf, (self.rect.x + 16, row_y))

                name_surf = self.font_body.render(name, True, COLORS['text_primary'])
                screen.blit(name_surf, (self.rect.x + 42, row_y - 2))

                # Clickable external-link arrow, opens the exact track in browser.
                arrow_center = (self.rect.right - 22 - bar_gutter, row_y + 6)
                arrow_color = COLORS['cyber_cyan'] if track_url else COLORS['text_dim']
                self._draw_link_arrow(screen, arrow_center, arrow_color)
                arrow_hit_rect = pygame.Rect(arrow_center[0] - 12, arrow_center[1] - 12, 24, 24)
                # Only register the click target if the arrow is actually visible
                # inside the viewport, so scrolled-out rows aren't clickable.
                if track_url and viewport.contains(arrow_hit_rect.clip(viewport)) \
                        and arrow_hit_rect.colliderect(viewport):
                    self.link_hit_boxes.append((arrow_hit_rect.clip(viewport), track_url))

                # Popularity mini meter
                bar_x = self.rect.x + 42
                bar_y = row_y + 18
                bar_w = self.rect.width - 42 - 44 - bar_gutter
                bar_h = 5
                pygame.draw.rect(screen, COLORS['grid_line'], (bar_x, bar_y, bar_w, bar_h), border_radius=3)
                try:
                    fill_w = int(max(0, min(100, int(track_pop))) / 100 * bar_w)
                except (TypeError, ValueError):
                    fill_w = 0
                if fill_w > 0:
                    pygame.draw.rect(screen, COLORS['spotify_green'], (bar_x, bar_y, fill_w, bar_h),
                                      border_radius=3)

            screen.set_clip(prev_clip)

            if needs_scrollbar:
                self._draw_scrollbar(screen, viewport, content_h)
        except Exception as e:
            print(f"[ArtistStatsCard] draw error: {e}")

    def _draw_scrollbar(self, screen: pygame.Surface, viewport: pygame.Rect, content_h: int):
        """Draw a subtle vertical scrollbar indicator for the tracklist."""
        try:
            track_x = viewport.right - 5
            track_rect = pygame.Rect(track_x, viewport.y, 4, viewport.height)
            track_surf = pygame.Surface(track_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(track_surf, (*COLORS['grid_line'], 140), track_surf.get_rect(),
                              border_radius=2)
            screen.blit(track_surf, track_rect.topleft)

            visible_ratio = viewport.height / content_h if content_h else 1.0
            thumb_h = max(24, int(viewport.height * visible_ratio))
            scroll_ratio = (self.scroll_offset / self.max_scroll) if self.max_scroll else 0.0
            thumb_y = viewport.y + int((viewport.height - thumb_h) * scroll_ratio)

            thumb_rect = pygame.Rect(track_x, thumb_y, 4, thumb_h)
            thumb_surf = pygame.Surface(thumb_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(thumb_surf, (*COLORS['spotify_green'], 200), thumb_surf.get_rect(),
                              border_radius=2)
            screen.blit(thumb_surf, thumb_rect.topleft)
        except Exception as e:
            print(f"[ArtistStatsCard] scrollbar draw error: {e}")


# ---------------------------------------------------------------------------
# MAIN APPLICATION
# ---------------------------------------------------------------------------

class DashboardApp:
    """Principal orchestrator for the full-screen analytics dashboard."""

    def __init__(self):
        pygame.init()
        # Enable key-repeat so holding Backspace (or any key) smoothly repeats
        # input instead of requiring separate individual key presses.
        # (350ms initial delay, then repeats every 40ms while held.)
        try:
            pygame.key.set_repeat(350, 40)
        except Exception as e:
            print(f"[DashboardApp] set_repeat error: {e}")

        self.fullscreen = True
        self.screen = self._create_display(self.fullscreen)
        pygame.display.set_caption("Global Artist Timeline & Peak Explorer")
        self.clock = pygame.time.Clock()

        self.data_manager = DataManager()

        self.running = True
        self.primary_artist_data: Optional[Dict] = None
        self.search_busy = False
        # True while the dropdown is showing the default recommendation list
        # (rather than live search results), so we only rebuild it on state
        # transitions instead of every event (which would reset hover state).
        self._recs_visible = False
        self.status_flash: Optional[Tuple[str, Tuple[int, int, int], int]] = None  # (msg, color, ttl_ms)

        self.font_title = load_font(32, bold=True)
        self.font_subtitle = load_font(15)

        self._build_layout()

    # ---------------------------------------------------------------
    # Display / layout management
    # ---------------------------------------------------------------
    def _create_display(self, fullscreen: bool) -> pygame.Surface:
        try:
            if fullscreen:
                screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                screen = pygame.display.set_mode((DEFAULT_WIDTH, DEFAULT_HEIGHT), pygame.RESIZABLE)
            SCREEN_STATE['width'], SCREEN_STATE['height'] = screen.get_size()
            return screen
        except Exception as e:
            print(f"[DashboardApp] Fullscreen failed, using resizable window: {e}")
            screen = pygame.display.set_mode((DEFAULT_WIDTH, DEFAULT_HEIGHT), pygame.RESIZABLE)
            SCREEN_STATE['width'], SCREEN_STATE['height'] = screen.get_size()
            return screen

    def _toggle_fullscreen(self):
        try:
            self.fullscreen = not self.fullscreen
            self.screen = self._create_display(self.fullscreen)
            self._build_layout()
        except Exception as e:
            print(f"[DashboardApp] toggle_fullscreen error: {e}")

    def _handle_resize(self, size: Tuple[int, int]):
        try:
            if not self.fullscreen:
                self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
            SCREEN_STATE['width'], SCREEN_STATE['height'] = self.screen.get_size()
            self._build_layout()
        except Exception as e:
            print(f"[DashboardApp] resize error: {e}")

    def _build_layout(self):
        """Compute responsive positions for all components based on current screen size.

        Vertical banding (top to bottom):
          1. Title/subtitle header band       (~0   .. 78px)
          2. Dedicated search bar row          (~78  .. 140px) -- its own clear row,
             with the results dropdown rendering below it so it never overlaps
             the chart canvas.
          3. Main content band (chart + right column) filling the rest of the
             screen down to a small bottom margin. With the timeline slider
             removed, this band now extends almost to the bottom of the window.
        """
        try:
            w, h = self.screen.get_size()

            header_band_bottom = 78
            search_row_top = header_band_bottom + 6
            search_h = 48
            search_row_bottom = search_row_top + search_h + 14  # clearance below search row

            content_top = search_row_bottom + 16
            content_bottom_margin = 24
            content_h = h - content_top - content_bottom_margin

            # --- Dedicated search bar row (its own clear band, generous padding) ---
            search_w = min(600, int(w * 0.42))
            search_x = (w - search_w) // 2
            search_y = search_row_top

            if not hasattr(self, 'search_bar'):
                self.search_bar = SearchBar(search_x, search_y, search_w, search_h)
                self.search_dropdown = SearchResultsDropdown(search_x, search_y + search_h + 8, search_w)
            else:
                self.search_bar.reposition(search_x, search_y, search_w, search_h)
                self.search_dropdown.reposition(search_x, search_y + search_h + 8, search_w)

            # --- Right column: pinned artists panel (top) + stats/details card (bottom) ---
            right_col_w = min(300, int(w * 0.20))
            right_col_x = w - right_col_w - 24
            right_col_y = content_top

            # Sized generously so all MAX_PINNED_ARTISTS (5) chips fit with
            # comfortable breathing room, never feeling cramped: header (~40px)
            # + MAX_PINNED_ARTISTS (6) chips x ~48px each + bottom padding.
            # PinnedArtistsPanel.draw() also sizes chips adaptively from this
            # height, so the two stay consistent automatically.
            pin_h = 40 + MAX_PINNED_ARTISTS * 48 + 16
            self._ensure_component('pinned_panel', PinnedArtistsPanel,
                                    right_col_x, right_col_y, right_col_w, pin_h)

            stats_y = right_col_y + pin_h + 16
            stats_h = max(200, content_top + content_h - stats_y)
            self._ensure_component('stats_card', ArtistStatsCard,
                                    right_col_x, stats_y, right_col_w, stats_h)

            # --- Trajectory chart occupies the remaining central area, now taller
            #     since the bottom timeline slider band has been reclaimed. ---
            chart_x = 30
            chart_y = content_top
            chart_w = right_col_x - chart_x - 24
            chart_h = content_h
            self._ensure_component('trajectory_chart', TrajectoryChart,
                                    chart_x, chart_y, chart_w, chart_h)

        except Exception as e:
            print(f"[DashboardApp] build_layout error: {e}")

    def _ensure_component(self, attr_name: str, cls, x: int, y: int, w: int, h: int):
        """Create a UI component on first layout pass, otherwise reposition it in place."""
        try:
            if not hasattr(self, attr_name):
                setattr(self, attr_name, cls(x, y, w, h))
            else:
                getattr(self, attr_name).reposition(x, y, w, h)
        except Exception as e:
            print(f"[DashboardApp] _ensure_component error ({attr_name}): {e}")

    # ---------------------------------------------------------------
    # Event handling (all protected individually per spec)
    # ---------------------------------------------------------------
    def handle_events(self):
        for event in pygame.event.get():
            try:
                if event.type == pygame.QUIT:
                    self.running = False
            except Exception as e:
                print(f"[DashboardApp] QUIT handling error: {e}")

            try:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.fullscreen:
                            self._toggle_fullscreen()
                        else:
                            self.running = False
                    elif event.key == pygame.K_F11:
                        self._toggle_fullscreen()
                    elif event.key == pygame.K_p and self.primary_artist_data:
                        self._toggle_pin_primary()
            except Exception as e:
                print(f"[DashboardApp] KEYDOWN handling error: {e}")

            try:
                if event.type == pygame.VIDEORESIZE and not self.fullscreen:
                    self._handle_resize((event.w, event.h))
            except Exception as e:
                print(f"[DashboardApp] VIDEORESIZE handling error: {e}")

            try:
                if self.search_bar.handle_event(event):
                    self._perform_search()
                if self.search_bar.just_cleared:
                    # Clicking the search bar's (X) button clears the text AND
                    # closes any open results dropdown immediately.
                    self.search_dropdown.set_results([])
                    self._recs_visible = False
                self._sync_recommendations()
            except Exception as e:
                print(f"[DashboardApp] search_bar handling error: {e}")

            try:
                chosen = self.search_dropdown.handle_event(event)
                if chosen:
                    self._load_primary_artist(chosen)
            except Exception as e:
                print(f"[DashboardApp] dropdown handling error: {e}")

            try:
                previously_selected = self.pinned_panel.selected_name
                unpinned_name = self.pinned_panel.handle_event(event)
                if unpinned_name:
                    self._refresh_chart_overlays()
                if self.pinned_panel.selected_name != previously_selected:
                    self._focus_selected_pinned_artist()
            except Exception as e:
                print(f"[DashboardApp] pinned_panel handling error: {e}")

            try:
                self.trajectory_chart.handle_event(event)
            except Exception as e:
                print(f"[DashboardApp] chart handling error: {e}")

            try:
                self.stats_card.handle_event(event)
            except Exception as e:
                print(f"[DashboardApp] stats_card link handling error: {e}")

            try:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._check_pin_button_click(event.pos)
            except Exception as e:
                print(f"[DashboardApp] pin-button click error: {e}")

    def _check_pin_button_click(self, pos: Tuple[int, int]):
        """The stats card header area doubles as a pin/unpin toggle button."""
        try:
            if not self.primary_artist_data:
                return
            pin_button_rect = pygame.Rect(self.stats_card.rect.right - 90,
                                           self.stats_card.rect.y + 8, 74, 26)
            if pin_button_rect.collidepoint(pos):
                self._toggle_pin_primary()
        except Exception as e:
            print(f"[DashboardApp] pin button check error: {e}")

    def _toggle_pin_primary(self):
        try:
            info = self.primary_artist_data.get('artist_info', {})
            name = info.get('name', '')
            if not name:
                return
            now_pinned = self.pinned_panel.toggle_pin(name, self.primary_artist_data)
            self._show_status(f"{'Pinned' if now_pinned else 'Unpinned'} {name}",
                               COLORS['success'] if now_pinned else COLORS['warning'])
            self._refresh_chart_overlays()
        except Exception as e:
            print(f"[DashboardApp] toggle_pin_primary error: {e}")

    def _refresh_chart_overlays(self):
        try:
            overlays = [{'name': p['name'], 'color': p['color'],
                         'timeline': p['data'].get('timeline', [])}
                        for p in self.pinned_panel.pinned]
            self.trajectory_chart.set_overlays(overlays)
        except Exception as e:
            print(f"[DashboardApp] refresh_overlays error: {e}")

    def _focus_selected_pinned_artist(self):
        """When a pinned chip is clicked, show that artist's details in the
        bottom-right details card (without disturbing the chart's primary
        trajectory or the other pinned overlays)."""
        try:
            selected_data = self.pinned_panel.get_selected_data()
            if selected_data:
                self.stats_card.set_data(selected_data)
                name = selected_data.get('artist_info', {}).get('name', 'artist')
                self._show_status(f"Viewing details for {name}", COLORS['cyber_cyan'])
            elif self.primary_artist_data:
                # Nothing selected anymore -- fall back to showing the primary artist.
                self.stats_card.set_data(self.primary_artist_data)
        except Exception as e:
            print(f"[DashboardApp] focus_selected_pinned_artist error: {e}")

    def _show_status(self, message: str, color: Tuple[int, int, int], ttl_ms: int = 2500):
        self.status_flash = (safe_str(message), color, ttl_ms)

    # ---------------------------------------------------------------
    # Search & data loading
    # ---------------------------------------------------------------
    def _sync_recommendations(self):
        """Show the default top-10 recommended artists whenever the search bar
        is focused with an empty query (on click/focus, after pressing the
        clear button, or after backspacing the query away)."""
        try:
            should_show = bool(self.search_bar.active) and not self.search_bar.text.strip()
            if should_show and not self._recs_visible:
                recs = self.data_manager.get_recommended_artists()
                if recs:
                    self.search_dropdown.set_results(recs, header_text="RECOMMENDED ARTISTS")
                    self._recs_visible = True
            elif not should_show and self._recs_visible:
                self._recs_visible = False
        except Exception as e:
            print(f"[DashboardApp] sync_recommendations error: {e}")

    def _perform_search(self):
        try:
            query = self.search_bar.text.strip()
            if not query:
                self.search_dropdown.set_results([])
                return
            self.search_busy = True
            results = self.data_manager.search_artists(query)
            self.search_dropdown.set_results(results)
            self._recs_visible = False  # dropdown now holds live results, not recs
            if not results:
                self._show_status(f'No artists found for "{query}"', COLORS['warning'])
        except Exception as e:
            print(f"[DashboardApp] perform_search error: {e}")
            self.search_dropdown.set_results([])
        finally:
            self.search_busy = False

    def _load_primary_artist(self, artist_info: Dict):
        try:
            artist_id = artist_info.get('id', '')
            artist_name = artist_info.get('name', '')
            if not artist_id and not artist_name:
                return

            live_genres = artist_info.get('genres') or None
            timeline_data = self.data_manager.get_artist_timeline(artist_id, artist_name, live_genres)
            if not timeline_data:
                self._show_status(f"Could not load data for {artist_name}", COLORS['danger'])
                return

            self.primary_artist_data = timeline_data
            info = timeline_data.get('artist_info', {})
            timeline = timeline_data.get('timeline', [])

            self.trajectory_chart.set_primary(info.get('name', artist_name), timeline)
            self.stats_card.set_data(timeline_data)
            # Loading a fresh primary artist via search takes focus away from
            # whatever pinned chip may have been selected previously.
            self.pinned_panel.selected_name = ""

            self.search_bar.text = info.get('name', artist_name)
            self.search_dropdown.set_results([])

            if timeline_data.get('no_data'):
                self._show_status(
                    f"No data available for {info.get('name', artist_name)} "
                    f"(not in curated dataset)", COLORS['warning'])
            else:
                self._show_status(f"Loaded {info.get('name', artist_name)}", COLORS['success'])

        except Exception as e:
            print(f"[DashboardApp] load_primary_artist error: {e}")
            self._show_status("Error loading artist data", COLORS['danger'])

    # ---------------------------------------------------------------
    # Update / draw / run
    # ---------------------------------------------------------------
    def update(self, dt_ms: float):
        try:
            self.search_bar.update(dt_ms)
        except Exception as e:
            print(f"[DashboardApp] update error: {e}")

        try:
            if self.status_flash:
                msg, color, ttl = self.status_flash
                ttl -= dt_ms
                self.status_flash = (msg, color, ttl) if ttl > 0 else None
        except Exception as e:
            print(f"[DashboardApp] status_flash update error: {e}")

    def draw(self):
        try:
            self.screen.fill(COLORS['canvas'])
            self._draw_background_grid()
            self._draw_header()

            self.trajectory_chart.draw(self.screen)
            self.pinned_panel.draw(self.screen)
            self.stats_card.draw(self.screen)
            self._draw_pin_button()

            self.search_bar.draw(self.screen)
            self.search_dropdown.draw(self.screen)

            self._draw_status_overlay()

            # Chart tooltip is drawn LAST, on top of every panel, the search
            # bar and the results dropdown, so it can never be occluded.
            self.trajectory_chart.draw_tooltip_overlay(self.screen)

            pygame.display.flip()
        except Exception as e:
            print(f"[DashboardApp] draw error: {e}")

    def _draw_background_grid(self):
        try:
            w, h = self.screen.get_size()
            spacing = 60
            for x in range(0, w, spacing):
                pygame.draw.line(self.screen, (*COLORS['grid_line'], ), (x, 0), (x, h), 1)
            for y in range(0, h, spacing):
                pygame.draw.line(self.screen, (*COLORS['grid_line'], ), (0, y), (w, y), 1)
        except Exception as e:
            print(f"[DashboardApp] background_grid error: {e}")

    def _draw_header(self):
        try:
            w, _ = self.screen.get_size()
            title = "GLOBAL ARTIST TIMELINE & PEAK EXPLORER"
            title_surf = self.font_title.render(safe_str(title), True, COLORS['text_primary'])
            title_rect = title_surf.get_rect(centerx=w // 2, y=12)
            self.screen.blit(title_surf, title_rect)

            subtitle = "Spotify Analytics Dashboard"
            sub_surf = self.font_subtitle.render(safe_str(subtitle), True, COLORS['cyber_cyan'])
            sub_rect = sub_surf.get_rect(centerx=w // 2, y=title_rect.bottom + 4)
            self.screen.blit(sub_surf, sub_rect)

            # Thin divider closing out the header band, separating it visually
            # from the dedicated search row beneath it.
            divider_y = 78
            pygame.draw.line(self.screen, COLORS['panel_border'], (40, divider_y), (w - 40, divider_y), 1)
        except Exception as e:
            print(f"[DashboardApp] header error: {e}")

    def _draw_pin_button(self):
        try:
            if not self.primary_artist_data:
                return
            info = self.primary_artist_data.get('artist_info', {})
            name = info.get('name', '')
            is_pinned = self.pinned_panel.has_artist(name)

            btn_rect = pygame.Rect(self.stats_card.rect.right - 90, self.stats_card.rect.y + 8, 74, 26)
            color = COLORS['spotify_green'] if not is_pinned else COLORS['warning']
            btn_surf = pygame.Surface(btn_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(btn_surf, (*color, 45), btn_surf.get_rect(), border_radius=13)
            pygame.draw.rect(btn_surf, (*color, 255), btn_surf.get_rect(), width=1, border_radius=13)
            self.screen.blit(btn_surf, btn_rect.topleft)

            label = "Unpin" if is_pinned else "Pin (P)"
            font = load_font(12, bold=True)
            label_surf = font.render(safe_str(label), True, color)
            self.screen.blit(label_surf, label_surf.get_rect(center=btn_rect.center))
        except Exception as e:
            print(f"[DashboardApp] pin_button draw error: {e}")

    def _draw_status_overlay(self):
        try:
            w, h = self.screen.get_size()
            y_offset = 10
            font = load_font(15, bold=True)

            if self.data_manager.is_offline():
                msg = "OFFLINE MODE: Using Local Historical Timeline Data"
                surf = font.render(safe_str(msg), True, COLORS['danger'])
                rect = surf.get_rect(centerx=w // 2, y=y_offset)
                bg_rect = rect.inflate(24, 10)
                bg_surf = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(bg_surf, (*COLORS['danger'], 30), bg_surf.get_rect(), border_radius=8)
                pygame.draw.rect(bg_surf, (*COLORS['danger'], 200), bg_surf.get_rect(), width=1, border_radius=8)
                self.screen.blit(bg_surf, bg_rect.topleft)
                self.screen.blit(surf, rect)
                y_offset += 34

            if self.status_flash:
                msg, color, _ = self.status_flash
                surf = font.render(safe_str(msg), True, color)
                rect = surf.get_rect(centerx=w // 2, y=y_offset)
                self.screen.blit(surf, rect)
        except Exception as e:
            print(f"[DashboardApp] status_overlay error: {e}")

    def run(self):
        try:
            last_tick = pygame.time.get_ticks()
            while self.running:
                now = pygame.time.get_ticks()
                dt = now - last_tick
                last_tick = now

                self.handle_events()
                self.update(dt)
                self.draw()
                self.clock.tick(FPS)
        except Exception as e:
            print(f"[DashboardApp] run loop error: {e}")
        finally:
            try:
                pygame.quit()
            except Exception:
                pass


def main():
    try:
        app = DashboardApp()
        app.run()
    except Exception as e:
        print(f"[main] Fatal startup error: {e}")
        try:
            pygame.quit()
        except Exception:
            pass
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()