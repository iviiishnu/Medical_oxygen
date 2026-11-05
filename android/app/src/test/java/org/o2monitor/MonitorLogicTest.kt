package org.o2monitor

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.o2monitor.core.MonitorConfig
import org.o2monitor.monitor.MonitorLogic
import org.o2monitor.monitor.MonitorLogic.Action
import org.o2monitor.vision.FakeGaugeReader
import org.o2monitor.vision.FakeGaugeReader.Scenario

class MonitorLogicTest {
    private val cfg = MonitorConfig()
    private val t0 = 1_763_000_000_000L

    /** Run [seconds] of 1 fps frames; returns (second, action) pairs. */
    private fun run(scenario: Scenario, seconds: Int, seed: Int = 1, logic: MonitorLogic = MonitorLogic(cfg)):
        List<Pair<Int, Action>> {
        val fake = FakeGaugeReader(cfg, scenario, seed = seed)
        val acts = mutableListOf<Pair<Int, Action>>()
        for (s in 0 until seconds) {
            val now = t0 + s * 1000L
            logic.onFrame(fake.read(null, now), now, 80.0, true).forEach { acts += s to it }
        }
        return acts
    }

    private fun opened(acts: List<Pair<Int, Action>>) =
        acts.mapNotNull { (s, a) -> (a as? Action.OpenAlert)?.let { s to it.type } }

    @Test
    fun steadyHasNoAlerts() {
        assertTrue(opened(run(Scenario.STEADY, 600)).isEmpty())
    }

    @Test
    fun suddenDropAlertsWithin3Frames() {
        val o = opened(run(Scenario.SUDDEN_DROP, 30))
        assertEquals(listOf(12 to "CRITICAL"), o)        // drop at t=10, 3rd low frame at t=12
    }

    @Test
    fun slowLeakWarnsByTrendBeforeLow() {
        val o = opened(run(Scenario.SLOW_LEAK, 300))
        val trend = o.first { it.second == "TREND_FALLING" }.first
        val low = o.first { it.second == "LOW" }.first
        assertTrue("trend at $trend should precede LOW at $low", trend < low)
        assertTrue(o.any { it.second == "CRITICAL" })
    }

    @Test
    fun unreadableBecomesUncertainThenLost() {
        val acts = run(Scenario.UNREADABLE, 40)
        val o = opened(acts)
        assertEquals("UNCERTAIN", o[0].second)
        assertEquals(12, o[0].first)        // UNCERTAIN from t=2, alert after 10 s more
        val lost = o.first { it.second == "MONITORING_LOST" }
        assertEquals(30, lost.first)
        // UNCERTAIN is resolved when it escalates to LOST (one monitoring alert at a time)
        assertTrue(acts.any { (s, a) -> s == 30 && a is Action.ResolveAlert && a.type == "UNCERTAIN" })
    }

    @Test
    fun panelLampLowRaisesLow() {
        assertEquals(listOf(2 to "LOW"), opened(run(Scenario.LAMP_LOW, 20)).filter { it.second == "LOW" })
    }

    /** Simulated 24 h soak: steady pressure with 10% glare frames -> zero alarms. */
    @Test
    fun soak24hWithGlareNoFalseAlarm() {
        val logic = MonitorLogic(cfg)
        val acts = run(Scenario.GLARE_SPIKES, 24 * 3600, seed = 7, logic = logic)
        val o = opened(acts)
        assertTrue("false alarms: ${o.take(5)}", o.isEmpty())
        val history = acts.count { it.second is Action.SaveHistory }
        assertTrue("history rows $history", history in 1400..1700)       // ~1 per minute
    }

    @Test
    fun recoveryResolvesAlarm() {
        val acts = run(Scenario.RECOVERY, 60)
        assertTrue(acts.any { it.second is Action.OpenAlert && (it.second as Action.OpenAlert).type == "CRITICAL" })
        assertTrue(acts.any { it.second is Action.ResolveAlert && (it.second as Action.ResolveAlert).type == "LOW" })
    }

    @Test
    fun frameStopWatchdogRaisesLost() {
        val logic = MonitorLogic(cfg)
        val fake = FakeGaugeReader(cfg, Scenario.STEADY)
        for (s in 0 until 5) logic.onFrame(fake.read(null, t0 + s * 1000L), t0 + s * 1000L, 80.0, true)
        var lostAt = -1
        for (s in 5 until 60) {
            if (logic.onTick(t0 + s * 1000L).any { it is Action.OpenAlert && it.type == "MONITORING_LOST" }) {
                lostAt = s; break
            }
        }
        assertEquals(34, lostAt)          // last good frame at t=4, lost at 4 + 30
        assertTrue(logic.state.localAlarm)
    }

    @Test
    fun silenceIsCancelledByWorseAlert() {
        val logic = MonitorLogic(cfg)
        val fake = FakeGaugeReader(cfg, Scenario.STEADY)
        var now = t0
        repeat(5) { logic.onFrame(fake.read(null, now), now, 80.0, true); now += 1000 }
        repeat(35) { logic.onTick(now); now += 1000 }                      // lost (sev 4)
        assertTrue(logic.state.localAlarm)
        logic.silence(now, 5)
        logic.onTick(now)
        assertFalse(logic.state.localAlarm)
        fake.scenario = Scenario.SUDDEN_DROP
        repeat(20) { logic.onFrame(fake.read(null, now), now, 80.0, true); now += 1000 }   // CRITICAL (sev 5)
        assertEquals("CRITICAL", logic.state.alarm)
        assertTrue("worse alert must ring again", logic.state.localAlarm)
    }
}
