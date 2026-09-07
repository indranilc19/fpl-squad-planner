# FPL Squad Planner

> A browser-based tool for building a Fantasy Premier League squad against live prices — no spreadsheet, no login, no live API call from the browser.

**Type:** Live demo &nbsp;|&nbsp; **Role:** Product (define + build) &nbsp;|&nbsp; **Timeframe:** —
**Live:** <fill in after deploy> &nbsp;|&nbsp; **Repo:** <fill in after `gh repo create`>

---

## The problem
Fantasy Premier League managers plan transfers against three constraints at once — a £100m budget, a fixed squad shape (2 GK / 5 DEF / 5 MID / 3 FWD), and a 3-players-per-club cap. Most people do this in a spreadsheet, re-checking the math by hand every time they swap a player. The FPL site itself only lets you plan inside an existing team, not sketch a squad from scratch.

## Who it's for
FPL managers doing pre-season or pre-deadline planning who want to test squad ideas quickly and see instantly whether an idea is legal and affordable.

## What I decided (and traded off)
- **Decision:** Don't call the FPL API from the browser at all — instead run a scheduled GitHub Action that fetches the data server-side and commits it into the repo → **because** the FPL API doesn't send CORS headers for browser origins, so a client-side call either fails outright or depends on a third-party CORS relay I don't control → **trade-off accepted:** data is only as fresh as the last scheduled run, not truly live.
- **Decision:** Refresh twice daily rather than hourly or on every page load → **because** FPL prices and stats don't move faster than that in practice, and I matched the cadence a production FPL data project (FPL-Core-Insights) actually uses, rather than guessing → **trade-off accepted:** a price change in the last few hours won't show until the next scheduled run; added a manual "run now" trigger in GitHub Actions for anyone who wants to force a refresh.
- **Decision:** Every data refresh commit triggers an automatic Vercel redeploy → **because** it means the live site updates itself with zero manual steps once it's set up → **trade-off accepted:** the site technically redeploys 2x/day whether or not the data actually changed (the workflow skips the commit if nothing changed, but that adds a small amount of pipeline complexity for a static site).
- **Decision:** Enforce budget, position quota, and the 3-per-club rule entirely client-side, no server validation → **because** this plans a hypothetical squad, it doesn't submit one to FPL, so there's nothing to protect → **trade-off accepted:** none of this data is authoritative against FPL's real rules if they change mid-season.
- **Decision:** Persist the in-progress squad in the browser's local storage rather than requiring an account → **because** the entire point is a zero-friction planning tool.

## How it works
A GitHub Action (`.github/workflows/refresh-data.yml`) runs on a cron schedule, executes a small Python script that calls the official FPL `bootstrap-static` endpoint, trims the payload to only the fields the app needs, and commits the result to `data/players.json`. That push triggers Vercel to redeploy automatically. The frontend — a single static HTML/JS file, no framework — fetches `data/players.json` as a same-origin request (no CORS involved at all) and runs all squad-building logic (budget, quota, club-cap checks) locally in the browser, persisting the in-progress squad to local storage.

## Outcome
Not yet measured with real users — this is a fresh build. What I'd track: time-to-first-legal-squad for a new user, and whether the twice-daily refresh cadence is tight enough in practice around price-change windows (FPL prices typically move overnight).

## What I'd do next
- Add a "who's about to change price" indicator using the `cost_change_event` field already in the FPL data, since that's a common pre-deadline question.
- Surface upcoming fixture difficulty per player — price and season points don't capture near-term matchup risk.
- If usage showed people wanting truly live prices, the next step would be a lightweight serverless function on a shorter cache window, not reverting to a client-side call.

## AI/ML specifics
No model in this build — it's deterministic squad-legality logic plus a scheduled ETL job, not a prediction problem. If extended, the natural next step is a simple expected-points model per fixture (form + fixture difficulty + minutes risk) to rank transfer targets, with the model's inputs shown transparently so a user can override it rather than trusting a black-box score.
