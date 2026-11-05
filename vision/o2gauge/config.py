"""Monitor configuration. Defaults live in contract/monitor_config.default.json so
Python, Kotlin, Cloud Functions and the dashboard all read the same numbers.

!! LOW / CRITICAL thresholds are PLACEHOLDERS until Babu sir / the biomedical
!! engineer confirms them. They are configurable (Firestore devices/{id}.config).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "contract" / "monitor_config.default.json"


@dataclass
class MonitorConfig:
    low_threshold: float = 3.5
    critical_threshold: float = 3.0
    hysteresis: float = 0.2
    confirm_count: int = 3
    median_window: int = 5
    trend_rate_per_min: float = 0.5
    trend_window_s: float = 60.0
    trend_min_points: int = 8
    min_confidence: float = 0.5
    agree_tolerance: float = 0.4
    lamp_low_setpoint: float | None = None
    lamp_tolerance: float = 0.5
    lost_after_s: float = 30.0
    battery_low_pct: int = 15
    heartbeat_s: int = 30

    def validate(self) -> None:
        if self.critical_threshold >= self.low_threshold:
            raise ValueError("critical_threshold must be below low_threshold")
        if self.hysteresis < 0 or self.confirm_count < 1 or self.median_window < 1:
            raise ValueError("bad hysteresis/confirm_count/median_window")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be in [0,1]")

    @classmethod
    def from_dict(cls, d: dict) -> "MonitorConfig":
        names = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in d.items() if k in names})
        cfg.validate()
        return cfg

    @classmethod
    def load(cls, path: str | Path = DEFAULT_PATH) -> "MonitorConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return asdict(self)
