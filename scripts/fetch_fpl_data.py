"""
Fetches FPL bootstrap-static (players, teams, gameweek events) and fixtures,
writes trimmed data/players.json and data/fixtures.json into the repo. Runs
on GitHub's servers via the scheduled Action — not in the browser — so the
FPL API's lack of browser CORS headers never comes into play.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/?future=1"
PLAYERS_OUT = "data/players.json"
FIXTURES_OUT = "data/fixtures.json"

PLAYER_FIELDS = [
    "id", "first_name", "second_name", "team", "element_type",
    "now_cost", "total_points", "form",
    "status", "news", "news_added", "chance_of_playing_next_round",
    "selected_by_percent",
]
TEAM_FIELDS = ["id", "name", "short_name"]
FIXTURE_FIELDS = [
    "event", "kickoff_time", "team_h", "team_a",
    "team_h_difficulty", "team_a_difficulty", "finished",
]
# Gameweek context for the Gameweek control bar — deadline, current/next flags.
EVENT_FIELDS = ["id", "name", "deadline_time", "is_current", "is_next", "finished"]


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fpl-squad-planner/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    try:
        bootstrap = fetch_json(BOOTSTRAP_URL)
        fixtures_raw = fetch_json(FIXTURES_URL)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch FPL data: {exc}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    players = [{k: p.get(k) for k in PLAYER_FIELDS} for p in bootstrap.get("elements", [])]
    teams = [{k: t.get(k) for k in TEAM_FIELDS} for t in bootstrap.get("teams", [])]
    events = [{k: e.get(k) for k in EVENT_FIELDS} for e in bootstrap.get("events", [])]

    with open(PLAYERS_OUT, "w", encoding="utf-8") as f:
        json.dump(
            {"generated_at": now, "players": players, "teams": teams, "events": events},
            f, separators=(",", ":"),
        )

    upcoming = [f for f in fixtures_raw if f.get("event") is not None][:100]
    fixtures = [{k: fx.get(k) for k in FIXTURE_FIELDS} for fx in upcoming]
    with open(FIXTURES_OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now, "fixtures": fixtures}, f, separators=(",", ":"))

    print(f"Wrote {len(players)} players, {len(teams)} teams, {len(events)} events, {len(fixtures)} fixtures")


if __name__ == "__main__":
    main()
