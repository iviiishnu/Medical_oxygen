import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { MobileStackParamList } from '../../types/navigation';
import type { DataSource } from '../../api/dataSource';
import { useMonitoring } from '../../hooks/useMonitoring';
import { useResponsive } from '../../hooks/useResponsive';
import { StatusBadge } from '../../components/StatusBadge';
import { HeroMetric } from '../../components/HeroMetric';
import { ThresholdIndicator } from '../../components/ThresholdIndicator';
import { AlertBanner } from '../../components/AlertBanner';
import { ConnectionIndicator } from '../../components/ConnectionIndicator';
import { effectiveStatus, ago } from '../../utils/logic';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

interface Props {
  source: DataSource;
}

export const MobileDashboardScreen: React.FC<Props> = ({ source }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const navigation = useNavigation<NativeStackNavigationProp<MobileStackParamList>>();
  const { isLandscape, columns } = useResponsive();
  const insets = useSafeAreaInsets();
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

  const [refreshing, setRefreshing] = React.useState(false);

  const onRefresh = React.useCallback(() => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 800);
  }, []);

  return (
    <View style={[styles.container, isRinging && styles.ringingBackground]}>
      {/* Top Station Header */}
      <View style={[styles.header, { paddingTop: Math.max(insets.top, 8) + 10 }]}>
        <View style={styles.headerLeft}>
          <Text style={styles.headerTitle}>Oxygen Supply</Text>
          <Text style={styles.headerSubtitle}>
            Hospital Monitoring Console · {source.userName() || 'Staff'}
          </Text>
        </View>
        <View style={styles.headerRight}>
          <ConnectionIndicator mode={source.mode} online={devices.some(d => d.online)} />
          <TouchableOpacity
            style={[styles.soundBtn, !soundEnabled && styles.soundBtnMuted]}
            onPress={() => setSoundEnabled(!soundEnabled)}
            activeOpacity={0.7}
          >
            <Text style={styles.soundBtnText}>{soundEnabled ? '🔔 Alarm ON' : '🔕 Muted'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Persistent Actionable Alert Banner */}
      <AlertBanner
        alerts={openAlerts}
        now={now}
        onAcknowledge={acknowledgeAlert}
        ackError={ackError}
      />

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {devices.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyText}>No monitoring tablets registered yet.</Text>
          </View>
        ) : (
          <View style={[styles.grid, columns > 1 && styles.gridLandscape]}>
            {devices.map(d => {
              const s = effectiveStatus(d, now);
              const edgeColor = colors.statusEdges[s] || colors.muted;
              return (
                <TouchableOpacity
                  key={d.id}
                  style={[
                    styles.deviceCard,
                    { borderLeftColor: edgeColor },
                    columns > 1 && { width: `${100 / columns - 2}%` },
                  ]}
                  activeOpacity={0.85}
                  onPress={() =>
                    navigation.navigate('DeviceDetail', {
                      deviceId: d.id,
                      deviceName: d.name,
                    })
                  }
                >
                  <View style={styles.cardHeader}>
                    <View style={styles.cardTitleWrap}>
                      <Text style={styles.deviceName} numberOfLines={1}>
                        {d.name}
                      </Text>
                      <Text style={styles.deviceMeta}>
                        {d.id} · updated {ago(d.lastHeartbeatMs, now)}
                        {d.battery != null && ` · 🔋 ${Math.round(d.battery)}%`}
                      </Text>
                    </View>
                    <StatusBadge status={s} />
                  </View>

                  <HeroMetric
                    value={d.value}
                    unit={d.unit}
                    trendFalling={d.trendFalling}
                    isOffline={s === 'TABLET_OFFLINE'}
                  />

                  <ThresholdIndicator
                    lowThreshold={d.lowThreshold}
                    criticalThreshold={d.criticalThreshold}
                    unit={d.unit}
                  />

                  <View style={styles.cardFooter}>
                    <Text style={styles.viewDetailsText}>Tap for 24h history & data &gt;</Text>
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>
        )}
      </ScrollView>
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.page,
  },
  ringingBackground: {
    backgroundColor: colors.criticalLight,
  },
  header: {
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: colors.grid,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerLeft: {
    flex: 1,
  },
  headerRight: {
    alignItems: 'flex-end',
    gap: 6,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: colors.ink,
  },
  headerSubtitle: {
    fontSize: 12,
    lineHeight: 17,
    color: colors.ink2,
    marginTop: 2,
  },
  soundBtn: {
    backgroundColor: colors.seriesLight,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  soundBtnMuted: {
    backgroundColor: colors.borderLight,
  },
  soundBtnText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.series,
  },
  scrollContent: {
    padding: 12,
  },
  emptyCard: {
    padding: 30,
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.grid,
  },
  emptyText: {
    fontSize: 14,
    color: colors.muted,
  },
  grid: {
    flexDirection: 'column',
  },
  gridLandscape: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  deviceCard: {
    backgroundColor: colors.surface,
    borderRadius: 12, // Mirroring dashboard .panel { border-radius: 12px; }
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.grid,
    borderLeftWidth: 6, // Signature dashboard status edge accent (.st-*-edge)
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  cardTitleWrap: {
    flex: 1,
    marginRight: 8,
  },
  deviceName: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.ink,
  },
  deviceMeta: {
    fontSize: 11,
    color: colors.ink2,
    marginTop: 2,
  },
  cardFooter: {
    marginTop: 10,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    paddingTop: 8,
    alignItems: 'flex-end',
  },
  viewDetailsText: {
    fontSize: 11,
    color: colors.series,
    fontWeight: '600',
  },
});
