"""Derive coherent basketball market values from one caller-supplied stat draw.

This is deterministic arithmetic, not a trained model, joint sampler, dependence
estimate or certification of an NBA box score. All seven base counts must be
supplied; missing counts are not silently replaced with observed zeroes.
"""
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class BasketballDraw:
    points: int
    rebounds: int
    assists: int
    threes_made: int
    turnovers: int
    blocks: int
    steals: int

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field.name} must be a nonnegative integer, not a boolean")
        if self.points < 3 * self.threes_made:
            raise ValueError("points must include at least three points per made three-pointer")

    def market_values(self) -> dict[str, int]:
        """Return totals and binary DD/TD events from exactly this same draw.

        Double/triple doubles count double-digit PTS, REB, AST, STL and BLK
        categories. Made threes and turnovers do not count. At least three
        qualifying categories also satisfies the at-least-two DD event.
        These are statistical outcomes; venue settlement remains separate.
        """
        qualifying = sum(value >= 10 for value in (
            self.points, self.rebounds, self.assists, self.steals, self.blocks,
        ))
        return {
            "PTS": self.points,
            "PRA": self.points + self.rebounds + self.assists,
            "REB": self.rebounds,
            "3PM": self.threes_made,
            "AST": self.assists,
            "RA": self.rebounds + self.assists,
            "PR": self.points + self.rebounds,
            "PA": self.points + self.assists,
            "TOV": self.turnovers,
            "TD": int(qualifying >= 3),
            "DD": int(qualifying >= 2),
            "BLK": self.blocks,
            "STL": self.steals,
            "BLK+STL": self.blocks + self.steals,
        }
