"""Reference alert engine (Python). The tablet runs the identical Kotlin version
(android/app/src/main/java/.../alert/AlertEngine.kt). Both are tested against the
same scenarios in contract/alert_scenarios.json.

Safety rules implemented
  * smoothing     : median of the last `median_window` VALID readings
  * confirmation  : LOW/CRITICAL only after `confirm_count` consecutive low medians
  * hysteresis    : clear only after `confirm_count` medians >= threshold + hysteresis
  * trend         : warn when the fitted fall rate over `trend_window_s` exceeds trend_rate_per_min
  * panel lamp    : a confirmed LOW lamp raises LOW even if the needle disagrees (alert-biased)
  * uncertain     : `confirm_count` consecutive unusable frames -> UNCERTAIN
  * fail-safe     : no valid reading for `lost_after_s`, lamp OFF for `lost_after_s`,
                    or battery low -> MONITORING_LOST
  * alarms never clear on bad data - only on good readings
Status priority: MONITORING_LOST > CRITICAL > LOW > UNCERTAIN > OK
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from statistics import median

from .config import MonitorConfig

PRIORITY = {"OK": 0, "UNCERTAIN": 1, "LOW": 2, "CRITICAL": 3, "MONITORING_LOST": 4}


@dataclass
class EngineInput:
    ts: float                         # seconds (monotonic or epoch)
    value: float | None
    confidence: float
    method_agree: bool
    lamp_state: str = "UNKNOWN"
    battery_pct: float | None = None
    charging: bool = True


@dataclass
class EngineOutput:
    status: str
    alarm: str                        # latched pressure alarm: OK | LOW | CRITICAL
    value: float | None               # smoothed (median) value
    trend_falling: bool
    fall_rate_per_min: float | None
    lost_reason: str | None
    events: list[dict] = field(default_factory=list)


class AlertEngine:
    def __init__(self, cfg: MonitorConfig):
        cfg.validate()
        self.cfg = cfg
        self.window: deque[float] = deque(maxlen=cfg.median_window)
        self.trend_buf: deque[tuple[float, float]] = deque()
        self.alarm = "OK"
        self.low_streak = self.crit_streak = 0
        self.clear_streak = 0
        self.lamp_low_streak = 0
        self.uncertain_streak = 0
        self.last_valid_ts: float | None = None
        self.start_ts: float | None = None
        self.lamp_off_since: float | None = None
        self.battery_low = False
        self.trend_falling = False
        self.fall_rate: float | None = None
        self.last_status = "OK"
        self.last_trend = False

    # ------------------------------------------------------------------
    def update(self, r: EngineInput) -> EngineOutput:
        c = self.cfg
        if self.start_ts is None:
            self.start_ts = r.ts
        valid = r.value is not None and r.confidence >= c.min_confidence and r.method_agree

        # lamp bookkeeping (independent of needle validity)
        self.lamp_low_streak = self.lamp_low_streak + 1 if r.lamp_state == "LOW" else 0
        if r.lamp_state == "OFF":
            if self.lamp_off_since is None:
                self.lamp_off_since = r.ts
        else:
            self.lamp_off_since = None
        self.battery_low = (r.battery_pct is not None and r.battery_pct < c.battery_low_pct
                            and not r.charging)

        if valid:
            if self.last_valid_ts is not None and r.ts - self.last_valid_ts >= c.lost_after_s:
                # recovering from a long gap: old samples are stale, start fresh
                # (the latched alarm is kept - it only clears on good readings)
                self.window.clear()
                self.trend_buf.clear()
                self.low_streak = self.crit_streak = self.clear_streak = 0
                self.trend_falling = False
                self.fall_rate = None
            self.uncertain_streak = 0
            self.last_valid_ts = r.ts
            self.window.append(float(r.value))
            self.trend_buf.append((r.ts, float(r.value)))
            while self.trend_buf and r.ts - self.trend_buf[0][0] > c.trend_window_s:
                self.trend_buf.popleft()
            self._update_pressure_alarm(float(r.value))
            self._update_trend()
        else:
            self.uncertain_streak += 1

        # panel lamp says LOW (confirmed): trust the hospital's own alarm
        if self.lamp_low_streak >= c.confirm_count and self.alarm == "OK":
            self.alarm = "LOW"
            self.clear_streak = 0
        return self._emit(r.ts)

    def tick(self, ts: float) -> EngineOutput:
        """Watchdog: call every second even when no frame arrives."""
        if self.start_ts is None:
            self.start_ts = ts
        return self._emit(ts)

    # ------------------------------------------------------------------
    def _median(self) -> float | None:
        return float(median(self.window)) if self.window else None

    def _update_pressure_alarm(self, v: float) -> None:
        """Raise: `confirm_count` consecutive valid readings below the threshold
        AND the median below it (a single glare frame can do neither).
        Clear: `confirm_count` consecutive medians above threshold + hysteresis."""
        c = self.cfg
        med = self._median()
        self.crit_streak = self.crit_streak + 1 if v < c.critical_threshold else 0
        self.low_streak = self.low_streak + 1 if v < c.low_threshold else 0

        if self.crit_streak >= c.confirm_count and med < c.critical_threshold:
            if self.alarm != "CRITICAL":
                self.clear_streak = 0
            self.alarm = "CRITICAL"
        elif self.low_streak >= c.confirm_count and med < c.low_threshold and self.alarm == "OK":
            self.alarm = "LOW"
            self.clear_streak = 0

        if self.alarm == "CRITICAL":
            if med >= c.critical_threshold + c.hysteresis:
                self.clear_streak += 1
                if self.clear_streak >= c.confirm_count:
                    self.alarm, self.clear_streak = "LOW", 0
            else:
                self.clear_streak = 0
        elif self.alarm == "LOW":
            lamp_low = self.lamp_low_streak > 0
            if med >= c.low_threshold + c.hysteresis and not lamp_low:
                self.clear_streak += 1
                if self.clear_streak >= c.confirm_count:
                    self.alarm, self.clear_streak = "OK", 0
            else:
                self.clear_streak = 0

    def _update_trend(self) -> None:
        c = self.cfg
        pts = self.trend_buf
        if len(pts) < c.trend_min_points or pts[-1][0] - pts[0][0] < c.trend_window_s * 0.5:
            self.fall_rate = None
            return
        n = len(pts)
        mt = sum(t for t, _ in pts) / n
        mv = sum(v for _, v in pts) / n
        sxx = sum((t - mt) ** 2 for t, _ in pts)
        if sxx <= 0:
            return
        slope = sum((t - mt) * (v - mv) for t, v in pts) / sxx     # per second
        rate = -slope * 60.0                                          # fall per minute
        self.fall_rate = round(rate, 4)
        if rate >= c.trend_rate_per_min:
            self.trend_falling = True
        elif rate < c.trend_rate_per_min * 0.5:
            self.trend_falling = False

    def _lost_reason(self, ts: float) -> str | None:
        c = self.cfg
        ref = self.last_valid_ts if self.last_valid_ts is not None else self.start_ts
        if ts - ref >= c.lost_after_s:
            return "no_valid_reading"
        if self.lamp_off_since is not None and ts - self.lamp_off_since >= c.lost_after_s:
            return "lamp_off"
        if self.battery_low:
            return "battery_low"
        return None

    def _emit(self, ts: float) -> EngineOutput:
        lost = self._lost_reason(ts)
        if lost:
            status = "MONITORING_LOST"
        elif self.alarm != "OK":
            status = self.alarm
        elif self.uncertain_streak >= self.cfg.confirm_count:
            status = "UNCERTAIN"
        else:
            status = "OK"
        events = []
        if status != self.last_status:
            events.append({"type": "STATUS", "from": self.last_status, "to": status, "ts": ts})
            self.last_status = status
        if self.trend_falling != self.last_trend:
            events.append({"type": "TREND_FALLING", "active": self.trend_falling, "ts": ts})
            self.last_trend = self.trend_falling
        med = self._median()
        return EngineOutput(status, self.alarm, None if med is None else round(med, 3),
                            self.trend_falling, self.fall_rate, lost, events)
