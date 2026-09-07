# FPL Squad Planner

> A pitch-based Fantasy Premier League decision workspace: build a squad in a real formation, set your captain, load in your live team, and check fixtures and injury news — all from one page.

**Type:** Live demo &nbsp;|&nbsp; **Role:** Product (define + build) &nbsp;|&nbsp; **Timeframe:** —
**Live:** <fill in after deploy> &nbsp;|&nbsp; **Repo:** <fill in after `gh repo create`>

---

## The problem
The earlier version worked but read as a squad-*editor* — a flat list of 15 names against a budget bar. It didn't answer the questions an FPL manager actually has moment to moment: what does my formation look like, who's captain, what's my next fixture, and how much time is left before the deadline.

## The redesign brief
I was handed a detailed UX brief modeled on professional FPL analytics tools — projected points, expected goals/assists, ownership trend graphs, a captaincy-recommendation engine, a full player-comparison and watchlist system, transfer-suggestion AI. The brief itself included the right instruction: **implement in phases**, and **never invent a statistic the data doesn't support**.

## What I decided (and traded off)
- **Decision:** Treat the brief as a phased roadmap, not a single build → **because** the full scope is genuinely several weeks of product work; attempting all of it at once risks a shallow, half-working pass on every feature rather than a solid one on the core experience → **trade-off accepted:** several requested features (player comparison, watchlist, analytics dashboard, transfer-suggestion engine) are deferred, not delivered.
- **Decision:** Explicitly refuse to build "projected points" or a "captaincy recommendation" score → **because** the public FPL API has no such field — it would be an invented heuristic presented as fact, which the brief's own data-integrity section rules out → **trade-off accepted:** the product doesn't yet answer "who should I captain," only surfaces the real inputs (form, fixture difficulty, availability) a manager needs to decide that themselves.
- **Decision:** Add a real football pitch with formation-based starting XI / bench, rather than the previous flat list → **because** this is the single highest-value change from the brief: it's the actual mental model FPL managers use → **trade-off accepted:** manual line-up overrides are limited to same-position swaps (start/bench a player), not free drag-and-drop reordering — full drag-and-drop is a real dependency for a small ergonomic gain, which the brief's own performance section warns against.
- **Decision:** Add a live gameweek deadline countdown using real `events` data from the FPL API (not previously fetched) → **because** it's genuinely computable and directly serves the brief's "establish context" requirement → this required extending the existing scheduled data pipeline, not building a new one.
- **Decision:** Keep the existing architecture completely intact — same GitHub Action, same serverless proxy, same static data files → **because** the brief explicitly said not to replace working infrastructure without a technical reason, and there wasn't one here; this was a frontend and data-shape change, not an architecture change.

## How it works
Unchanged: a GitHub Action refreshes player prices, fixtures, and injury news twice daily into static files; a Vercel serverless function proxies personal team lookups live. New: the same Action now also fetches gameweek (`events`) data — deadlines and current/next flags — powering a live countdown. The frontend adds a formation engine (7 legal formations, auto-assigns the highest-scoring eligible players per position into the starting XI, remainder to bench), click-to-select captain/vice-captain, and same-position bench/start swaps, all layered on the same player dataset the rest of the app already used.

## Outcome
Not yet measured with real users. What I'd track first: whether the pitch view actually gets used over a flatter list for a repeat visitor, since that's the core bet of this redesign.

## What I'd do next (the deferred phases)
- **Player discovery upgrades** (ownership/form/fixture filters) — the ownership data (`selected_by_percent`) is already in the pipeline, unused; this is the next cheapest win.
- **Decision support** (captaincy signal, projected points) — the honest path is a simple, transparent heuristic (form × fixture ease × expected minutes) shown with its inputs visible, never as a bare "predicted score" — so a user can see and challenge the reasoning rather than trust a black box.
- **Transfer planner IN/OUT workflow** — a natural next phase once the pitch/lineup model above is solid, since a transfer is really just "remove one starter, add one replacement" against the same budget/quota rules already enforced.
- **Player comparison, watchlist, full analytics dashboard** — real features, each deserving its own scoped pass rather than being squeezed in alongside everything else.

## AI/ML specifics
Still no model in this build, by design. If a captaincy or projected-points feature is built, it should be a transparent, inspectable heuristic over real inputs already in the pipeline (form, fixture difficulty, availability, minutes) — not a trained model presented as more authoritative than the data supports. This mirrors the free-transfers and fixture-history decisions from earlier phases of the project: show what's verifiable, and say plainly what isn't.
