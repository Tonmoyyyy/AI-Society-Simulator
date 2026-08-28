# AI Society Simulator — Frontend (v0.1)

http://127.0.0.1:5500/AI-Society-Simulator-main/frontend/pages/dashboard.html

Plain HTML + CSS + vanilla JS + Bootstrap 5, per the approved v0.1 stack —
no build tool, no npm install, no bundler. Open a terminal and go.

## Design

A civic observatory, not a social app — the aesthetic borrows from census
records and instrument panels (paper, ink, brass) rather than social-media
brights. Two typographic voices carry the concept: **Fraunces** (serif)
names citizens and headlines, because citizens are individuals with
stories; **JetBrains Mono** renders every number, timestamp, and tick
count, because aggregate data is a different kind of thing than a person.
**Inter** holds the UI chrome together in between. The signature element is
the pulse indicator in the nav bar — it only glows when the WebSocket feed
is actually connected, not a decorative animation.

## 1. Start the backend first

The frontend calls `http://127.0.0.1:8000` by default (see
`static/js/config.js`). Follow `backend/README.md` to get the API running
before opening any frontend page — every page will show a clear error if it
can't reach the backend, rather than failing silently.

## 2. Serve the frontend

Any static file server works. From this `frontend/` folder:

```powershell
python -m http.server 5500
```

Then open **http://127.0.0.1:5500** in a browser.

Do NOT just double-click the HTML files (`file://` URLs) — the WebSocket
connection and some fetch behavior are more reliable served over `http://`,
even for a static site.

## 3. Pages

| Page | Auth needed? | What it does |
|---|---|---|
| `pages/login.html` | — | Sign up or log in (JWT stored in `localStorage`) |
| `pages/dashboard.html` | Read: no. "Run one tick": yes | Population/wellbeing stats, wellbeing chart, trending posts, recent history, manual tick trigger |
| `pages/citizens.html` | Read: no. "Add a citizen": yes | Browsable roster with personality trait bars, paginated; click a card to open its profile |
| `pages/citizen.html?id=N` | No | Full profile — stats, personality bars, wallet balance + recent purchases, recent memories; auto-refreshes when a WS event mentions this citizen |
| `pages/feed.html` | Read: no. (posting is via the tick engine, not a UI form in v0.1) | Live feed — new posts from ticks appear at the top automatically over WebSocket |
| `pages/shops.html` | Read: no. Creating a shop/product: yes | Marketplace — every shop and its products; new shops/products via modal forms; live "just bought" notices over WebSocket |
| `pages/timeline.html` | No | Simulation history — population milestones, wealth changes, happiness crises/recoveries, filterable by category |
| `pages/world.html` | Read: no. "Generate world": yes | The 3D society map — Three.js view of every city, district, road, building and citizen marker, with click-to-inspect info panels, a city selector and a live header that follows the simulation |

Every page works read-only without logging in (citizens/dashboard/feed/
timeline/world are all public API endpoints) — logging in only unlocks the
write actions (create a citizen, trigger a tick, generate the world).

### The world map's dependencies

`pages/world.html` is the only page that loads a third-party library beyond
Bootstrap and Chart.js: **Three.js 0.160.1**, from a CDN via an
`<script type="importmap">`, with no build step. The map's own code is split
across `static/js/world/` — `scene.js` (camera, lights, renderer; the only file
that imports `"three"` directly), `builders.js` (geometry), `picking.js`
(raycasting), `panels.js` (DOM cards and the legend) and `main.js`
(orchestration, polling, performance guards).

## What's not here yet (by design)

- No manual post/comment/reaction/follow UI — those exist in the API
  (Phase 4) but the UI only surfaces what the tick engine generates
  automatically; adding manual social actions is a fast follow, not core
  to watching the simulation
- No admin UI for the government — appointing a President, setting the tax
  rate or toggling the curfew is done through `PATCH /api/v1/government`
  (or `POST /api/v1/government/auto-appoint`) for now. The map *reads* the
  government live and relabels the Presidential Palace within one poll, so a
  change made over the API is visible without a page reload
- No wallet/transaction detail view per citizen yet
- Config (`API_BASE`, `WS_URL`) is a single hardcoded object in
  `config.js` — fine for local dev, would need an env-based build step for
  a real deployment (out of scope for v0.1's "no build tool" constraint)

## A real bug found and fixed while building this

While wiring the Timeline page to `GET /api/v1/timeline`, the response
showed `total: 1` with an empty `items: []` on a table that was actually
completely empty (verified directly in MySQL). The cause was in
`timeline_repo.list_paginated` on the backend: `query.with_entities(func.count())`
strips a Query's table context when there's no explicit `select_from()`,
so it silently ran a bare `SELECT count(*)` with **no FROM clause at all**
— which MySQL answers with `1` (counting one implicit row of constants),
completely disconnected from the real table. Every other count query in the
codebase already used `.select_from(Model)` and was unaffected; only this
one path had the bug. Fixed by switching to `query.count()`, which
correctly preserves the FROM clause and any filters already applied — with
two regression tests added (`test_timeline_total_matches_items_when_empty`,
`test_timeline_total_matches_items_length_on_one_page`) so this can't
silently come back.

This was caught by writing a small Node script that replicated the exact
`fetch()` calls each frontend page makes and checking the response shape
against what the JS expects — not by reading the frontend code in
isolation. Worth doing that kind of contract check for any future page too.
