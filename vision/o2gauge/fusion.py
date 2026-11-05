"""Fusion of Stage B (keypoint model), Stage A (classical) and the panel lamp
into ONE per-frame reading. Mirrored in Kotlin (Fusion.kt).

Rules
  * value      = confidence-weighted mean of Stage A and Stage B when both are confident
                 and agree; the single confident method otherwise; Stage B if they disagree
                 (that frame is UNCERTAIN anyway).
  * method_agree = needle methods within agree_tolerance AND lamp consistent.
  * per-frame status:
        unreadable / low confidence / disagreement -> UNCERTAIN
        else value < critical -> CRITICAL, < low -> LOW, else OK
    The alert engine (not this function) decides when an ALARM is raised.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import MonitorConfig
from .stage_a import NeedleResult

LIT_STATES = ("NORMAL", "LOW", "HIGH")


@dataclass
class Fused:
    value: float | None
    confidence: float
    method_agree: bool
    lamp_agree: bool
    status: str
    source: str
    notes: list[str]


def lamp_expected(value: float, cfg: MonitorConfig) -> str:
    setpoint = cfg.lamp_low_setpoint if cfg.lamp_low_setpoint is not None else cfg.low_threshold
    return "LOW" if value < setpoint else "NORMAL"


def lamp_consistent(value: float | None, lamp_state: str, cfg: MonitorConfig) -> bool:
    """False only when the lamp is lit and clearly contradicts the needle."""
    if value is None or lamp_state not in LIT_STATES:
        return True
    setpoint = cfg.lamp_low_setpoint if cfg.lamp_low_setpoint is not None else cfg.low_threshold
    if abs(value - setpoint) <= cfg.lamp_tolerance:
        return True                                # too close to the panel's set-point to judge
    exp = lamp_expected(value, cfg)
    if lamp_state == "HIGH":
        return exp == "NORMAL"                     # HIGH lamp is not a low-pressure contradiction
    return lamp_state == exp


def fuse(a: NeedleResult | None, b: NeedleResult | None, lamp_state: str,
         cfg: MonitorConfig) -> Fused:
    notes: list[str] = []
    a_ok = a is not None and a.value is not None and a.confidence >= cfg.min_confidence
    b_ok = b is not None and b.value is not None and b.confidence >= cfg.min_confidence

    if b_ok and a_ok:
        diff = abs(b.value - a.value)
        needles_agree = diff <= cfg.agree_tolerance
        value, source = b.value, "stage_b"
        if needles_agree:
            # both methods are accurate and their errors are largely independent:
            # the confidence-weighted mean beats either one alone (measured: docs/eval_final*.json)
            wa, wb = a.confidence, b.confidence
            value, source = (wa * a.value + wb * b.value) / (wa + wb), "a+b"
            conf = 1.0 - (1.0 - a.confidence) * (1.0 - b.confidence)
        else:
            conf = 0.5 * min(a.confidence, b.confidence)
            notes.append(f"needle methods disagree by {diff:.2f}")
    elif b_ok or a_ok:
        r = b if b_ok else a
        value, source, conf = r.value, r.method, r.confidence
        needles_agree = True                        # nothing to disagree with
        notes.append(f"single method ({source})")
    else:
        # neither method is confident: still report the best guess for the log
        cands = [r for r in (b, a) if r is not None and r.value is not None]
        best = max(cands, key=lambda r: r.confidence) if cands else None
        value = best.value if best else None
        conf = best.confidence if best else 0.0
        source = best.method if best else "none"
        needles_agree = False
        notes.append("no confident needle reading")

    l_ok = lamp_consistent(value, lamp_state, cfg)
    if not l_ok:
        notes.append(f"lamp {lamp_state} contradicts needle {value}")
        conf *= 0.5
    if lamp_state in ("OFF", "CONFLICT"):
        notes.append(f"lamp state {lamp_state}")

    method_agree = needles_agree and l_ok
    if value is None or conf < cfg.min_confidence or not method_agree or lamp_state == "CONFLICT":
        status = "UNCERTAIN"
    elif value < cfg.critical_threshold:
        status = "CRITICAL"
    elif value < cfg.low_threshold:
        status = "LOW"
    else:
        status = "OK"
    return Fused(None if value is None else round(float(value), 3), round(float(conf), 3),
                 bool(method_agree), bool(l_ok), status, source, notes)
