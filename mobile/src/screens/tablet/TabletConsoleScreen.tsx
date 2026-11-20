import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import type { DataSource } from '../../api/dataSource';
import type { Device } from '../../types/monitoring';
import { useMonitoring } from '../../hooks/useMonitoring';
import { useDeviceHistory } from '../../hooks/useDeviceHistory';
import { useResponsive } from '../../hooks/useResponsive';
import { StatusBadge } from '../../components/StatusBadge';
import { HeroMetric } from '../../components/HeroMetric';
import { ThresholdIndicator } from '../../components/ThresholdIndicator';
import { HistoryChart } from '../../components/HistoryChart';
import { ReadingsTable } from '../../components/ReadingsTable';
import { CameraPreviewWidget } from '../../components/CameraPreviewWidget';
import { AlertBanner } from '../../components/AlertBanner';
import { ConnectionIndicator } from '../../components/ConnectionIndicator';
import { effectiveStatus, ago } from '../../utils/logic';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';

interface Props {
  source: DataSource;
  onSignOut: () => void;
  onRegisterDevice: () => void;
  showDrawerButton: boolean;
  onOpenDrawer: () => void;
  initialDeviceId?: string;
  onInitialDeviceFocused?: () => void;
}

export const TabletConsoleScreen: React.FC<Props> = ({ source, onSignOut, onRegisterDevice, showDrawerButton, onOpenDrawer, initialDeviceId, onInitialDeviceFocused }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const { isLandscape, screenWidth } = useResponsive();
  const wideLandscape = isLandscape && screenWidth >= 1320;
  const {
    devices,
    openAlerts,
    now,
    isRinging,
    soundEnabled,
    setSoundEnabled,
    acknowledgeAlert,
    ackError,
  } = useMonitoring(source);

  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);

  React.useEffect(() => {
    if (!initialDeviceId) return;
    setSelectedDeviceId(initialDeviceId);
    onInitialDeviceFocused?.();
  }, [initialDeviceId, onInitialDeviceFocused]);

  const activeDevice: Device | null = React.useMemo(() => {
    if (!devices.length) return null;
    return devices.find(d => d.id === selectedDeviceId) ?? devices[0];
  }, [devices, selectedDeviceId]);

  const { filteredHistory, viewMode, setViewMode } = useDeviceHistory(
    source,
    activeDevice?.id ?? '',
    now
  );

  return (
    <View style={[styles.root, isRinging && styles.ringingRoot]}>
      {/* Top Tablet Header Console Bar */}
      <View style={styles.topBar}>
        {showDrawerButton && (
          <TouchableOpacity style={styles.drawerButton} onPress={onOpenDrawer} accessibilityRole="button" accessibilityLabel="Open console menu">
            <Text style={styles.drawerButtonText}>☰</Text>
          </TouchableOpacity>
        )}
        <View style={styles.topBarLeft}>
          <Text style={styles.hospitalTitle}>OXYGEN SUPPLY MONITORING CONSOLE</Text>
          <Text style={styles.stationMeta}>
            Nursing Station Central Desk · Active Staff: {source.userName() || 'Staff'}
          </Text>
        </View>

        <View style={styles.topBarRight}>
          <ConnectionIndicator mode={source.mode} online={devices.some(d => d.online)} />

          <TouchableOpacity
            style={[styles.actionBtn, !soundEnabled && styles.actionBtnMuted]}
            onPress={() => setSoundEnabled(!soundEnabled)}
          >
            <Text style={styles.actionBtnText}>
              {soundEnabled ? '🔔 Sound Alarm ON' : '🔕 Alarm Sound Muted'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.signOutBtn} onPress={onSignOut}>
            <Text style={styles.signOutBtnText}>Sign Out</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Actionable Banner */}
      <AlertBanner
        alerts={openAlerts}
        now={now}
        onAcknowledge={acknowledgeAlert}
        ackError={ackError}
      />

      {/* Multi-Pane Tablet Console Body */}
      <View style={[styles.body, isLandscape ? styles.bodyLandscape : styles.bodyPortrait]}>
        {/* Left Column: Device Selector & Hero Telemetry */}
        <View style={[styles.sidebarPane, isLandscape ? (wideLandscape ? styles.sidebarLandscape : styles.sidebarLandscapeCompact) : styles.sidebarPortrait]}>
          <Text style={styles.paneHeading}>Registered Supply Panels</Text>
          <ScrollView style={styles.deviceListScroll}>
            {devices.map(d => {
              const s = effectiveStatus(d, now);
              const isSelected = activeDevice?.id === d.id;
              const edgeColor = colors.statusEdges[s] || colors.muted;
              return (
                <TouchableOpacity
                  key={d.id}
                  style={[
                    styles.deviceItem,
                    { borderLeftColor: edgeColor },
                    isSelected && styles.deviceItemSelected,
                  ]}
                  onPress={() => setSelectedDeviceId(d.id)}
                  activeOpacity={0.8}
                >
                  <View style={styles.deviceItemHeader}>
                    <Text style={styles.deviceItemName}>{d.name}</Text>
                    <StatusBadge status={s} size="small" />
                  </View>
                  <Text style={styles.deviceItemMeta}>
                    {d.id} · {ago(d.lastHeartbeatMs, now)}
                  </Text>
                  <HeroMetric
                    value={d.value}
                    unit={d.unit}
                    trendFalling={d.trendFalling}
                    size="compact"
                    isOffline={s === 'TABLET_OFFLINE'}
                  />
                  <ThresholdIndicator
                    lowThreshold={d.lowThreshold}
                    criticalThreshold={d.criticalThreshold}
                    highThreshold={d.highThreshold}
                    unit={d.unit}
                  />
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {/* Center / Main Column: Live Camera & 24h Telemetry Chart */}
        <View style={[styles.mainPane, isLandscape ? (wideLandscape ? styles.mainLandscape : styles.mainLandscapeCompact) : styles.mainPortrait]}>
          <ScrollView contentContainerStyle={styles.mainScroll}>
            {/* Live Camera Feed Panel */}
            <View style={styles.panelCard}>
              <View style={styles.panelCardHeader}>
                <Text style={styles.panelCardTitle}>Live Camera Inspection</Text>
                <Text style={styles.panelCardSubtitle}>Vision Model Real-time Feedback</Text>
              </View>
              <CameraPreviewWidget source={source} onRegisterDevice={onRegisterDevice} />
            </View>

            {/* 24-Hour Telemetry Inspection Card */}
            {activeDevice && (
              <View style={styles.panelCard}>
                <View style={styles.panelCardHeader}>
                  <View>
                    <Text style={styles.panelCardTitle}>{activeDevice.name} — 24-Hour Trend</Text>
                    <Text style={styles.panelCardSubtitle}>
                      {activeDevice.id} · Thresholds: LOW {activeDevice.lowThreshold} / CRIT {activeDevice.criticalThreshold}{activeDevice.highThreshold != null ? ` / HIGH ${activeDevice.highThreshold}` : ''} {activeDevice.unit.replace('cm2', 'cm²')}
                    </Text>
                  </View>
                  <View style={styles.toggleGroup}>
                    <TouchableOpacity
                      style={[styles.toggleBtn, viewMode === 'chart' && styles.toggleBtnActive]}
                      onPress={() => setViewMode('chart')}
                    >
                      <Text
                        style={[
                          styles.toggleBtnText,
                          viewMode === 'chart' && styles.toggleBtnTextActive,
                        ]}
                      >
                        Chart View
                      </Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.toggleBtn, viewMode === 'table' && styles.toggleBtnActive]}
                      onPress={() => setViewMode('table')}
                    >
                      <Text
                        style={[
                          styles.toggleBtnText,
                          viewMode === 'table' && styles.toggleBtnTextActive,
                        ]}
                      >
                        Table View
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>

                {viewMode === 'chart' ? (
                  <HistoryChart
                    points={filteredHistory}
                    low={activeDevice.lowThreshold}
                    critical={activeDevice.criticalThreshold}
                    high={activeDevice.highThreshold}
                    unit={activeDevice.unit}
                    nowMs={now}
                    height={260}
                  />
                ) : (
                  <ReadingsTable points={filteredHistory} unit={activeDevice.unit} maxRows={300} />
                )}
              </View>
            )}
          </ScrollView>
        </View>

        {/* Right Column: Live Alert Feed (Landscape mode) */}
        {wideLandscape && (
          <View style={styles.alertsPane}>
            <Text style={styles.paneHeading}>Active Alerts</Text>
            <ScrollView style={styles.alertsScroll}>
              {openAlerts.length === 0 ? (
                <Text style={styles.emptyText}>All monitored units nominal.</Text>
              ) : (
                openAlerts.slice(0, 15).map(a => (
                  <View key={a.id} style={styles.alertRow}>
                    <View style={styles.alertRowTop}>
                      <StatusBadge status={a.type} size="small" />
                      <Text style={styles.alertTime}>{ago(a.createdMs ?? now, now)}</Text>
                    </View>
                    <Text style={styles.alertDevice}>{a.deviceId}</Text>
                    <Text style={styles.alertVal}>
                      {a.value == null ? '--' : a.value.toFixed(2)} {a.unit.replace('cm2', 'cm²')}
                    </Text>
                    <Text style={styles.alertState}>State: {a.state}</Text>
                  </View>
                ))
              )}
            </ScrollView>
          </View>
        )}
      </View>
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.page,
  },
  ringingRoot: {
    backgroundColor: colors.criticalLight,
  },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    backgroundColor: colors.surface,
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: colors.grid,
  },
  topBarLeft: {
    flex: 1,
    minWidth: 190,
  },
  drawerButton: {
    width: 42,
    height: 42,
    marginRight: 10,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    backgroundColor: colors.borderLight,
  },
  drawerButtonText: {
    color: colors.ink,
    fontSize: 23,
    fontWeight: '700',
  },
  hospitalTitle: {
    fontSize: 18,
    fontWeight: '900',
    color: colors.ink,
    letterSpacing: 0.5,
  },
  stationMeta: {
    fontSize: 12,
    color: colors.ink2,
    marginTop: 2,
  },
  topBarRight: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: 10,
  },
  actionBtn: {
    backgroundColor: colors.seriesLight,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  actionBtnMuted: {
    backgroundColor: colors.borderLight,
  },
  actionBtnText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.series,
  },
  signOutBtn: {
    backgroundColor: colors.criticalLight,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  signOutBtnText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.critical,
  },
  body: {
    flex: 1,
  },
  bodyLandscape: {
    flexDirection: 'row',
  },
  bodyPortrait: {
    flexDirection: 'column',
  },
  sidebarPane: {
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderRightColor: colors.grid,
    padding: 14,
  },
  sidebarLandscape: {
    width: 310,
  },
  sidebarLandscapeCompact: {
    width: 260,
  },
  sidebarPortrait: {
    maxHeight: 250,
    borderBottomWidth: 1,
    borderBottomColor: colors.grid,
  },
  paneHeading: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.ink,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 10,
  },
  deviceListScroll: {
    flex: 1,
  },
  deviceItem: {
    backgroundColor: colors.surface,
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: colors.grid,
    borderLeftWidth: 6, // Mirroring dashboard .panel status edge
  },
  deviceItemSelected: {
    borderColor: colors.series,
    backgroundColor: colors.seriesLight,
    borderWidth: 2,
    borderLeftWidth: 6,
  },
  deviceItemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  deviceItemName: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.ink,
    flex: 1,
  },
  deviceItemMeta: {
    fontSize: 11,
    color: colors.ink2,
    marginVertical: 2,
  },
  mainPane: {
    flex: 1,
    backgroundColor: colors.page,
  },
  mainLandscape: {
    flex: 2,
  },
  mainLandscapeCompact: {
    flex: 1,
  },
  mainPortrait: {
    flex: 1,
  },
  mainScroll: {
    padding: 16,
  },
  panelCard: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: colors.grid,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  panelCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  panelCardTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.ink,
  },
  panelCardSubtitle: {
    fontSize: 12,
    color: colors.ink2,
    marginTop: 2,
  },
  toggleGroup: {
    flexDirection: 'row',
    backgroundColor: colors.borderLight,
    borderRadius: 6,
    padding: 2,
  },
  toggleBtn: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 4,
  },
  toggleBtnActive: {
    backgroundColor: colors.surface,
    elevation: 1,
  },
  toggleBtnText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.ink2,
  },
  toggleBtnTextActive: {
    color: colors.series,
  },
  alertsPane: {
    width: 280,
    backgroundColor: colors.surface,
    borderLeftWidth: 1,
    borderLeftColor: colors.grid,
    padding: 14,
  },
  alertsScroll: {
    flex: 1,
  },
  alertRow: {
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  alertRowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  alertTime: {
    fontSize: 11,
    color: colors.ink2,
  },
  alertDevice: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.ink,
  },
  alertVal: {
    fontSize: 12,
    color: colors.series,
    fontWeight: '600',
  },
  alertState: {
    fontSize: 11,
    color: colors.ink2,
  },
  emptyText: {
    fontSize: 12,
    color: colors.muted,
    textAlign: 'center',
    marginTop: 20,
  },
});
