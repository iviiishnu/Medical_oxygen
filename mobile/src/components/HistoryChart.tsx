import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, LayoutChangeEvent, GestureResponderEvent } from 'react-native';
import Svg, { Line, Polyline, Text as SvgText, Circle, G, Rect } from 'react-native-svg';
import type { Point } from '../types/monitoring';
import { decimate, niceTicks, segments } from '../utils/logic';
import { colors as baseColors, type ThemePalette } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

interface Props {
  points: Point[];
  low: number;
  critical: number;
  unit: string;
  nowMs: number;
  height?: number;
}

const SPAN = 24 * 3600_000;
const MARGIN = { left: 40, right: 65, top: 16, bottom: 24 };

export const HistoryChart: React.FC<Props> = ({
  points,
  low,
  critical,
  unit,
  nowMs,
  height = 220,
}) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const [chartWidth, setChartWidth] = useState<number>(340);
  const [hoverPoint, setHoverPoint] = useState<Point | null>(null);

  const t0 = nowMs - SPAN;
  const data = useMemo(
    () => decimate(points.filter(p => p.t >= t0), 300),
    [points, t0]
  );

  const vals = data.filter(p => p.v != null).map(p => p.v as number);
  const vMax = Math.max(low + 1, ...vals, 0) * 1.08;
  const yTicks = niceTicks(0, vMax, 4);
  const yTop = yTicks[yTicks.length - 1] >= vMax ? yTicks[yTicks.length - 1] : vMax;

  const W = Math.max(chartWidth, 200);
  const H = height;

  const x = (t: number) =>
    MARGIN.left + ((t - t0) / SPAN) * (W - MARGIN.left - MARGIN.right);

  const y = (v: number) =>
    MARGIN.top + (1 - v / (yTop || 1)) * (H - MARGIN.top - MARGIN.bottom);

  const segs = segments(data, 3 * 60_000);
  const hours = Array.from({ length: 5 }, (_, i) => t0 + i * 6 * 3600_000);

  const handleLayout = (e: LayoutChangeEvent) => {
    setChartWidth(e.nativeEvent.layout.width);
  };

  const handleTouch = (e: GestureResponderEvent) => {
    if (!data.length) return;
    const touchX = e.nativeEvent.locationX;
    const clampedX = Math.max(MARGIN.left, Math.min(W - MARGIN.right, touchX));
    const targetTime = t0 + ((clampedX - MARGIN.left) / (W - MARGIN.left - MARGIN.right)) * SPAN;

    let closest = data[0];
    for (const p of data) {
      if (Math.abs(p.t - targetTime) < Math.abs(closest.t - targetTime)) {
        closest = p;
      }
    }
    setHoverPoint(closest);
  };

  const fmt = (t: number) =>
    new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <View style={styles.container} onLayout={handleLayout}>
      <View
        style={{ width: W, height: H }}
        onStartShouldSetResponder={() => true}
        onResponderMove={handleTouch}
        onResponderGrant={handleTouch}
        onResponderRelease={() => setHoverPoint(null)}
      >
        <Svg
          width={W}
          height={H}
          accessible={true}
          accessibilityLabel={`Telemetry history over the last 24 hours, ${unit}`}
        >

        {/* Y-axis gridlines and labels (mirrors dashboard .gridline and .tick) */}
        {yTicks.map(v => (
          <G key={`y-${v}`}>
            <Line
              x1={MARGIN.left}
              x2={W - MARGIN.right}
              y1={y(v)}
              y2={y(v)}
              stroke={colors.grid}
              strokeWidth={1}
            />
            <SvgText
              x={MARGIN.left - 6}
              y={y(v) + 4}
              fontSize={10}
              fill={colors.muted}
              textAnchor="end"
            >
              {v}
            </SvgText>
          </G>
        ))}

        {/* X-axis time ticks */}
        {hours.map(t => (
          <SvgText
            key={`x-${t}`}
            x={x(t)}
            y={H - 6}
            fontSize={10}
            fill={colors.muted}
            textAnchor="middle"
          >
            {fmt(t)}
          </SvgText>
        ))}

        {/* Base axis line (mirrors dashboard .axis) */}
        <Line
          x1={MARGIN.left}
          x2={W - MARGIN.right}
          y1={y(0)}
          y2={y(0)}
          stroke={colors.axis}
          strokeWidth={1}
        />

        {/* Threshold reference lines: LOW & CRITICAL (mirrors dashboard .ref-low & .ref-crit) */}
        <G key="ref-low">
          <Line
            x1={MARGIN.left}
            x2={W - MARGIN.right}
            y1={y(low)}
            y2={y(low)}
            stroke={colors.warning}
            strokeWidth={1.5}
            strokeDasharray="6 4"
          />
          <SvgText
            x={W - MARGIN.right + 4}
            y={y(low) + 3}
            fontSize={10}
            fontWeight="600"
            fill={colors.ink2}
          >
            LOW {low}
          </SvgText>
        </G>

        <G key="ref-crit">
          <Line
            x1={MARGIN.left}
            x2={W - MARGIN.right}
            y1={y(critical)}
            y2={y(critical)}
            stroke={colors.critical}
            strokeWidth={1.5}
            strokeDasharray="6 4"
          />
          <SvgText
            x={W - MARGIN.right + 4}
            y={y(critical) + 3}
            fontSize={10}
            fontWeight="600"
            fill={colors.critical}
          >
            CRIT {critical}
          </SvgText>
        </G>

        {/* Data series lines (mirrors dashboard .series) */}
        {segs.map((s, i) => (
          <Polyline
            key={`seg-${i}`}
            points={s.map(p => `${x(p.t)},${y(p.v as number)}`).join(' ')}
            fill="none"
            stroke={colors.series}
            strokeWidth={2}
          />
        ))}

        {/* Scrubbing crosshair indicator (mirrors dashboard .crosshair & .dot) */}
        {hoverPoint && hoverPoint.v != null && (
          <G pointerEvents="none">
            <Line
              x1={x(hoverPoint.t)}
              x2={x(hoverPoint.t)}
              y1={MARGIN.top}
              y2={H - MARGIN.bottom}
              stroke={colors.axis}
              strokeWidth={1}
            />
            <Circle
              cx={x(hoverPoint.t)}
              cy={y(hoverPoint.v)}
              r={5}
              fill={colors.series}
              stroke={colors.surface}
              strokeWidth={2}
            />
          </G>
        )}
        </Svg>
      </View>

      {/* Touch Tooltip Display (mirrors dashboard .tooltip) */}
      {hoverPoint && (
        <View style={styles.tooltipContainer}>
          <Text style={styles.tooltipTime}>{new Date(hoverPoint.t).toLocaleTimeString()}</Text>
          <Text style={styles.tooltipVal}>
            {hoverPoint.v == null ? 'No reading' : `${hoverPoint.v.toFixed(2)} ${unit}`}
          </Text>
          <Text style={styles.tooltipStatus}>{hoverPoint.status}</Text>
        </View>
      )}

      {!vals.length && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>No readings recorded in the last 24 hours</Text>
        </View>
      )}
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    backgroundColor: colors.surface,
    borderRadius: 8,
    paddingVertical: 8,
    marginVertical: 6,
    overflow: 'hidden',
  },
  tooltipContainer: {
    marginTop: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: colors.surface,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.grid,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  tooltipTime: {
    fontSize: 11,
    color: colors.ink2,
  },
  tooltipVal: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
  },
  tooltipStatus: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.muted,
  },
  emptyContainer: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 12,
    color: colors.muted,
  },
});
