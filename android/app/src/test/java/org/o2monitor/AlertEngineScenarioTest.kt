package org.o2monitor

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.double
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.o2monitor.core.AlertEngine
import org.o2monitor.core.MonitorConfig

/** Runs the SAME scenarios as vision/tests/test_alert_engine.py. */
class AlertEngineScenarioTest {
    private val cfg = MonitorConfig.fromJson(TestFiles.contract("monitor_config.default.json").readText())
    private val scenarios = Json.parseToJsonElement(TestFiles.contract("alert_scenarios.json").readText())
        .jsonObject["scenarios"]!!.jsonArray

    private fun run(steps: List<JsonObject>): List<AlertEngine.Output> {
        val eng = AlertEngine(cfg)
        return steps.map { s ->
            val t = s["t"]!!.jsonPrimitive.double
            if (s["tick"]?.jsonPrimitive?.booleanOrNull == true) eng.tick(t)
            else eng.update(
                AlertEngine.Input(
                    ts = t,
                    value = s["value"]?.jsonPrimitive?.doubleOrNull,
                    confidence = s["conf"]!!.jsonPrimitive.double,
                    methodAgree = s["agree"]!!.jsonPrimitive.boolean,
                    lampState = s["lamp"]!!.jsonPrimitive.content,
                    batteryPct = s["battery"]?.jsonPrimitive?.doubleOrNull,
                    charging = s["charging"]?.jsonPrimitive?.booleanOrNull ?: true,
                ),
            )
        }
    }

    @Test
    fun allSharedScenariosPass() {
        assertTrue("scenario file empty", scenarios.size >= 19)
        val failures = mutableListOf<String>()
        for (sc in scenarios) {
            val name = sc.jsonObject["name"]!!.jsonPrimitive.content
            val steps = sc.jsonObject["steps"]!!.jsonArray.map { it.jsonObject }
            val outs = run(steps)
            steps.zip(outs).forEachIndexed { i, (s, o) ->
                s["expect"]?.jsonPrimitive?.content?.let {
                    if (o.status != it) failures += "$name step $i: status ${o.status} != $it"
                }
                s["expect_trend"]?.jsonPrimitive?.booleanOrNull?.let {
                    if (o.trendFalling != it) failures += "$name step $i: trend ${o.trendFalling} != $it"
                }
            }
        }
        assertTrue(failures.take(20).joinToString("\n"), failures.isEmpty())
    }

    @Test
    fun eventsOncePerTransition() {
        val sc = scenarios.first { it.jsonObject["name"]!!.jsonPrimitive.content == "sudden_drop_low_after_3" }
        val outs = run(sc.jsonObject["steps"]!!.jsonArray.map { it.jsonObject })
        val evs = outs.flatMap { it.events }
        assertEquals(listOf(AlertEngine.Event.StatusChange("OK", "LOW", 8.0)), evs)
    }

    @Test
    fun recoveryAfterLostUsesFreshWindow() {
        val eng = AlertEngine(cfg)
        for (t in 0..5) eng.update(AlertEngine.Input(t.toDouble(), 2.0, 0.9, true))
        assertEquals("MONITORING_LOST", eng.tick(40.0).status)
        val out = eng.update(AlertEngine.Input(41.0, 6.0, 0.9, true))
        assertEquals(6.0, out.value!!, 1e-9)
        assertEquals("CRITICAL", out.alarm)
    }
}
