# FPL Squad Planner

> A Fantasy Premier League companion: plan a squad against live prices, pull your own team in as a starting point, check upcoming fixture difficulty, and track player availability — all from one page.

**Type:** Live demo &nbsp;|&nbsp; **Role:** Product (define + build) &nbsp;|&nbsp; **Timeframe:** —
**Live:** <fill in after deploy> &nbsp;|&nbsp; **Repo:** <fill in after `gh repo create`>

---

## The problem
FPL managers juggle several separate questions across the season: what should my squad look like (budget, quota, club cap), what does my actual team look like right now, are my players' next few fixtures easy or hard, and is anyone I own injured or suspended. The official app answers all of these, but split across different screens with no single quick-glance view — and no way to sandbox "what if" squad ideas against real prices without touching your live team.

## Who it's for
FPL managers who want a faster, single-page view across planning, their live team, fixture difficulty, and injury news — particularly useful right after a wildcard or during a busy transfer week.

## What I decided (and traded off)
- **Decision:** Use two different data-fetch strategies for two different data shapes — a scheduled GitHub Action for anything shared across all users (prices, fixtures, injury news), a live serverless proxy for anything personal (a specific team's picks and history) → **because** the personal data is keyed by an ID typed in at runtime and can't be pre-baked for every possible team, while the shared data benefits from being fast and CORS-free → **trade-off accepted:** two moving parts to maintain instead of one.
- **Decision:** Let a user pull their live squad into the planner with one click, but keep it a one-way copy rather than a live sync → **because** the planner's job is to test hypothetical changes, and a live sync would blur "what I actually own" with "what I'm considering" → **trade-off accepted:** if the user's live team changes after loading it in, the planner doesn't know — they'd need to reload it.
- **Decision:** Show fixture difficulty using FPL's own attack/defence strength ratings rather than attempting a "how did this player do against this opponent last season" analysis → **because** the public API only exposes career-total stats per player, not fixture-by-fixture history from prior seasons — building that would mean scraping a third-party historical dataset and accepting a much less trustworthy pipeline → **trade-off accepted:** the fixture view answers "is this a hard run of games" rather than the more specific "did this exact matchup favor this exact player before," and the app says so explicitly rather than implying more precision than it has.
- **Decision:** Surface player status/news/chance-of-playing directly from the existing player dataset instead of building a separate news pipeline → **because** the FPL API already includes this on every player record, so it required no new infrastructure, only new fields kept in the existing scheduled fetch → **trade-off accepted:** it's whatever FPL itself publishes as "news," not aggregated injury reporting from other sources.
- **Decision:** Don't compute "free transfers remaining" → **because** the public API doesn't expose it and deriving it correctly requires full transfer/wildcard history → **trade-off accepted:** managers still need the official app for that one number.

## How it works
A GitHub Action refreshes three things twice daily into static files: player prices/points/form, player status/news/availability, and upcoming fixture difficulty ratings — all from the official FPL `bootstrap-static` and `fixtures` endpoints, fetched server-side so CORS never applies. A Vercel serverless function (`api/team.js`) handles the personal path: given a team ID, it fetches that entry's current picks, gameweek-by-gameweek score history, and active chip, live, server-side. The frontend is one static page with four tabs sharing the same loaded player/team data: Planner (budget/quota/club-cap squad building), My Team (live lookup plus a "load into planner" action), Fixtures (difficulty by gameweek), and News (availability status).

## Outcome
Not yet measured with real users. What I'd track: which of the four tabs actually gets repeat use, since that tells me whether this earns its place as one tool versus should have stayed a narrower planner.

## What I'd do next
- Cross-reference the News tab against the Planner/My Team squads so a flagged player in your own squad is visually called out, not just listed separately.
- Extend the fixture view to a rolling difficulty score per player (sum of next-N-fixture difficulty) rather than gameweek-by-gameweek only.
- If real usage showed demand for genuine same-fixture historical comparison, the honest path is integrating a proper historical dataset (e.g. a maintained community project with match-level records) as its own scheduled ingestion — not approximating it from data that doesn't support the claim.

## AI/ML specifics
No model in this build. If extended toward transfer recommendations, the natural next step is a simple expected-points model per fixture (form + fixture difficulty + minutes risk + availability status, all of which the app already has), with inputs shown transparently so a user can see and override the reasoning — consistent with this project's running principle: show what's verifiable, and say plainly what isn't.
