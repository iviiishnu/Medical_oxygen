import React, { useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Modal,
  ScrollView,
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import type { DataSource } from '../../api/dataSource';
import { useMonitoring } from '../../hooks/useMonitoring';
import { AlertCard } from '../../components/AlertCard';
import { AlertBanner } from '../../components/AlertBanner';
import type { AlertDetails } from '../../types/monitoring';
import { useNavigation } from '@react-navigation/native';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';
import { useResponsive } from '../../hooks/useResponsive';

interface Props {
  source: DataSource;
  onCreateIncident?: (alertId: string) => void;
  onOpenDevice?: (deviceId: string, deviceName: string) => void;
}

export const MobileAlertsScreen: React.FC<Props> = ({ source, onCreateIncident, onOpenDevice }) => {
  const navigation = useNavigation<any>();
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const { isTablet, isLandscape } = useResponsive();
  const showTabletDetails = isTablet && isLandscape;
  const {
    alerts,
    openAlerts,
    now,
    acknowledgeAlert,
    ackError,
  } = useMonitoring(source);

  const [filter, setFilter] = useState<'ALL' | 'OPEN' | 'ACKED' | 'RESOLVED'>('ALL');
  const [refreshing, setRefreshing] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<AlertDetails | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState('');

  const openDetail = async (id: string) => {
    setLoadingDetail(true); setDetailError(''); setSelectedAlert(null);
    try { setSelectedAlert(await source.getAlertDetails(id)); }
    catch (e) { setDetailError(e instanceof Error ? e.message : 'Could not load alert details.'); }
    finally { setLoadingDetail(false); }
  };

  const filteredAlerts = React.useMemo(() => {
    if (filter === 'ALL') return alerts;
    return alerts.filter(a => a.state === filter);
  }, [alerts, filter]);

  const onRefresh = () => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 600);
  };

  const detailBody = selectedAlert ? <>
    <View style={styles.detailHeader}><Text style={styles.detailTitle}>Alert details</Text>{!showTabletDetails && <TouchableOpacity onPress={() => setSelectedAlert(null)}><Text style={styles.close}>Close</Text></TouchableOpacity>}</View>
    <Text style={styles.detailText}>{selectedAlert.deviceName} · {selectedAlert.deviceId}</Text>
    <Text style={styles.detailValue}>{selectedAlert.value == null ? 'No reading' : `${selectedAlert.value.toFixed(2)} ${selectedAlert.unit}`} · {selectedAlert.type}</Text>
    <Text style={styles.detailText}>{selectedAlert.createdMs ? new Date(selectedAlert.createdMs).toLocaleString() : ''} · {selectedAlert.state}</Text>
    <Text style={styles.detailText}>Critical below {selectedAlert.criticalThreshold ?? '—'} · Low below {selectedAlert.lowThreshold ?? '—'}{selectedAlert.highThreshold != null ? ` · High above ${selectedAlert.highThreshold}` : ''} {selectedAlert.unit}</Text>
    {!!selectedAlert.reason && <Text style={styles.detailText}>{selectedAlert.reason}</Text>}
    <TouchableOpacity onPress={() => { const detail = selectedAlert; setSelectedAlert(null); if (onOpenDevice) onOpenDevice(detail.deviceId, detail.deviceName); else navigation.navigate('HomeTab', { screen: 'DeviceDetail', params: { deviceId: detail.deviceId, deviceName: detail.deviceName } }); }}><Text style={styles.close}>Open device</Text></TouchableOpacity>
    {!!selectedAlert.evidenceImage && <Image source={{ uri: selectedAlert.evidenceImage }} style={styles.evidence} resizeMode="contain" />}
    <Text style={styles.detailTitle}>Previous readings</Text>
    {selectedAlert.recentReadings.slice(-12).reverse().map((point, index) => <Text key={`${point.t}-${index}`} style={styles.detailText}>{new Date(point.t).toLocaleTimeString()} · {point.v == null ? 'Unreadable' : `${point.v.toFixed(2)} ${selectedAlert.unit}`} · {point.status}</Text>)}
    <TouchableOpacity style={styles.incidentButton} onPress={() => { const alertId = selectedAlert.id; setSelectedAlert(null); if (onCreateIncident) onCreateIncident(alertId); else navigation.navigate('MoreTab', { screen: 'Incidents', params: { alertId } }); }}><Text style={styles.incidentButtonText}>Create linked incident</Text></TouchableOpacity>
  </> : detailError ? <><Text style={styles.detailTitle}>Could not load alert</Text><Text style={styles.detailText}>{detailError}</Text><TouchableOpacity onPress={() => setDetailError('')}><Text style={styles.close}>Close</Text></TouchableOpacity></> : <Text style={styles.detailText}>Select an alert to view its thresholds, recent readings, and captured evidence.</Text>;

  return (
    <View style={styles.container}>
      <View style={styles.heading}><Text style={styles.title}>Alerts</Text><Text style={styles.counts}>{openAlerts.length} active · {alerts.filter(a => a.state === 'ACKED').length} acknowledged · {alerts.filter(a => a.state === 'RESOLVED').length} resolved</Text></View>
      <AlertBanner
        alerts={openAlerts}
        now={now}
        onAcknowledge={acknowledgeAlert}
        ackError={ackError}
      />

      {/* Filter Tabs */}
      <View style={styles.filterRow}>
        {(['ALL', 'OPEN', 'ACKED', 'RESOLVED'] as const).map(tab => (
          <TouchableOpacity
            key={tab}
            style={[styles.filterBtn, filter === tab && styles.filterBtnActive]}
            onPress={() => setFilter(tab)}
          >
            <Text
              style={[styles.filterText, filter === tab && styles.filterTextActive]}
            >
              {tab}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={[styles.bodyPane, showTabletDetails && styles.bodyPaneTablet]}>
        <FlatList
          style={showTabletDetails && styles.tabletAlertList}
          data={filteredAlerts}
          keyExtractor={(item: any) => item.id}
          renderItem={({ item }: { item: any }) => <TouchableOpacity onPress={() => void openDetail(item.id)}><AlertCard alert={item} /></TouchableOpacity>}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          ListEmptyComponent={<View style={styles.empty}><Text style={styles.emptyText}>No alerts matching filter criteria in the last 24 hours.</Text></View>}
        />
        {showTabletDetails && <ScrollView style={styles.tabletDetailPane} contentContainerStyle={styles.detailContent}>{loadingDetail ? <ActivityIndicator color={colors.series} /> : detailBody}</ScrollView>}
      </View>
      <Modal visible={!showTabletDetails && (loadingDetail || !!selectedAlert || !!detailError)} transparent animationType="slide" onRequestClose={() => { setSelectedAlert(null); setDetailError(''); }}>
        <View style={styles.modalBackdrop}><ScrollView style={styles.detailCard} contentContainerStyle={styles.detailContent}>{loadingDetail ? <ActivityIndicator color={colors.series} /> : detailBody}</ScrollView></View>
      </Modal>
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.page,
  },
  heading: { paddingHorizontal: 14, paddingTop: 12, paddingBottom: 5, gap: 3 },
  title: { fontSize: 23, fontWeight: '800', color: colors.ink },
  counts: { fontSize: 11, color: colors.ink2 },
  bodyPane: { flex: 1 }, bodyPaneTablet: { flexDirection: 'row', gap: 10, padding: 12 }, tabletAlertList: { flex: 0.42 }, tabletDetailPane: { flex: 0.58, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.grid, borderRadius: 12 },
  modalBackdrop: { flex: 1, justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.55)', padding: 18 },
  detailCard: { maxHeight: '88%', backgroundColor: colors.surface, borderRadius: 14 }, detailContent: { padding: 16, gap: 9 }, detailHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, detailTitle: { fontSize: 16, fontWeight: '800', color: colors.ink }, detailText: { fontSize: 12, lineHeight: 18, color: colors.ink2 }, detailValue: { fontSize: 18, fontWeight: '800', color: colors.critical }, close: { color: colors.series, fontWeight: '700' }, evidence: { width: '100%', height: 210, backgroundColor: colors.page, borderRadius: 8 }, incidentButton: { backgroundColor: colors.series, padding: 12, alignItems: 'center', borderRadius: 8 }, incidentButtonText: { color: '#fff', fontWeight: '700' },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.grid,
    gap: 8,
  },
  filterBtn: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 16,
    backgroundColor: colors.borderLight,
  },
  filterBtnActive: {
    backgroundColor: colors.ink, // Mirroring dashboard button: var(--ink)
  },
  filterText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.ink2,
  },
  filterTextActive: {
    color: colors.surface,
  },
  list: {
    padding: 12,
  },
  empty: {
    padding: 30,
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.grid,
    marginTop: 20,
  },
  emptyText: {
    fontSize: 13,
    color: colors.muted,
    textAlign: 'center',
  },
});
