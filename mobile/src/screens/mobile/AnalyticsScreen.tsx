import React, { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { DataSource } from '../../api/dataSource';
import { HistoryChart } from '../../components/HistoryChart';
import { ReadingsTable } from '../../components/ReadingsTable';
import { useMonitoring } from '../../hooks/useMonitoring';
import { useDeviceHistory } from '../../hooks/useDeviceHistory';
import { useThemeColors } from '../../theme/ThemeContext';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';

interface Props { source: DataSource; }
const ranges = [{ label: '1H', hours: 1, ms: 3600_000 }, { label: '6H', hours: 6, ms: 6 * 3600_000 }, { label: '24H', hours: 24, ms: 24 * 3600_000 }, { label: '7D', hours: 168, ms: 7 * 24 * 3600_000 }, { label: '30D', hours: 720, ms: 30 * 24 * 3600_000 }] as const;

export const AnalyticsScreen: React.FC<Props> = ({ source }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const { devices, now } = useMonitoring(source);
  const [deviceId, setDeviceId] = useState('');
  const [range, setRange] = useState<(typeof ranges)[number]>(ranges[2]);
  const [tableMode, setTableMode] = useState(false);
  const device = devices.find(d => d.id === deviceId) ?? devices[0];
  const { filteredHistory } = useDeviceHistory(source, device?.id ?? '', now, range.hours);
  const points = useMemo(() => filteredHistory.filter(p => p.t >= now - range.ms), [filteredHistory, now, range]);
  const values = points.flatMap(p => p.v == null ? [] : [p.v]);
  const average = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  const minimum = values.length ? Math.min(...values) : null;
  const maximum = values.length ? Math.max(...values) : null;

  return <ScrollView contentContainerStyle={styles.page}>
    <Text style={styles.title}>History & analytics</Text>
    <Text style={styles.subtitle}>Recorded readings from the monitoring backend. Data refreshes automatically.</Text>
    {!devices.length ? <View style={styles.card}><Text style={styles.cardTitle}>No registered devices</Text><Text style={styles.subtitle}>Register a panel and record readings to build its history.</Text></View> : <>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.choices}>
        {devices.map(d => <TouchableOpacity key={d.id} onPress={() => setDeviceId(d.id)} style={[styles.choice, (device?.id === d.id) && styles.choiceActive]}><Text style={[styles.choiceText, device?.id === d.id && styles.choiceTextActive]}>{d.name}</Text></TouchableOpacity>)}
      </ScrollView>
      <View style={styles.rangeRow}>{ranges.map(item => <TouchableOpacity key={item.label} onPress={() => setRange(item)} style={[styles.rangeButton, range.label === item.label && styles.choiceActive]}><Text style={[styles.choiceText, range.label === item.label && styles.choiceTextActive]}>{item.label}</Text></TouchableOpacity>)}</View>
      {!!device && <>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{device.name} · {device.unit.replace('cm2', 'cm²')}</Text>
          <Text style={styles.subtitle}>{device.id} · {points.length} recorded samples</Text>
          <View style={styles.stats}>{[
            ['Average', average], ['Minimum', minimum], ['Maximum', maximum],
          ].map(([label, value]) => <View key={String(label)} style={styles.stat}>
            <Text style={styles.statLabel}>{label}</Text><Text style={styles.statValue}>{typeof value === 'number' ? value.toFixed(2) : '—'}</Text>
          </View>)}</View>
          <View style={styles.rangeRow}>
            <TouchableOpacity onPress={() => setTableMode(false)} style={[styles.rangeButton, !tableMode && styles.choiceActive]}><Text style={[styles.choiceText, !tableMode && styles.choiceTextActive]}>Trend</Text></TouchableOpacity>
            <TouchableOpacity onPress={() => setTableMode(true)} style={[styles.rangeButton, tableMode && styles.choiceActive]}><Text style={[styles.choiceText, tableMode && styles.choiceTextActive]}>Readings</Text></TouchableOpacity>
          </View>
          {tableMode ? <ReadingsTable points={points} unit={device.unit} maxRows={100} /> : <HistoryChart points={points} low={device.lowThreshold} critical={device.criticalThreshold} high={device.highThreshold} unit={device.unit} nowMs={now} rangeMs={range.ms} height={230} />}
        </View>
      </>}
    </>}
  </ScrollView>;
};

const createStyles = (c: ThemePalette) => StyleSheet.create({
  page: { flexGrow: 1, padding: 16, gap: 12, backgroundColor: c.page },
  title: { fontSize: 24, fontWeight: '800', color: c.ink }, subtitle: { color: c.ink2, fontSize: 13, lineHeight: 19 },
  choices: { flexDirection: 'row', gap: 8 }, choice: { paddingHorizontal: 13, paddingVertical: 9, borderRadius: 20, borderWidth: 1, borderColor: c.grid, backgroundColor: c.surface }, choiceActive: { backgroundColor: c.series, borderColor: c.series }, choiceText: { color: c.ink2, fontSize: 12, fontWeight: '700' }, choiceTextActive: { color: '#fff' },
  rangeRow: { flexDirection: 'row', gap: 8, alignItems: 'center' }, rangeButton: { borderWidth: 1, borderColor: c.grid, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: c.surface },
  card: { backgroundColor: c.surface, borderWidth: 1, borderColor: c.grid, borderRadius: 12, padding: 14, gap: 8 }, cardTitle: { color: c.ink, fontSize: 16, fontWeight: '800' },
  stats: { flexDirection: 'row', gap: 8, marginVertical: 6 }, stat: { flex: 1, backgroundColor: c.page, borderRadius: 8, padding: 9 }, statLabel: { fontSize: 11, color: c.ink2 }, statValue: { fontSize: 16, fontWeight: '800', color: c.ink, marginTop: 3 },
});
