"""Full frame -> JSON reading pipeline (Python reference of what the tablet runs)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np

from .calibration import Calibration
from .config import MonitorConfig
from .fusion import fuse
from .lamps import read_lamps
from .stage_a import read_needle, NeedleResult

IST = timezone(timedelta(hours=5, minutes=30))
STATUSES = ("OK", "LOW", "CRITICAL", "UNCERTAIN", "MONITORING_LOST")
LAMP_STATES = ("NORMAL", "LOW", "HIGH", "OFF", "CONFLICT", "UNKNOWN")


class GaugePipeline:
    def __init__(self, cal: Calibration, cfg: MonitorConfig | None = None, stage_b=None):
        """stage_b: optional callable(img, cal) -> NeedleResult (the keypoint model)."""
        self.cal = cal
        self.cfg = cfg or MonitorConfig()
        self.stage_b = stage_b

    def read(self, img: np.ndarray, ts: datetime | None = None) -> tuple[dict, dict]:
        a = read_needle(img, self.cal)
        b: NeedleResult | None = self.stage_b(img, self.cal) if self.stage_b else None
        lamp_state, lamp_details = read_lamps(img, self.cal)
        f = fuse(a, b, lamp_state, self.cfg)
        ts = ts or datetime.now(IST)
        msg = {
            "device_id": self.cal.device_id,
            "gauge_id": self.cal.gauge_id,
            "ts": ts.isoformat(timespec="seconds"),
            "value": f.value,
            "unit": self.cal.unit,
            "confidence": f.confidence,
            "lamp_state": lamp_state,
            "method_agree": f.method_agree,
            "status": f.status,
        }
        debug = {"stage_a": a, "stage_b": b, "lamps": lamp_details, "fusion": f}
        return msg, debug
