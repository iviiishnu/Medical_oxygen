import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import type { MobileStackParamList } from '../../types/navigation';
import type { DataSource } from '../../api/dataSource';
import type { Device } from '../../types/monitoring';
import { useDeviceHistory } from '../../hooks/useDeviceHistory';
import { useResponsive } from '../../hooks/useResponsive';
import { StatusBadge } from '../../components/StatusBadge';
import { HeroMetric } from '../../components/HeroMetric';
import { ThresholdIndicator } from '../../components/ThresholdIndicator';
import { HistoryChart } from '../../components/HistoryChart';
import { ReadingsTable } from '../../components/ReadingsTable';
import { effectiveStatus, ago } from '../../utils/logic';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';

interface Props {
  source: DataSource;
}

type DeviceDetailRouteProp = RouteProp<MobileStackParamList, 'DeviceDetail'>;

export const MobileDeviceDetailScreen: React.FC<Props> = ({ source }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const route = useRoute<DeviceDetailRouteProp>();
  const { deviceId } = route.params;
  const { isLandscape } = useResponsive();

  const [device, setDevice] = useState<Device | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const unsub = source.onDevices(devices => {
      const found = devices.find(d => d.id === deviceId);
      if (found) setDevice(found);
    });
    return () => unsub();
  }, [source, deviceId]);

  const { filteredHistory, viewMode, setViewMode } = useDeviceHistory(
    source,
    deviceId,
    now
  );

  if (!device) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.loadingText}>Loading device telemetry...</Text>
      </View>
    );
  }

  const status = effectiveStatus(device, now);
  const edgeColor = colors.statusEdges[status] || colors.muted;

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      {/* Device Overview Card with signature dashboard status edge */}
      <View style={[styles.card, { borderLeftWidth: 6, borderLeftColor: edgeColor }]}>
        <View style={styles.topRow}>
          <View style={styles.titleWrap}>
            <Text style={styles.name}>{device.name}</Text>
            <Text style={styles.meta}>
              ID: {device.id} · updated {ago(device.lastHeartbeatMs, now)}
              {device.battery != null && ` · 🔋 ${Math.round(device.battery)}%`}
            </Text>
          </View>
          <StatusBadge status={status} size="large" />
        </View>

        <HeroMetric
          value={device.value}
          unit={device.unit}
          trendFalling={device.trendFalling}
          isOffline={status === 'TABLET_OFFLINE'}
          size="prominent"
        />

        <ThresholdIndicator
          lowThreshold={device.lowThreshold}
          criticalThreshold={device.criticalThreshold}
          highThreshold={device.highThreshold}
          unit={device.unit}
        />
      </View>

      {/* 24-Hour Inspection Card */}
      <View style={styles.card}>
        <View style={styles.chartHeader}>
          <Text style={styles.sectionTitle}>Last 24 Hours</Text>
          <View style={styles.toggleRow}>
            <TouchableOpacity
              style={[styles.toggleBtn, viewMode === 'chart' && styles.toggleBtnActive]}
              onPress={() => setViewMode('chart')}
            >
              <Text
                style={[
                  styles.toggleText,
                  viewMode === 'chart' && styles.toggleTextActive,
                ]}
              >
                Chart
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.toggleBtn, viewMode === 'table' && styles.toggleBtnActive]}
              onPress={() => setViewMode('table')}
            >
              <Text
                style={[
                  styles.toggleText,
                  viewMode === 'table' && styles.toggleTextActive,
                ]}
              >
                Table
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {viewMode === 'chart' ? (
          <HistoryChart
            points={filteredHistory}
            low={device.lowThreshold}
            critical={device.criticalThreshold}
                    high={device.highThreshold}
            unit={device.unit}
            nowMs={now}
            height={isLandscape ? 180 : 260}
          />
        ) : (
          <ReadingsTable points={filteredHistory} unit={device.unit} maxRows={300} />
        )}
      </View>
    </ScrollView>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  scroll: {
    padding: 14,
    backgroundColor: colors.page,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.page,
  },
  loadingText: {
    fontSize: 14,
    color: colors.ink2,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: colors.grid,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 10,
  },
  titleWrap: {
    flex: 1,
    marginRight: 8,
  },
  name: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.ink,
  },
  meta: {
    fontSize: 12,
    color: colors.ink2,
    marginTop: 2,
  },
  chartHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.ink,
  },
  toggleRow: {
    flexDirection: 'row',
    backgroundColor: colors.borderLight,
    borderRadius: 6,
    padding: 2,
  },
  toggleBtn: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
  },
  toggleBtnActive: {
    backgroundColor: colors.surface,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 1,
    elevation: 1,
  },
  toggleText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.ink2,
  },
  toggleTextActive: {
    color: colors.series,
  },
});
