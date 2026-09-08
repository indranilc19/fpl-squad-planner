"""
Fetch FPL bootstrap-static (players, teams, gameweek events), fixtures, and the
configured manager's current team snapshot. Runs on GitHub's servers via the
scheduled Action — not in the browser — so the FPL API's lack of browser CORS
headers never comes into play.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/?future=1"
TEAM_ID = 2160927
TEAM_URL = f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/"
TEAM_HISTORY_URL = f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/history/"
TEAM_PICKS_URL = f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/event/{{event}}/picks/"
PLAYERS_OUT = "data/players.json"
FIXTURES_OUT = "data/fixtures.json"
TEAM_OUT = "data/team.json"

PLAYER_FIELDS = [
    "id", "first_name", "second_name", "web_name", "team", "element_type",
    "now_cost", "total_points", "form", "status", "news",
    "chance_of_playing_next_round", "selected_by_percent",
]
TEAM_FIELDS = ["id", "name", "short_name"]
FIXTURE_FIELDS = [
    "event", "kickoff_time", "team_h", "team_a",
    "team_h_difficulty", "team_a_difficulty", "finished",
]
EVENT_FIELDS = ["id", "name", "deadline_time", "is_current", "is_next", "finished"]


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fpl-squad-planner/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    try:
        bootstrap = fetch_json(BOOTSTRAP_URL)
        fixtures_raw = fetch_json(FIXTURES_URL)
        team_entry = fetch_json(TEAM_URL)
        team_history = fetch_json(TEAM_HISTORY_URL)

        finished_events = [e for e in bootstrap.get("events", []) if e.get("finished")]
        current_events = [e for e in bootstrap.get("events", []) if e.get("is_current")]
        candidates = current_events or finished_events[-1:]
        target_event = candidates[-1] if candidates else None
        target_gw = target_event.get("id") if target_event else None
        team_picks = fetch_json(TEAM_PICKS_URL.format(event=target_gw)) if target_gw else {}
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch FPL data: {exc}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    players = [{k: p.get(k) for k in PLAYER_FIELDS} for p in bootstrap.get("elements", [])]
    teams = [{k: t.get(k) for k in TEAM_FIELDS} for t in bootstrap.get("teams", [])]
    events = [{k: e.get(k) for k in EVENT_FIELDS} for e in bootstrap.get("events", [])]

    with open(PLAYERS_OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now, "players": players, "teams": teams, "events": events}, f, separators=(",", ":"))

    upcoming = [f for f in fixtures_raw if f.get("event") is not None][:100]
    fixtures = [{k: fx.get(k) for k in FIXTURE_FIELDS} for fx in upcoming]
    with open(FIXTURES_OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now, "fixtures": fixtures}, f, separators=(",", ":"))

    team_snapshot = {
        "generated_at": now,
        "team_id": TEAM_ID,
        "gameweek": target_gw,
        "entry": team_entry,
        "history": team_history,
        "picks": team_picks,
    }
    with open(TEAM_OUT, "w", encoding="utf-8") as f:
        json.dump(team_snapshot, f, separators=(",", ":"))

    print(f"Wrote {len(players)} players, {len(teams)} teams, {len(events)} events, {len(fixtures)} fixtures and team {TEAM_ID} GW{target_gw} snapshot")


if __name__ == "__main__":
    main()
