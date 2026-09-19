# AI Prompt Log

**Project:** Global Artist Timeline & Peak Explorer
**Course:** CMU 15-113 — Effective Coding with AI
**Assignment:** HW3 — Explore an API

This document discloses the AI tools used to build this project and the key prompts that shaped the implementation, in the order they influenced the codebase.

---

## 1. AI Models & Tools Used

| Tool | Role in this project |
|---|---|
| **Google Gemini** | Early ideation and planning: choosing the API, brainstorming the visualization concept, and drafting the initial UI/UX direction and color language. |
| **Kiro AI** (agentic IDE, Claude-based) | Primary implementation partner: wrote and iteratively refactored `main.py`, authored the curated dataset, ran compile/runtime verification, and produced this documentation. |

**Division of labor.** Gemini was used conversationally to explore *what* to build. Kiro AI was used agentically to build it — it had direct access to the workspace, so it could edit files, execute `python -m py_compile`, run scripted smoke tests against the live Spotify API, and verify its own claims rather than only suggesting code.

---

## 2. Key Prompts That Shaped the Implementation

### 2.1 Initial scope and API selection

> "Build a complete academic-grade Python Pygame application titled 'Global Artist Timeline & Peak Explorer' for CMU 15-113 HW3 using `spotipy` and custom graph visualizations. Read credentials safely from environment variables with `python-dotenv`. Wrap all network and API parsing logic in strict try-except blocks. If Wi-Fi is disabled, rate limits occur, or credentials fail, do not crash — switch to a local fallback dataset."

**Effect:** established the project skeleton, the `.env` + `python-dotenv` credential pattern, the `try/except`-everywhere reliability requirement, and the offline-fallback concept that later became the core architecture.

### 2.2 Hybrid API architecture (the pivotal decision)

> "Keep live Spotify API integration for artist search and autocomplete. For trajectory charts, metrics, top tracks, and popularity timelines, seamlessly fall back to `timeline_fallback.json` or generated structured data whenever the Spotify API returns an error or restricted fields."

**Context and effect:** this prompt was a direct response to a blocking discovery. While verifying the first implementation, Kiro AI called the live API with the project's real credentials and found that Spotify's February/March 2026 Developer Mode changes had **removed `GET /artists/{id}/top-tracks` (403 Forbidden)** and **stripped the `popularity` and `followers` fields** from Artist objects for this access tier. The original design — charting live popularity over time — was therefore impossible on these credentials, regardless of code quality.

Rather than silently degrade, the AI surfaced the constraint with evidence and proposed options. The resulting architecture:

- **Live API** → artist search/discovery only (`sp.search`).
- **Curated local dataset** → popularity timelines, album milestones, top tracks.
- **Live overlay attempt** → `sp.artist()` and `sp.artist_top_tracks()` are still called; if they ever succeed, real values replace the local ones automatically.

This is the single most important design decision in the project, and it exists because the AI verified an assumption against reality instead of trusting it.

### 2.3 Fallback strategy and data normalization

> "Implement a strict `_normalize_artist_data()` method in `DataManager`. Guarantee that EVERY searched artist — whether from curated JSON, live API, or fallback — returns a fully populated data dictionary. Completely eliminate blank/empty stats cards or missing song lists."

**Effect:** introduced a single choke point that every data path must pass through before reaching the UI, so rendering code never has to defend against missing keys or empty lists. Also drove `deterministic_follower_count()` — a SHA-256 name-seeded, popularity-scaled estimator — after a bug report that every artist was showing an identical hardcoded `5,000,000` followers.

### 2.4 Honesty about missing data (a deliberate reversal)

> "Completely remove fake generated song names. If album-level historical track data is missing, set `top_tracks = []`."

> "For searched artists that do not have curated historical timeline data and return no API data: do not plot dummy points or misleading shapes. Render a clean overlay stating 'Sin acceso a información'."

**Effect:** these two prompts intentionally reversed part of the previous requirement. The normalization layer had been padding sparse data with invented song titles and synthesized album milestones to avoid empty panels. That was replaced with `build_no_data_payload()`, which fabricates nothing and flags `no_data: True`, and the UI now states plainly that no information is available. Fabricated-data generators (`_pad_top_tracks`, `_pad_album_tracks`, `_pad_timeline`) were deleted outright.

This is worth recording as a lesson: the AI had faithfully implemented "never show an empty panel," and that instruction — followed literally — produced misleading output. Correcting it required explicitly prioritizing honesty over visual completeness.

### 2.5 UI/UX: glassmorphism design language

> "Use a dark matte glassmorphism aesthetic: `#090A0F` canvas, translucent `#14161F` panels, glowing neon curves, sleek Spotify green `#1DB954`. Anti-aliased rendering, dashed grid lines, and smooth gradient fills beneath curves. Use crisp modern sans-serif typography with system font fallbacks."

**Effect:** produced the reusable drawing helpers that define the app's look — `draw_glass_panel()`, `draw_glow_border()`, `draw_glow_circle()`, `draw_dashed_line()`, `draw_gradient_fill()` — and the `load_font()` helper with a Helvetica → Arial → Trebuchet MS → Segoe UI fallback chain and font caching.

A later prompt asked to **remove all "cyberpunk" terminology** from code comments and UI labels while preserving the visual quality, which was applied across the module docstring, palette comments, window caption, and subtitle.

### 2.6 Rank-based Y-axis ("#1 at the top")

> "Fix the vertical ranking scale: position #1 (Peak / Top) at the very top of the chart's Y-axis, and lower rankings at the bottom. Invert the Y-coordinate mapping so higher performance is visually at the top."

**Effect:** investigation showed the *geometry* was already correct — popularity 100 already mapped to the top of the plot area. The real defect was **semantic**: the axis was labeled `0–100`, which invites the misreading that 0 is the top. The fix relabeled the axis in rank terms (`popularity_to_rank()` / `rank_to_popularity()` helpers, title "Global Peak Rank (#1 = Top)", ticks `#1` → `#101`, rank-based zone bands) and centralized the mapping into `_popularity_to_y()` / `_rank_to_y()`.

Another case where the AI checked the existing behavior before "fixing" it, and reported that the stated diagnosis was partly inaccurate.

### 2.7 Interaction and polish passes

Later prompts drove a series of targeted UI/UX fixes:

- Multi-artist comparison with **strictly unique colors** per pinned artist (raised from 5 to 6 slots, with an `assert` tying the palette length to `MAX_PINNED_ARTISTS`).
- **Color synchronization** between the pinned chip and its chart curve — a real bug where a pinned artist's curve was hardcoded green while its chip showed a different palette color.
- **Tooltip z-order**: drawing the tooltip last in the render loop so panels and the search bar can never occlude it, and flipping it below the hovered point near the top edge.
- **Search bar**: a clear (`✕`) button that only appears when there is text, plus `pygame.key.set_repeat(350, 40)` so holding `Backspace` deletes continuously.
- **Default recommendations**: a top-10 list shown when the search bar is focused while empty.
- **Scrollable tracklist** with a clipped viewport, mouse-wheel handling and a subtle scrollbar.
- **External links**: `webbrowser.open()` arrows for both individual tracks and the artist's Spotify profile.

### 2.8 Documentation and compliance

> "Review, create, and refine all required repository documentation. ALL generated content (README.md, prompt_log.md, and code comments) must be written strictly in 100% English. Do not execute any git push or remote repository commands."

**Effect:** produced the current `README.md` (structured against the HW3 handout sections), the strict `.gitignore`, and this log. It also surfaced a conflict worth noting: the earlier prompt had *mandated* the Spanish UI string "Sin acceso a información". The resolution was to keep that one specified phrase and translate every other non-English string in the app to English.

---

## 3. Notable Bugs the AI Found While Self-Verifying

These were not reported by the user — they were discovered because the AI ran the code and inspected real output rather than assuming success.

| Bug | How it surfaced | Fix |
|---|---|---|
| Stale OAuth token masked invalid credentials | Feeding deliberately bogus keys still reported "online" | Switched from spotipy's on-disk `.cache` to `MemoryCacheHandler()` |
| `import re` missing | `py_compile` passed; a runtime smoke test hit `NameError` when clicking a profile link | Added the import |
| Wrong `spotipy` kwarg | `artist_albums(album_type='album,single')` returned HTTP 400 | Changed to `include_groups` |
| Identical follower counts | Printed values for all curated artists and saw the same number repeated | Added `deterministic_follower_count()` |
| Rank order inverted for curated tracks | Curated `top_tracks` were ranked by raw JSON order, not popularity | Sort descending by popularity before assigning ranks |
| Doomed API calls for curated slugs | Console flooded with "Invalid base62 id" | Skip the live overlay unless the ID is a real 22-char base62 Spotify ID |
| Unreachable provenance badge | Audit showed "SIMULATED DATA" could no longer be reached after the no-data refactor | Replaced with a real `CURATED DATASET` / `CURATED + LIVE SPOTIFY` distinction |

---

## 4. Reflection on Working With AI

**What worked well.** Delegating verification, not just generation. The most valuable AI contributions here were not the code it wrote first, but the moments it executed that code, compared the result against the stated requirement, and reported a mismatch — the Spotify API restriction, the already-correct Y-axis geometry, and the `import re` omission would all have shipped broken or misdescribed otherwise.

**What required human judgment.** Three times the AI flagged that an instruction, followed literally, would produce a worse result: padding empty data with invented song titles, adding a 6th comparison color nearly identical to two existing ones, and writing documentation for API capabilities that the access tier does not actually grant. Each needed a human decision about intent, not more code.

**Key takeaway.** "It compiles" is not evidence that it works. `python -m py_compile main.py` passed cleanly while the code still contained a missing import that crashed on a real click. Runtime verification against real data caught what static checks could not.
