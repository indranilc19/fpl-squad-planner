# FPL Squad Planner

> A browser-based tool for building a Fantasy Premier League squad against live prices, and for pulling up your own team's current picks, bank, and chip status.

**Type:** Live demo &nbsp;|&nbsp; **Role:** Product (define + build) &nbsp;|&nbsp; **Timeframe:** —
**Live:** <fill in after deploy> &nbsp;|&nbsp; **Repo:** <fill in after `gh repo create`>

---

## The problem
Two related but distinct needs: (1) FPL managers planning transfers want to test squad ideas against a £100m budget, a fixed shape (2 GK/5 DEF/5 MID/3 FWD), and a 3-per-club cap, without a spreadsheet; (2) once they've made a squad, they want a quick read on their actual team — bank, value, chip used, transfer cost — without opening the FPL app.

## Who it's for
FPL managers doing pre-deadline planning, and managers who want a faster glance at their own team status than the official app gives.

## What I decided (and traded off)
- **Decision:** Use two different data-fetch strategies for two different data shapes, rather than forcing one pattern everywhere → **because** the player price list is shared and public (good fit for a scheduled job baking it into a static file), while a team lookup is personal and keyed by an ID typed in at runtime (can't be pre-baked for every possible team) → **trade-off accepted:** the app now has two moving parts — a GitHub Action and a serverless function — instead of one, which is more to maintain.
- **Decision:** For the personal lookup, add a small Vercel serverless function that proxies the FPL entry/picks endpoints server-side → **because** the FPL API has no CORS headers for browser origins, so a client-side call would fail the same way the player-list fetch originally did, and this data can't be pre-generated like the price list → **trade-off accepted:** adds a live network dependency the static player-list path doesn't have; if the FPL API is slow, the team lookup is slow.
- **Decision:** Don't attempt to compute or display "free transfers remaining" → **because** the public API doesn't expose it directly, and correctly deriving it requires the full transfer history including wildcard resets — getting it wrong would be worse than not showing it → **trade-off accepted:** managers have to go to the official app for that one number; I show what I can verify (transfers made and points cost this gameweek) and say plainly why the rest isn't shown.
- **Decision:** Keep the squad *planner* and the team *lookup* as separate tabs in one app rather than two projects → **because** they share the same player dataset and visual language, and a hiring manager sees more product thinking in one cohesive tool than two thin ones.

## How it works
A GitHub Action still refreshes `data/players.json` twice daily for the shared price list (unchanged from the original design). A new serverless function at `api/team.js` handles personal lookups: the browser calls it same-origin, it fetches the FPL `entry` and `entry/event/{gw}/picks` endpoints server-side, and returns the combined result. The frontend renders team meta (points, rank, bank, value, active chip) and the full squad with captain/vice-captain tags, using the already-loaded player list to resolve names and positions.

## Outcome
Not yet measured with real users. What I'd track: how often the team-lookup path actually gets used versus the planner, since that tells me whether the two-tool-in-one bet was right.

## What I'd do next
- Cache team lookups briefly (the function already sets a short `Cache-Control` header) to avoid hammering the FPL API if the same team ID gets looked up repeatedly.
- Let a user load their own team directly *into* the planner as a starting point for "what if I made this transfer," rather than keeping the two tabs fully separate.
- If free-transfer tracking became a real user need, the correct fix is asking the user to confirm their last wildcard/transfer state once, not guessing from public data.

## AI/ML specifics
No model in this build. If extended toward transfer recommendations, the natural next step is a simple expected-points model per fixture, with its inputs shown transparently so a user can override it rather than trust a black-box suggestion — same principle as the free-transfers decision above: don't present a number as fact when the underlying data doesn't actually support it.
