import React, { useState } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity } from 'react-native';
import type { DataSource } from '../../api/dataSource';
import { useMonitoring } from '../../hooks/useMonitoring';
import { AlertCard } from '../../components/AlertCard';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';
import { useResponsive } from '../../hooks/useResponsive';

interface Props {
  source: DataSource;
}

export const TabletAlertHistoryScreen: React.FC<Props> = ({ source }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const { isLandscape, screenWidth } = useResponsive();
  const { alerts } = useMonitoring(source);
  const [filter, setFilter] = useState<'ALL' | 'OPEN' | 'ACKED' | 'RESOLVED'>('ALL');

  const filtered = alerts.filter(a => (filter === 'ALL' ? true : a.state === filter));

  return (
    <View style={styles.container}>
      <View style={[styles.header, isLandscape && screenWidth >= 900 ? styles.headerLandscape : styles.headerPortrait]}>
        <Text style={styles.title}>Hospital Oxygen Supply Alert Audit History</Text>
        <View style={styles.filters}>
          {(['ALL', 'OPEN', 'ACKED', 'RESOLVED'] as const).map(tab => (
            <TouchableOpacity
              key={tab}
              style={[styles.btn, filter === tab && styles.btnActive]}
              onPress={() => setFilter(tab)}
            >
              <Text style={[styles.btnText, filter === tab && styles.btnTextActive]}>
                {tab}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <FlatList
        data={filtered}
        keyExtractor={item => item.id}
        renderItem={({ item }) => <AlertCard alert={item} />}
        contentContainerStyle={styles.list}
      />
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.page,
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  headerLandscape: {
    flexDirection: 'row',
  },
  headerPortrait: {
    flexDirection: 'column',
    alignItems: 'stretch',
    gap: 10,
  },
  title: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.ink,
  },
  filters: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  btn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 6,
    backgroundColor: colors.borderLight,
  },
  btnActive: {
    backgroundColor: colors.ink, // Mirroring dashboard solid buttons
  },
  btnText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.ink2,
  },
  btnTextActive: {
    color: colors.surface,
  },
  list: {
    paddingBottom: 20,
  },
});
