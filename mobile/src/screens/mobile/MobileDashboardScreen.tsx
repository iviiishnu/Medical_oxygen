import React, { useMemo, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { DataSource } from '../../api/dataSource';
import { HistoryChart } from '../../components/HistoryChart';
import { StatusBadge } from '../../components/StatusBadge';
import { useMonitoring } from '../../hooks/useMonitoring';
import { useDeviceHistory } from '../../hooks/useDeviceHistory';
import { effectiveStatus, ago } from '../../utils/logic';
import { useThemeColors } from '../../theme/ThemeContext';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';

interface Props { source: DataSource; onSignOut?: () => void; }

export const MobileDashboardScreen: React.FC<Props> = ({ source }) => {
  const navigation = useNavigation<any>();
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const { devices, alerts, offlineDevices, now } = useMonitoring(source);
  const activeAlerts = alerts.filter(a => a.state !== 'RESOLVED');
  const [refreshing, setRefreshing] = useState(false);
  const selected = devices[0];
  const { filteredHistory } = useDeviceHistory(source, selected?.id ?? '', now);
  const normalCount = useMemo(() => devices.filter(d => effectiveStatus(d, now) === 'OK').length, [devices, now]);
  const criticalCount = useMemo(() => devices.filter(d => d.status === 'CRITICAL' || d.alarm === 'CRITICAL').length, [devices]);

  return <ScrollView contentContainerStyle={styles.page} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); setTimeout(() => setRefreshing(false), 500); }} />}>
    <View style={styles.header}><View><Text style={styles.eyebrow}>{source.mode === 'demo' ? 'DEMO SIMULATION' : 'OXYGEN MONITORING'}</Text><Text style={styles.title}>Dashboard</Text></View><TouchableOpacity style={styles.headerButton} onPress={() => navigation.navigate('AlertsTab')}><Text style={styles.headerButtonText}>Alerts {activeAlerts.length ? `· ${activeAlerts.length}` : ''}</Text></TouchableOpacity></View>
    <View style={styles.systemCard}>
      <View style={[styles.systemDot, offlineDevices.length || activeAlerts.length ? styles.systemBad : styles.systemGood]} />
      <View style={styles.systemText}><Text style={styles.systemTitle}>{activeAlerts.length ? 'Active alert requires attention' : offlineDevices.length ? 'Device connection issue' : devices.length ? 'Monitoring operational' : 'No devices registered'}</Text><Text style={styles.subtitle}>{devices.length} device{devices.length === 1 ? '' : 's'} · {offlineDevices.length} offline · {activeAlerts.length} active alert{activeAlerts.length === 1 ? '' : 's'}</Text></View>
    </View>
    <View style={styles.summaryRow}>
      {[["Devices", devices.length], ["Normal", normalCount], ["Critical", criticalCount], ["Offline", offlineDevices.length]].map(([label, value]) => <View key={String(label)} style={styles.summaryCard}><Text style={styles.summaryValue}>{value}</Text><Text style={styles.summaryLabel}>{label}</Text></View>)}
    </View>
    <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Devices</Text><TouchableOpacity onPress={() => navigation.navigate('DevicesTab')}><Text style={styles.link}>View all</Text></TouchableOpacity></View>
    {!devices.length ? <View style={styles.card}><Text style={styles.subtitle}>There are no registered monitoring devices yet. Register a panel from Live Monitoring.</Text><TouchableOpacity style={styles.primaryButton} onPress={() => navigation.getParent()?.navigate('MoreTab', { screen: 'CameraStream' })}><Text style={styles.primaryText}>Open live monitoring</Text></TouchableOpacity></View> : devices.map(d => {
      const status = effectiveStatus(d, now);
      return <TouchableOpacity key={d.id} style={[styles.deviceCard, { borderLeftColor: colors.statusEdges[status] ?? colors.muted }]} onPress={() => navigation.navigate('DeviceDetail', { deviceId: d.id, deviceName: d.name })}>
        <View style={styles.deviceTop}><View style={styles.deviceInfo}><Text style={styles.deviceName}>{d.name}</Text><Text style={styles.deviceMeta}>{d.id} · {d.online ? 'Connected' : 'Offline'} · updated {ago(d.lastHeartbeatMs, now)}</Text></View><StatusBadge status={status} size="small" /></View>
        <View style={styles.valueRow}><Text style={styles.value}>{d.value == null ? '—' : d.value.toFixed(2)}</Text><Text style={styles.unit}>{d.unit.replace('cm2', 'cm²')}</Text></View>
        <Text style={styles.thresholdText}>Low {d.lowThreshold} · Critical {d.criticalThreshold}{d.highThreshold != null ? ` · High ${d.highThreshold}` : ''}</Text>
      </TouchableOpacity>;
    })}
    {!!selected && <View style={styles.card}><View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Recent pressure · {selected.name}</Text><TouchableOpacity onPress={() => navigation.navigate('AnalyticsTab')}><Text style={styles.link}>History</Text></TouchableOpacity></View><HistoryChart points={filteredHistory} low={selected.lowThreshold} critical={selected.criticalThreshold} high={selected.highThreshold} unit={selected.unit} nowMs={now} rangeMs={3600_000} height={175} /></View>}
    <View style={styles.card}><View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Recent alerts</Text><TouchableOpacity onPress={() => navigation.navigate('AlertsTab')}><Text style={styles.link}>View all</Text></TouchableOpacity></View>
      {!alerts.length ? <Text style={styles.subtitle}>No alert history has been recorded.</Text> : alerts.slice(0, 3).map(a => <View key={a.id} style={styles.alertRow}><StatusBadge status={a.type} size="small"/><View style={styles.alertInfo}><Text style={styles.deviceName}>{a.deviceId} · {a.type}</Text><Text style={styles.deviceMeta}>{a.value == null ? 'No reading' : `${a.value.toFixed(2)} ${a.unit}`} · {a.createdMs ? new Date(a.createdMs).toLocaleString() : 'time unavailable'}</Text></View><Text style={styles.alertState}>{a.state}</Text></View>)}
    </View>
  </ScrollView>;
};

const createStyles = (c: ThemePalette) => StyleSheet.create({
  page: { flexGrow: 1, padding: 14, gap: 12, backgroundColor: c.page, paddingBottom: 24 }, header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, eyebrow: { color: c.series, fontSize: 10, fontWeight: '800', letterSpacing: 1 }, title: { color: c.ink, fontSize: 24, fontWeight: '800' }, headerButton: { backgroundColor: c.surface, borderWidth: 1, borderColor: c.grid, paddingVertical: 8, paddingHorizontal: 11, borderRadius: 10 }, headerButtonText: { color: c.ink, fontSize: 12, fontWeight: '700' },
  systemCard: { flexDirection: 'row', gap: 10, alignItems: 'center', backgroundColor: c.surface, borderColor: c.grid, borderWidth: 1, borderRadius: 12, padding: 12 }, systemDot: { width: 10, height: 10, borderRadius: 5 }, systemGood: { backgroundColor: c.good }, systemBad: { backgroundColor: c.critical }, systemText: { flex: 1, gap: 2 }, systemTitle: { color: c.ink, fontSize: 14, fontWeight: '800' }, subtitle: { color: c.ink2, fontSize: 12, lineHeight: 17 },
  summaryRow: { flexDirection: 'row', gap: 7 }, summaryCard: { flex: 1, backgroundColor: c.surface, borderWidth: 1, borderColor: c.grid, borderRadius: 10, padding: 10 }, summaryValue: { fontSize: 19, fontWeight: '800', color: c.ink }, summaryLabel: { fontSize: 10, color: c.ink2, marginTop: 2 }, sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }, sectionTitle: { color: c.ink, fontWeight: '800', fontSize: 15 }, link: { color: c.series, fontSize: 12, fontWeight: '700' },
  deviceCard: { backgroundColor: c.surface, borderWidth: 1, borderColor: c.grid, borderLeftWidth: 4, borderRadius: 12, padding: 12, gap: 6 }, deviceTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }, deviceInfo: { flex: 1 }, deviceName: { color: c.ink, fontSize: 14, fontWeight: '800' }, deviceMeta: { color: c.ink2, fontSize: 10, marginTop: 3 }, valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 7 }, value: { color: c.ink, fontSize: 34, fontWeight: '800', fontVariant: ['tabular-nums'] }, unit: { color: c.ink2, fontSize: 13, fontWeight: '700' }, thresholdText: { color: c.ink2, fontSize: 11 },
  card: { backgroundColor: c.surface, borderWidth: 1, borderColor: c.grid, borderRadius: 12, padding: 12, gap: 8 }, alertRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 7, borderTopWidth: 1, borderTopColor: c.grid }, alertInfo: { flex: 1 }, alertState: { color: c.ink2, fontSize: 10, fontWeight: '700' }, primaryButton: { alignSelf: 'flex-start', backgroundColor: c.series, borderRadius: 8, padding: 10 }, primaryText: { color: '#fff', fontSize: 12, fontWeight: '700' },
});
