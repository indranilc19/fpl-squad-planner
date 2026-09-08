"""Build a position-balanced Top 30 FPL analysis dataset with fixture-specific history.

The ranking is deliberately fixture-aware. For each current player we inspect the
next five fixtures and combine:
- current FPL form/value/availability;
- multi-season historical output;
- historical gameweek-by-gameweek performance against each upcoming opponent;
- whether those historical meetings were home or away;
- the current FPL difficulty rating for each upcoming fixture.

Vaastav's 2024-25 merged GW file has a documented total_points issue for GW22-38,
so matchup history uses 2024-25 only through GW21 and uses all GWs for 2022-23 and
2023-24. The cleaned season totals can still be used for the broader historical
signal. Historical xP/ep is never used because it can contain lookahead bias.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYERS_FILE = ROOT / "data" / "players.json"
OUTPUT_FILE = ROOT / "data" / "analysis.json"
BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
SEASONS = ["2022-23", "2023-24", "2024-25"]
SEASON_WEIGHT = {"2022-23": 0.20, "2023-24": 0.30, "2024-25": 0.50}
POSITION_MAP = {"1": "GK", "2": "DEF", "3": "MID", "4": "FWD", "GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD", "GKP": "GK"}
TOP30_QUOTA = {"GK": 4, "DEF": 10, "MID": 10, "FWD": 6}
WEIGHTS = {
    "GK": {"history": 0.22, "current": 0.15, "value": 0.08, "fixture": 0.15, "matchup": 0.28, "minutes": 0.07, "availability": 0.05},
    "DEF": {"history": 0.20, "current": 0.15, "value": 0.08, "fixture": 0.15, "matchup": 0.27, "minutes": 0.10, "availability": 0.05},
    "MID": {"history": 0.20, "current": 0.15, "value": 0.08, "fixture": 0.15, "matchup": 0.27, "minutes": 0.10, "availability": 0.05},
    "FWD": {"history": 0.20, "current": 0.15, "value": 0.08, "fixture": 0.15, "matchup": 0.27, "minutes": 0.10, "availability": 0.05},
}


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return text


def fnum(row: dict, key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key)
        if value in (None, "", "None"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fetch_csv(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "fpl-squad-planner/1.0"})
    response = urllib.request.urlopen(req, timeout=60)
    return csv.DictReader(line.decode("utf-8") if isinstance(line, bytes) else line for line in response)


def pct_rank(values: list[float], value: float) -> float:
    clean = [v for v in values if math.isfinite(v)]
    if not clean:
        return 50.0
    return 100.0 * sum(v <= value for v in clean) / len(clean)


def inverse_pct(values: list[float], value: float) -> float:
    return 100.0 - pct_rank(values, value)


def load_season_totals() -> dict[str, list[dict]]:
    history = defaultdict(list)
    for season in SEASONS:
        try:
            reader = fetch_csv(f"{BASE}/{season}/cleaned_players.csv")
            for row in reader:
                pos = POSITION_MAP.get((row.get("element_type") or "").strip().upper())
                key = norm(f"{row.get('first_name','')} {row.get('second_name','')}")
                if pos and key:
                    row["season"] = season
                    row["position"] = pos
                    history[key].append(row)
        except Exception as exc:
            print(f"Warning: season totals {season}: {exc}", file=sys.stderr)
    return history


def weighted_history(rows: list[dict]) -> dict:
    by_season = {r["season"]: r for r in rows}
    weights = {s: SEASON_WEIGHT[s] for s in SEASONS if s in by_season}
    total = sum(weights.values())
    if not total:
        return {"points": 0.0, "minutes": 0.0, "goals": 0.0, "assists": 0.0, "clean_sheets": 0.0}

    def avg(field: str) -> float:
        return sum(fnum(by_season[s], field) * w for s, w in weights.items()) / total

    minutes = avg("minutes")
    return {
        "points": avg("total_points"),
        "minutes": minutes,
        "goals": avg("goals_scored"),
        "assists": avg("assists"),
        "clean_sheets": avg("clean_sheets"),
    }


def load_matchup_history(candidate_names: set[str]) -> tuple[dict, list[str]]:
    """Return player/opponent/venue aggregates from historical GW files."""
    aggregate = defaultdict(lambda: {"rows": 0, "points": 0.0, "minutes": 0.0, "weighted_points": 0.0, "weighted_minutes": 0.0})
    all_history = defaultdict(lambda: {"rows": 0, "points": 0.0, "minutes": 0.0})
    warnings = []

    for season in SEASONS:
        # The repository documents incorrect total_points in 2024-25 GW22-38.
        max_gw = 21 if season == "2024-25" else 38
        try:
            teams_reader = fetch_csv(f"{BASE}/{season}/teams.csv")
            team_names = {}
            for row in teams_reader:
                team_names[int(float(row.get("id", 0)))] = norm(row.get("name"))

            reader = fetch_csv(f"{BASE}/{season}/gws/merged_gw.csv")
            for row in reader:
                name = norm(row.get("name"))
                if name not in candidate_names:
                    continue
                gw = int(fnum(row, "round", 0))
                if not gw or gw > max_gw:
                    continue
                opponent = team_names.get(int(fnum(row, "opponent_team", 0)), "")
                if not opponent:
                    continue
                home = str(row.get("was_home", "")).strip().lower() in {"true", "1", "yes"}
                venue = "H" if home else "A"
                points = fnum(row, "total_points")
                minutes = fnum(row, "minutes")
                weight = SEASON_WEIGHT[season]
                key = (name, opponent, venue)
                aggregate[key]["rows"] += 1
                aggregate[key]["points"] += points
                aggregate[key]["minutes"] += minutes
                aggregate[key]["weighted_points"] += points * weight
                aggregate[key]["weighted_minutes"] += minutes * weight
                overall_key = (name, opponent, "ALL")
                aggregate[overall_key]["rows"] += 1
                aggregate[overall_key]["points"] += points
                aggregate[overall_key]["minutes"] += minutes
                aggregate[overall_key]["weighted_points"] += points * weight
                aggregate[overall_key]["weighted_minutes"] += minutes * weight
                all_history[name]["rows"] += 1
                all_history[name]["points"] += points
                all_history[name]["minutes"] += minutes
        except Exception as exc:
            warnings.append(f"{season} GW history unavailable: {exc}")

    return aggregate, warnings


def matchup_stat(aggregate: dict, player_name: str, opponent_name: str, venue: str, prior_ppg: float) -> dict:
    """Bayesian-shrink venue-specific history toward opponent and player priors."""
    overall = aggregate.get((player_name, opponent_name, "ALL"), {"rows": 0, "weighted_points": 0.0, "weighted_minutes": 0.0})
    venue_row = aggregate.get((player_name, opponent_name, venue), {"rows": 0, "weighted_points": 0.0, "weighted_minutes": 0.0})
    prior_matches = 3.0
    overall_ppg = (overall["weighted_points"] / max(overall["rows"], 1)) if overall["rows"] else prior_ppg
    venue_ppg = (venue_row["weighted_points"] / max(venue_row["rows"], 1)) if venue_row["rows"] else overall_ppg
    if venue_row["rows"]:
        # Strong venue signal when we have repeated meetings, but never let a tiny sample dominate.
        venue_shrunk = (venue_row["weighted_points"] + overall_ppg * prior_matches) / (venue_row["rows"] + prior_matches)
        effective = venue_shrunk * 0.70 + overall_ppg * 0.30
    elif overall["rows"]:
        effective = (overall["weighted_points"] + prior_ppg * prior_matches) / (overall["rows"] + prior_matches)
    else:
        effective = prior_ppg
    return {
        "ppg": round(effective, 2),
        "matches": int(venue_row["rows"] or overall["rows"]),
        "venue_matches": int(venue_row["rows"]),
        "overall_ppg": round(overall_ppg, 2),
        "venue_ppg": round(venue_ppg, 2),
    }


def build() -> None:
    current = json.loads(PLAYERS_FILE.read_text(encoding="utf-8"))
    players = current.get("players", [])
    teams = {int(t["id"]): t for t in current.get("teams", []) if "id" in t}
    fixtures = json.loads((ROOT / "data" / "fixtures.json").read_text(encoding="utf-8")).get("fixtures", []) if (ROOT / "data" / "fixtures.json").exists() else []
    events = current.get("events", [])
    selected_gw = next((e["id"] for e in events if e.get("is_next")), None) or next((e["id"] for e in events if e.get("is_current")), 1)

    season_totals = load_season_totals()
    candidates = []
    candidate_names = set()
    for p in players:
        pos = POSITION_MAP.get(str(p.get("element_type")).strip().upper())
        key = norm(f"{p.get('first_name','')} {p.get('second_name','')}")
        if pos and key:
            candidate_names.add(key)
            candidates.append({"raw": p, "pos": pos, "name_key": key, "history": weighted_history(season_totals.get(key, []))})

    matchup, warnings = load_matchup_history(candidate_names)
    by_pos = defaultdict(list)
    for c in candidates:
        by_pos[c["pos"]].append(c)

    for pos, group in by_pos.items():
        fixture_avgs = {}
        matchup_values = {}
        for c in group:
            p = c["raw"]
            team_id = int(p.get("team") or 0)
            upcoming = [f for f in fixtures if f.get("event") is not None and f.get("event") >= selected_gw and (f.get("team_h") == team_id or f.get("team_a") == team_id)]
            upcoming.sort(key=lambda x: (x.get("event") or 999, x.get("kickoff_time") or ""))
            upcoming = upcoming[:5]
            diffs = []
            fixture_details = []
            hist_ppgs = []
            prior_ppg = c["history"]["points"] / max(c["history"]["minutes"] / 90.0, 1.0) if c["history"]["minutes"] else max(fnum(p, "total_points") / max(fnum(p, "minutes") / 90.0, 1.0), 2.0)
            for fx in upcoming:
                home = fx.get("team_h") == team_id
                opp_id = fx.get("team_a") if home else fx.get("team_h")
                opp_name = norm(teams.get(int(opp_id or 0), {}).get("name", ""))
                venue = "H" if home else "A"
                diff = int(fnum(fx, "team_h_difficulty" if home else "team_a_difficulty", 3))
                mh = matchup_stat(matchup, c["name_key"], opp_name, venue, prior_ppg)
                diffs.append(diff)
                hist_ppgs.append(mh["ppg"])
                fixture_details.append({
                    "gw": int(fx.get("event")), "opponent": teams.get(int(opp_id or 0), {}).get("short_name", "—"),
                    "home": home, "difficulty": diff, "historical_ppg": mh["ppg"],
                    "historical_matches": mh["matches"], "venue_matches": mh["venue_matches"],
                    "historical_venue_ppg": mh["venue_ppg"],
                })
            fixture_avgs[p["id"]] = sum(diffs) / len(diffs) if diffs else 3.0
            matchup_values[p["id"]] = sum(hist_ppgs) / len(hist_ppgs) if hist_ppgs else prior_ppg
            c["fixtures"] = fixture_details
            c["matchup_ppg"] = matchup_values[p["id"]]

        pools = {
            "history": [c["history"]["points"] for c in group],
            "current": [fnum(c["raw"], "form") for c in group],
            "value": [fnum(c["raw"], "total_points") / max(fnum(c["raw"], "now_cost") / 10.0, 1.0) for c in group],
            "fixture": list(fixture_avgs.values()),
            "matchup": list(matchup_values.values()),
            "minutes": [c["history"]["minutes"] for c in group],
        }

        for c in group:
            p, hist = c["raw"], c["history"]
            fixture_avg = fixture_avgs[p["id"]]
            matchup_ppg = matchup_values[p["id"]]
            chance = p.get("chance_of_playing_next_round")
            availability = 100.0 if chance in (None, "") else max(0.0, min(100.0, fnum(p, "chance_of_playing_next_round")))
            parts = {
                "history": pct_rank(pools["history"], hist["points"]),
                "current": pct_rank(pools["current"], fnum(p, "form")),
                "value": pct_rank(pools["value"], fnum(p, "total_points") / max(fnum(p, "now_cost") / 10.0, 1.0)),
                "fixture": inverse_pct(pools["fixture"], fixture_avg),
                "matchup": pct_rank(pools["matchup"], matchup_ppg),
                "minutes": pct_rank(pools["minutes"], hist["minutes"]),
                "availability": availability,
            }
            score = sum(parts[k] * w for k, w in WEIGHTS[pos].items()) / sum(WEIGHTS[pos].values())
            seasons_found = len(season_totals.get(c["name_key"], []))
            confidence = "High" if hist["minutes"] >= 2000 and seasons_found >= 2 and matchup_ppg > 0 else "Medium" if hist["minutes"] >= 800 or matchup_ppg > 0 else "Low"

            reasons = []
            if parts["matchup"] >= 80:
                reasons.append(f"Strong vs next-5 opponents ({matchup_ppg:.1f} pts/match)")
            elif parts["matchup"] <= 30:
                reasons.append(f"Weak vs next-5 opponents ({matchup_ppg:.1f} pts/match)")
            if any(x["venue_matches"] >= 2 for x in c["fixtures"]):
                reasons.append("Home/away history included")
            if parts["fixture"] >= 75: reasons.append("Favourable next-5 FDR")
            elif parts["fixture"] <= 30: reasons.append("Difficult next-5 FDR")
            if parts["current"] >= 75: reasons.append("Excellent current form")
            elif parts["current"] >= 60: reasons.append("Positive recent form")
            if parts["history"] >= 75: reasons.append("Strong multi-season output")
            if parts["minutes"] >= 75: reasons.append("Reliable minutes profile")
            if availability < 100: reasons.append(f"{int(availability)}% next-GW chance")
            if not reasons: reasons.append("Balanced form, history and fixture profile")

            c["analysis"] = {
                "score": round(score, 1), "confidence": confidence,
                "team": teams.get(int(p.get("team") or 0), {}).get("short_name", "—"),
                "price": round(fnum(p, "now_cost") / 10.0, 1), "form": round(fnum(p, "form"), 1),
                "points": int(fnum(p, "total_points")), "historical_points": round(hist["points"], 1),
                "historical_minutes": int(hist["minutes"]), "value": round(fnum(p, "total_points") / max(fnum(p, "now_cost") / 10.0, 1.0), 2),
                "fixture_avg": round(fixture_avg, 2), "matchup_ppg": round(matchup_ppg, 2),
                "availability": int(availability), "next_fixtures": c["fixtures"], "reasons": reasons[:4],
            }

    final = []
    for pos, quota in TOP30_QUOTA.items():
        role_players = [c for c in candidates if c["pos"] == pos and "analysis" in c]
        role_players.sort(key=lambda c: c["analysis"]["score"], reverse=True)
        for position_rank, c in enumerate(role_players[:quota], 1):
            p, a = c["raw"], c["analysis"]
            final.append({
                "rank": 0, "position_rank": position_rank, "id": p.get("id"),
                "first_name": p.get("first_name"), "second_name": p.get("second_name"),
                "web_name": p.get("web_name", p.get("second_name")), "position": pos, **a,
            })
    final.sort(key=lambda x: x["score"], reverse=True)
    for rank, item in enumerate(final, 1): item["rank"] = rank

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Vaastav FPL season totals + gameweek history (2022-23, 2023-24, 2024-25 through GW21) + current FPL snapshot",
        "historical_seasons": SEASONS, "top30_quota": TOP30_QUOTA, "position_ratio": "2:5:5:3",
        "next_fixture_count": 5, "weights": WEIGHTS,
        "selection_notes": [
            "Ranking is position-balanced: 4 GK, 10 DEF, 10 MID, 6 FWD.",
            "The next five fixtures directly affect the score; current FPL FDR is combined with player-specific historical performance against those opponents.",
            "Historical matchup performance is split by home/away. Venue samples are shrunk toward the player's broader opponent record so one match cannot dominate.",
            "Historical seasons are weighted 50% 2024-25, 30% 2023-24 and 20% 2022-23 when available.",
            "2024-25 GW22-38 are excluded from matchup history because the source repository documents incorrect total_points values for those gameweeks.",
            "Historical xP/ep fields are excluded because the source repository warns they can contain lookahead information.",
        ],
        "warnings": warnings,
        "players": final,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"Built {len(final)} Top 30 players with five-fixture matchup history")


if __name__ == "__main__":
    build()
