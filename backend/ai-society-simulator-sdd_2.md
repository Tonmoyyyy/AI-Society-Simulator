# AI Society Simulator — Software Design Document (v0.1 MVP)

**Tagline:** "Build a world. Watch AI create civilization."

> Revision note: this version simplifies the original SDD per approved architecture-improvement instructions — lighter stack, smaller table set, MVP-first phasing. Full civilization scope (crime, politics, market, disasters, etc.) stays on the backlog and gets designed when its phase actually starts.

---

## 1. Vision

AI Society Simulator হলো একটা persistent, tick-based digital civilization যেখানে AI citizen-রা নিজেদের personality, memory, mood এবং economy অনুযায়ী independently decide করে। Social media clone না — emergent-behavior simulation engine।

Core philosophy অপরিবর্তিত: **"No randomness without reason."**

## 2. Objectives

- Scalable-by-design (but simple-by-default) simulation core।
- Solo developer-friendly stack — existing skillসেট (MySQL, basic JS/HTML/CSS) ব্যবহার করে দ্রুত একটা playable v0.1 বের করা।
- Production-shaped code from day 1, even in a simplified stack।
- Distributed-system complexity (Redis/Celery/k8s/load balancing) পরে যোগ হবে, দরকার হলে — শুরুতে না।

## 3. Target Users

একই আগের মতো: developer নিজে (portfolio + research), পরে recruiter/spectator/researcher audience।

## 4. Technology Stack (v0.1 — simplified)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python, FastAPI | unchanged |
| Frontend | HTML + CSS + vanilla JS + Bootstrap | React আগের plan-এ ছিল, এখন v1.0-পরবর্তী migration হিসেবে backlog-এ |
| Database | MySQL | developer-এর existing strength; schema migration-friendly রাখা হচ্ছে যাতে PostgreSQL-এ future move সহজ হয় |
| ORM | SQLAlchemy | unchanged — DB-agnostic থাকে বলেই MySQL→Postgres migration সহজ থাকবে |
| Background jobs | APScheduler | Celery/Redis বাদ — MVP-তে একটাই process যথেষ্ট |
| Realtime | WebSocket (native FastAPI) | Redis pub/sub ছাড়া, single-instance broadcast যথেষ্ট এই স্কেলে |
| Auth | JWT | unchanged |
| Charts | Chart.js | unchanged, vanilla JS-এ mount করা হবে |
| Cache | — (none yet) | দরকার পড়লে পরে Redis যোগ হবে |
| Deployment | Docker | still "later", MVP আগে |

**Explicitly deferred (not v0.1):** Redis, Celery, Kubernetes, multiple workers, load balancing, microservices, React frontend, PostgreSQL. এগুলো architecture-কে block করছে না — layering (API/Service/Repository) এমনভাবে করা হচ্ছে যাতে পরে এগুলো drop-in করা যায়, rewrite ছাড়াই।

## 5. MVP Scope (v0.1)

**AI Citizen fields (v0.1):** id, name, age, personality_json, mood, happiness, energy, health, job, current_activity, created_at.
(Money citizens table-এ নেই — wallet-ই money-র একমাত্র source of truth, দেখো §8। পরবর্তী phase-এ stress, relationships, skills, goals ইত্যাদি যোগ হবে — schema additively বাড়বে।)

**Primary keys (v0.1):** সব table-এ `INT AUTO_INCREMENT PRIMARY KEY` — UUID না। Debug করা সহজ, MVP scale-এ যথেষ্ট। UUID migration future scaling phase-এর জন্য backlog-এ থাকবে।

**Personality structure:** `personality_json` একটা flat dict of 0–100 int scores, যেমন:
```json
{
  "kindness": 70,
  "intelligence": 80,
  "ambition": 60,
  "social": 40,
  "honesty": 90
}
```
Decision engine এই trait-গুলোকেই utility scoring-এ input হিসেবে ব্যবহার করবে (উদাহরণ: high `social` → socialize action-এর utility বাড়ায়, high `ambition` → work action-এর utility বাড়ায়)।

**Simulation configuration (v0.1):**
- Dev mode tick interval: 1 tick = 10 real seconds (APScheduler interval)
- Simulated time scale: 1 tick = 1 simulated hour
- Max citizens for v0.1: 100 (hard cap in citizen creation logic; future phases raise this)

**Core loops in v0.1:**
- Citizen CRUD + randomized-but-structured personality generation
- Tick-based decision engine: needs (hunger/energy/money/mood/goals) → action (work/sleep/eat/socialize/create post)
- Basic social: posts, comments, likes, follow — feed reacts to simulation events
- Basic economy: job, salary, wallet, transactions
- Dashboard: population, happiness, money stats, trending posts
- **Simulation Timeline / Replay** (new, see §9)

## 6. Non-Functional Requirements

- **Simplicity first:** every added technology must justify itself against "does v0.1 actually need this." Redis/Celery-class tools only when a measured bottleneck demands them.
- **Migration-friendly persistence:** SQLAlchemy models avoid MySQL-only syntax where reasonably possible, so a future Postgres move is a config change, not a rewrite.
- **Maintainability:** same API → Service → Repository layering as before — this is what keeps the stack swappable later.
- **Observability:** structured logging + a `simulation_ticks` log table from day 1.
- **Security:** JWT auth, password hashing (argon2/bcrypt), Pydantic validation at every boundary.

## 7. Risks (updated)

| Risk | Impact | Mitigation |
|---|---|---|
| Vanilla JS frontend becomes unmaintainable as features grow | Slower MVP iteration later | Keep JS modular (one file per page/feature), Bootstrap components over custom CSS where possible; React migration is an accepted, planned cost post-v1.0 |
| MySQL-specific features creep into schema | Harder Postgres migration later | Stick to portable SQLAlchemy types, avoid MySQL-only functions in queries |
| Single-process APScheduler becomes a bottleneck as citizen count grows | Tick time grows unbounded | Profile before optimizing; Celery/Redis is the known escape hatch, not implemented until needed |
| MVP scope creep back toward full 25-table design | Phase 1 never ships | Table list is capped per §8 until its phase starts |

## 8. Database Design (v0.1 — reduced table set)

Only these tables for MVP. Everything else (jobs table is folded into citizens for v0.1 simplicity — see note) gets added when its phase starts.

All primary keys below: `INT AUTO_INCREMENT PRIMARY KEY` (v0.1 decision — see §5).

### `users`
id (PK int), email (unique), password_hash, role (admin/spectator), created_at

### `citizens`
id (PK int), name, age, personality_json, mood (float), happiness (float), energy (float), health (float), job (varchar — plain field for v0.1, not a separate `jobs` table yet), current_activity (varchar), created_at

> No `money`/`balance` field here — wallet is the single source of truth for citizen money (see `wallets` below). Every read of "how much does this citizen have" goes through the wallet, never a cached column on `citizens`.
> A real `jobs` table (salary tiers, employer relationships) comes back in Phase 5 (Economy) when it actually does something.

### `memories` (simplified for v0.1)
id (PK int), citizen_id (FK), event_type (varchar), description (text), importance (int), created_at
Index: `(citizen_id, created_at)`.
> Sentiment scoring, decay, and `related_citizen_id` linking are deferred — v0.1 memory is just "what happened and how important was it," which is enough for the decision engine to weight recent important events higher.

### `posts`
id (PK int), citizen_id (FK), content, created_at

### `comments`
id (PK int), post_id (FK), citizen_id (FK), content, created_at

*(Likes and follows are small enough to fold in as lightweight tables too — `reactions(id, post_id, citizen_id, type, created_at)` and `follows(follower_id, followee_id, created_at)` — created in Phase 4 when the social system is actually built, not before.)*

### `wallets`
id (PK int), citizen_id (FK, unique), balance (decimal) — **only source of truth for citizen money**

### `transactions`
id (PK int), from_wallet_id (FK, nullable), to_wallet_id (FK, nullable), amount (decimal), type (varchar), created_at

All balance mutations go through one service method using a row lock + transaction row insert — never a bare `UPDATE balance`, even in MVP.

### `simulation_ticks`
id (PK int), tick_number, started_at, finished_at, citizens_processed, status

### `timeline_events` (see §9)
id (PK int), tick_number, category (varchar — e.g. "milestone", "economy", "social"), title, description, payload_json, created_at

---

## 9. Simulation History / Replay Feature (new)

A **Simulation Timeline**: the system detects and stores noteworthy events as they happen, so a user can scroll through the civilization's history instead of only seeing the live state.

Examples: "Day 1: 100 citizens created", "Day 20: [citizen] became richest", "Day 50: first business created", "Day 100: economic downturn".

**Design for v0.1:**
- `timeline_events` table (above) is the source of truth.
- The tick engine, after processing each tick, runs a small set of **milestone detectors** (cheap checks, not a separate AI layer): e.g. "is current richest citizen different from last tick's richest?", "did average happiness drop below threshold?", "citizen count crossed a round number?". Any hit writes a `timeline_events` row.
- Detectors are just plain Python functions registered in a list — easy to add one per new feature phase (e.g., Phase 5 adds an economy detector, Phase 4 adds a social detector).
- Frontend: a simple timeline page (Bootstrap list-group or vertical timeline component) reading `GET /api/v1/timeline` with pagination/filtering by category.

This stays cheap precisely because it's detection-on-top-of-existing-tick-data, not a new simulation subsystem.

---

# Architecture

## Backend Structure (unchanged shape, MySQL + APScheduler swapped in)

```
app/
  api/v1/            → route handlers (auth, citizens, posts, timeline, ...)
  services/          → business logic (citizen_service, memory_service, economy_service, social_service, timeline_service)
  repositories/      → DB access only
  models/            → SQLAlchemy ORM models (MySQL dialect via SQLAlchemy — portable)
  schemas/           → Pydantic request/response schemas
  core/              → config.py, security.py, deps.py
  db/                → session.py, base.py
  simulation/         → engine.py, decision_pipeline.py, milestone_detectors.py
  websocket/          → connection_manager.py, events.py (single-instance broadcast, no Redis pub/sub yet)
  tasks/               → tick_scheduler.py (APScheduler job)
  utils/
  tests/
  main.py
alembic/               → migrations (kept DB-agnostic where practical)
```

Layering rule unchanged: API → Service → Repository → DB. This is exactly what makes "swap MySQL→Postgres" or "swap APScheduler→Celery" later a config/adapter change, not a rewrite.

## Frontend Structure (vanilla, Bootstrap)

```
frontend/
  index.html
  pages/
    dashboard.html
    citizens.html
    citizen_profile.html
    feed.html
    timeline.html
    login.html
  static/
    css/
      custom.css
    js/
      api/            → fetch wrappers per domain (auth.js, citizens.js, posts.js, timeline.js)
      pages/           → one JS file per page, only handles that page's DOM
      charts/          → Chart.js setup helpers
      websocket.js
    vendor/            → Bootstrap, Chart.js (or via CDN)
```

Each HTML page loads only the JS it needs — no bundler/build step required for v0.1, keeping the "no frontend learning overhead" goal intact. A build tool (Vite) is an option later, not a requirement now.

## AI Decision Engine — unchanged design, same reasoning

Still a **utility-scored FSM** (perceive → generate candidates → score → select → execute → conflict resolution), for the same reason as before: cheap to run at citizen-scale, easy to debug, and it's the same pipeline shape a future behavior-tree or LLM-driven engine would slot into. v0.1 action catalog: work, sleep, eat, socialize, create post — matching the MVP scope.

---

# Development Roadmap (Phases — approved order)

| Phase | Scope |
|---|---|
| **Phase 1 — Project Setup** | FastAPI scaffold, MySQL connection, folder architecture, env config, Alembic init, `users` table + JWT auth |
| **Phase 2 — Citizen System** | `citizens` table, personality generation, CRUD API, basic citizen list/profile pages |
| **Phase 3 — Simulation Engine** | `simulation_ticks`, `memories` tables; tick scheduler (APScheduler); decision pipeline; action execution (work/sleep/eat/socialize/post) |
| **Phase 4 — Social System** | `posts`, `comments`, `reactions`, `follows`; feed page; WebSocket live updates; timeline social-detector |
| **Phase 5 — Economy** | `wallets`, `transactions`; real `jobs` concept (salary tied to tick engine); timeline economy-detector |
| **Phase 6 — Dashboard & Timeline UI** | Aggregate stats endpoints, Chart.js dashboard, `timeline_events` table + timeline page |
| **v0.1 release** | Stabilize: tests, setup docs, manual run instructions (Docker still deferred) |

Backlog (post-v0.1, unscoped until reached): React frontend migration, PostgreSQL migration, Redis/Celery, crime/justice, politics/elections, marketplace/businesses, disasters, heatmaps/GDP analytics, LLM-driven citizens.

---

# Coding Rules (confirmed)

- One module/phase at a time — no skipping ahead.
- Each delivery includes: file-by-file explanation, setup instructions, DB migration, and testing steps.
- Wait for explicit approval before starting the next phase.
