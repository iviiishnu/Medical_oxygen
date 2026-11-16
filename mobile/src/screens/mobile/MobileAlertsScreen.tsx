import React, { useState } from 'react';
import {
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
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';

interface Props {
  source: DataSource;
}

export const MobileAlertsScreen: React.FC<Props> = ({ source }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const {
    alerts,
    openAlerts,
    now,
    acknowledgeAlert,
    ackError,
  } = useMonitoring(source);

  const [filter, setFilter] = useState<'ALL' | 'OPEN' | 'ACKED' | 'RESOLVED'>('ALL');
  const [refreshing, setRefreshing] = useState(false);

  const filteredAlerts = React.useMemo(() => {
    if (filter === 'ALL') return alerts;
    return alerts.filter(a => a.state === filter);
  }, [alerts, filter]);

  const onRefresh = () => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 600);
  };

  return (
    <View style={styles.container}>
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

      <FlatList
        data={filteredAlerts}
        keyExtractor={item => item.id}
        renderItem={({ item }) => <AlertCard alert={item} />}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No alerts matching filter criteria in the last 24 hours.</Text>
          </View>
        }
      />
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.page,
  },
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
