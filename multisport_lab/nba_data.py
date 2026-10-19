"""Offline NBA boxscore normalization and bounded data-quality summaries.

These adapters establish field meaning, not historical pregame availability or
source permission. Namespaced source IDs remain source IDs; there is no implicit
ESPN-to-NBA identity mapping. Raw source files do not belong in public exports.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


COUNT_FIELDS = (
    "points", "fgm", "fga", "fg2m", "fg3m", "fg3a", "ftm", "fta",
    "oreb", "dreb", "rebounds", "assists", "turnovers", "blocks", "steals",
)
SDV_FIELDS = {
    "points": "points", "fgm": "field_goals_made",
    "fga": "field_goals_attempted", "fg3m": "three_point_field_goals_made",
    "fg3a": "three_point_field_goals_attempted", "ftm": "free_throws_made",
    "fta": "free_throws_attempted", "oreb": "offensive_rebounds",
    "dreb": "defensive_rebounds", "rebounds": "rebounds", "assists": "assists",
    "turnovers": "turnovers", "blocks": "blocks", "steals": "steals",
}
NBA_FIELDS = {
    "points": "points", "fgm": "fieldGoalsMade", "fga": "fieldGoalsAttempted",
    "fg3m": "threePointersMade", "fg3a": "threePointersAttempted",
    "ftm": "freeThrowsMade", "fta": "freeThrowsAttempted",
    "oreb": "reboundsOffensive", "dreb": "reboundsDefensive",
    "rebounds": "reboundsTotal", "assists": "assists", "turnovers": "turnovers",
    "blocks": "blocks", "steals": "steals",
}


def _id(value: Any, field: str) -> str:
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and value and value == value.strip():
        return value
    raise ValueError(f"{field} needs a nonempty source ID")


def _count(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} needs a nonnegative integer or null")
    return value


def parse_minutes(value: Any, *, encoding: str) -> float | None:
    """Parse declared units; a zero value never establishes nonparticipation."""
    if value is None or value == "":
        return None
    if encoding == "decimal_minutes":
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("minutes needs a finite nonnegative number")
        return float(value)
    if encoding == "clock":
        if not isinstance(value, str):
            raise ValueError("clock minutes needs a string")
        match = re.fullmatch(r"(?:PT)?(\d+)(?::|M)(\d{2}(?:\.\d+)?)(?:S)?", value)
        if not match or float(match[2]) >= 60:
            raise ValueError("minutes needs MM:SS or PTMM M SS S clock units")
        return int(match[1]) + float(match[2]) / 60
    raise ValueError("undeclared minutes encoding")


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("event_start needs an aware timestamp")
    return value.astimezone(timezone.utc)


def _strict_json(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("nonfinite JSON number")
        return number

    def invalid_constant(value):
        raise ValueError(f"invalid JSON constant {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_float=finite_float,
                      parse_constant=invalid_constant)


@dataclass(frozen=True)
class NBAPlayerGame:
    id_namespace: str
    event_id: str
    player_id: str
    team_id: str
    opponent_id: str
    season_ending_year: int
    season_type: str
    event_start: datetime
    participation: str
    minutes: float | None
    minutes_precision: str
    points: int | None
    fgm: int | None
    fga: int | None
    fg2m: int | None
    fg3m: int | None
    fg3a: int | None
    ftm: int | None
    fta: int | None
    oreb: int | None
    dreb: int | None
    rebounds: int | None
    assists: int | None
    turnovers: int | None
    blocks: int | None
    steals: int | None
    final_status: str = "UNKNOWN"
    final_periods: int | None = None

    def __post_init__(self) -> None:
        for field in ("id_namespace", "event_id", "player_id", "team_id", "opponent_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"invalid {field}")
        if self.team_id == self.opponent_id:
            raise ValueError("team and opponent IDs must differ")
        if type(self.season_ending_year) is not int or self.season_ending_year < 1947:
            raise ValueError("invalid NBA season ending year")
        if not isinstance(self.season_type, str) or not self.season_type:
            raise ValueError("season_type needs an explicit source value")
        object.__setattr__(self, "event_start", _timestamp(self.event_start))
        if self.participation not in {"APPEARED", "DNP", "UNKNOWN"}:
            raise ValueError("unknown participation state")
        if self.minutes_precision not in {"seconds", "rounded_whole_minutes", "unknown"}:
            raise ValueError("unknown minutes precision")
        if self.minutes is not None:
            parse_minutes(self.minutes, encoding="decimal_minutes")
            if self.minutes_precision == "rounded_whole_minutes" and self.minutes % 1:
                raise ValueError("fractional minutes conflict with whole-minute precision")
        for field in COUNT_FIELDS:
            _count(getattr(self, field), field)
        if self.participation == "DNP" and (
            self.minutes is not None or any(getattr(self, f) is not None for f in COUNT_FIELDS)
        ):
            raise ValueError("DNP outcomes must be null, not statistical zeros")
        if self.participation == "APPEARED" and self.minutes == 0 and self.minutes_precision == "seconds":
            raise ValueError("zero exact minutes does not verify an appearance")
        if self.final_status not in {"FINAL", "NOT_FINAL", "UNKNOWN"}:
            raise ValueError("unknown final status")
        if self.final_periods is not None and (
            type(self.final_periods) is not int or self.final_periods < 4 or self.final_status != "FINAL"
        ):
            raise ValueError("final periods require a completed standard NBA game")
        if self.game_duration_minutes is not None and self.minutes is not None:
            # Rounding is retained, never silently clipped into a valid share.
            if self.minutes > self.game_duration_minutes:
                raise ValueError("player minutes exceed verified game duration")

    @property
    def game_duration_minutes(self) -> int | None:
        return None if self.final_periods is None else 48 + 5 * (self.final_periods - 4)

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.id_namespace, self.event_id, self.player_id

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["event_start"] = self.event_start.isoformat()
        record["game_duration_minutes"] = self.game_duration_minutes
        return record


def _counts(raw: Mapping[str, Any], fields: Mapping[str, str]) -> dict[str, int | None]:
    values = {field: _count(raw.get(source), field) for field, source in fields.items()}
    fgm, fg3m = values["fgm"], values["fg3m"]
    values["fg2m"] = None if fgm is None or fg3m is None else fgm - fg3m
    _count(values["fg2m"], "fg2m")
    return values


def normalize_sdv_row(raw: Mapping[str, Any]) -> NBAPlayerGame:
    """Normalize the inspected hoopR ESPN release schema, preserving nulls."""
    dnp = raw.get("did_not_play")
    if dnp is not None and type(dnp) is not bool:
        raise ValueError("did_not_play must be a source Boolean or null")
    participation = "UNKNOWN" if dnp is None else "DNP" if dnp else "APPEARED"
    return NBAPlayerGame(
        id_namespace="espn", event_id=_id(raw.get("game_id"), "game_id"),
        player_id=_id(raw.get("athlete_id"), "athlete_id"),
        team_id=_id(raw.get("team_id"), "team_id"),
        opponent_id=_id(raw.get("opponent_team_id"), "opponent_team_id"),
        season_ending_year=raw.get("season"), season_type=str(raw.get("season_type", "UNKNOWN")),
        event_start=_timestamp(raw.get("game_date_time")), participation=participation,
        minutes=parse_minutes(raw.get("minutes"), encoding="decimal_minutes"),
        minutes_precision="rounded_whole_minutes", **_counts(raw, SDV_FIELDS),
    )


def normalize_sdv_rows(
    raw_rows: Iterable[Mapping[str, Any]], *, max_rows: int = 100_000
) -> tuple[list[NBAPlayerGame], list[dict[str, Any]]]:
    """Keep invalid identity/field rows in diagnostics, never guess repairs."""
    if type(max_rows) is not int or max_rows <= 0:
        raise ValueError("max_rows must be a positive integer")
    rows, rejected = [], []
    for index, raw in enumerate(raw_rows):
        if index >= max_rows:
            raise ValueError("normalization exceeds declared row budget")
        try:
            rows.append(normalize_sdv_row(raw))
        except (ValueError, TypeError) as error:
            rejected.append({"source_row_index": index, "event_id": str(raw.get("game_id")),
                             "reason": str(error)})
    return rows, rejected


def with_sdv_schedule(
    row: NBAPlayerGame, schedule: Mapping[str, Any], *, standard_team_ids: frozenset[str]
) -> NBAPlayerGame:
    """Join separate final-status evidence; never infer finality from a stat row.

    Standard NBA playing duration is admitted only for an explicit caller-owned
    team inventory and four-regulation-period format. Exhibition mini-games in
    the inspected release also have season_type=2 and must not acquire 48-minute
    duration merely from their season label.
    """
    if row.id_namespace != "espn" or row.event_id != _id(schedule.get("game_id"), "game_id"):
        raise ValueError("schedule and player event identity disagree")
    home, away = _id(schedule.get("home_id"), "home_id"), _id(schedule.get("away_id"), "away_id")
    if {row.team_id, row.opponent_id} != {home, away}:
        raise ValueError("schedule and player team identity disagree")
    if row.season_ending_year != schedule.get("season") or row.season_type != str(schedule.get("season_type")):
        raise ValueError("schedule and player season disagree")
    if row.event_start != _timestamp(schedule.get("game_date_time")):
        raise ValueError("schedule and player archived event times disagree")
    completed = schedule.get("status_type_completed")
    if type(completed) is not bool:
        raise ValueError("schedule completion evidence must be Boolean")
    if not completed:
        return replace(row, final_status="NOT_FINAL", final_periods=None)
    if schedule.get("status_type_state") != "post" or schedule.get("status_type_name") != "STATUS_FINAL":
        raise ValueError("schedule completion evidence conflicts with status")
    periods = None
    if home in standard_team_ids and away in standard_team_ids and schedule.get("format_regulation_periods") == 4:
        value = schedule.get("status_period")
        if type(value) not in (int, float) or not math.isfinite(value) or value < 4 or value % 1:
            raise ValueError("invalid standard NBA final period count")
        # The inspected archive resets many final clocks to a period's start.
        # Its explicit FINAL status still establishes archived completion, but
        # conflicting clock evidence does not establish completed playing time.
        if schedule.get("status_clock") == 0:
            periods = int(value)
    return replace(row, final_status="FINAL", final_periods=periods)


def extract_nba_game(html: str) -> Mapping[str, Any]:
    """Read the public game's embedded JSON; no requests or access bypasses."""
    if len(html) > 5_000_000:
        raise ValueError("NBA page exceeds bounded input size")
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        raise ValueError("NBA page has no embedded game evidence")
    payload = _strict_json(match[1])
    game = payload["props"]["pageProps"]["game"]
    if not isinstance(game, dict):
        raise ValueError("NBA game evidence must be an object")
    return game


def normalize_nba_game(
    game: Mapping[str, Any], *, season_ending_year: int, season_type: str
) -> list[NBAPlayerGame]:
    """Normalize official public-game JSON, including explicit DNP comments.

    NBA's blank-minute DNP rows contain zero placeholders. Only an explicit
    DNP/DND comment authorizes converting those placeholders to null outcomes.
    """
    final = game.get("gameStatus") == 3
    periods = game.get("period") if final else None
    if final:
        recorded_periods = [p["period"] for side in ("homeTeam", "awayTeam") for p in game[side]["periods"]]
        if type(periods) is not int or not recorded_periods or max(recorded_periods) != periods:
            raise ValueError("final period count disagrees with official period evidence")
    rows = []
    for side, other in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
        for player in game[side]["players"]:
            stats = player["statistics"]
            minutes = parse_minutes(stats.get("minutes"), encoding="clock")
            comment = player.get("comment", "")
            explicit_dnp = isinstance(comment, str) and comment.startswith(("DNP", "DND"))
            counts = _counts(stats, NBA_FIELDS)
            if explicit_dnp:
                if minutes is not None or any(value not in (None, 0) for value in counts.values()):
                    raise ValueError("official DNP has contradictory production")
                participation, counts = "DNP", dict.fromkeys(COUNT_FIELDS)
            else:
                participation = "APPEARED" if minutes is not None and minutes > 0 else "UNKNOWN"
            rows.append(NBAPlayerGame(
                id_namespace="nba", event_id=_id(game.get("gameId"), "gameId"),
                player_id=_id(player.get("personId"), "personId"),
                team_id=_id(game[side].get("teamId"), "teamId"),
                opponent_id=_id(game[other].get("teamId"), "opponentId"),
                season_ending_year=season_ending_year, season_type=season_type,
                event_start=_timestamp(game.get("gameTimeUTC")), participation=participation,
                minutes=minutes, minutes_precision="seconds", final_status="FINAL" if final else "NOT_FINAL",
                final_periods=periods, **counts,
            ))
    return rows


def audit_rows(rows: Iterable[NBAPlayerGame], *, max_rows: int = 100_000) -> dict[str, Any]:
    """Summarize, without deduplicating revisions or filling missing values."""
    if type(max_rows) is not int or max_rows <= 0:
        raise ValueError("max_rows must be a positive integer")
    identities: Counter = Counter()
    participation: Counter = Counter()
    seasons: Counter = Counter()
    missing = Counter({f: 0 for f in ("minutes", *COUNT_FIELDS)})
    zeros = missing.copy()
    failures: Counter = Counter()
    games, players, teams = set(), set(), set()
    count = known_final = verified_duration = 0
    for row in rows:
        count += 1
        if count > max_rows:
            raise ValueError("audit exceeds declared row budget")
        identities[row.identity] += 1
        participation[row.participation] += 1
        games.add((row.id_namespace, row.event_id))
        players.add((row.id_namespace, row.player_id))
        teams.add((row.id_namespace, row.team_id))
        seasons[f"{row.season_ending_year}:{row.season_type}"] += 1
        known_final += row.final_status == "FINAL"
        verified_duration += row.game_duration_minutes is not None
        if row.participation != "APPEARED":
            continue
        for field in missing:
            missing[field] += getattr(row, field) is None
            zeros[field] += getattr(row, field) == 0
        checks = {
            "scoring": (row.points, row.fg2m, row.fg3m, row.ftm),
            "rebounds": (row.rebounds, row.oreb, row.dreb),
        }
        if None not in checks["scoring"] and row.points != 2 * row.fg2m + 3 * row.fg3m + row.ftm:
            failures["scoring_identity"] += 1
        if None not in checks["rebounds"] and row.rebounds != row.oreb + row.dreb:
            failures["rebound_identity"] += 1
        for made, attempted in (("fgm", "fga"), ("fg3m", "fg3a"), ("ftm", "fta")):
            a, b = getattr(row, made), getattr(row, attempted)
            if a is not None and b is not None and a > b:
                failures[f"{made}_exceeds_attempts"] += 1
    return {
        "row_count": count, "event_count": len(games), "player_count": len(players),
        "team_count": len(teams), "participation": dict(participation),
        "seasons": dict(seasons), "duplicate_event_player_rows": sum(n - 1 for n in identities.values()),
        "appearance_missing_fields": dict(missing), "appearance_zero_fields": dict(zeros),
        "identity_failures": dict(failures), "rows_with_verified_final_status": known_final,
        "rows_with_verified_duration": verified_duration,
        "claims": {"historical_asof_verified": False, "pregame_roster_verified": False,
                   "model_evaluated": False, "source_permission_established": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--format", choices=("sdv-json", "nba-html"), required=True)
    parser.add_argument("--season-ending-year", type=int)
    parser.add_argument("--season-type")
    parser.add_argument("--max-rows", type=int, default=100_000)
    args = parser.parse_args()
    if args.input.stat().st_size > 32_000_000:
        parser.error("input exceeds the 32 MB offline audit budget")
    data = args.input.read_text()
    if args.format == "sdv-json":
        raw = _strict_json(data)
        if not isinstance(raw, list) or len(raw) > args.max_rows:
            parser.error("SDV input must be a list within the declared row budget")
        rows, rejected = normalize_sdv_rows(raw, max_rows=args.max_rows)
    else:
        if args.season_ending_year is None or args.season_type is None:
            parser.error("official NBA import requires explicit season ending year and season type")
        rows = normalize_nba_game(extract_nba_game(data), season_ending_year=args.season_ending_year,
                                  season_type=args.season_type)
        rejected = []
    report = audit_rows(rows, max_rows=args.max_rows)
    report["rejected_source_rows"] = rejected
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
