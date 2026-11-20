import React from 'react';
import { View, Text, StyleSheet, FlatList } from 'react-native';
import type { Point } from '../types/monitoring';
import { StatusBadge } from './StatusBadge';
import { colors } from '../theme/colors';

interface Props {
  points: Point[];
  unit: string;
  maxRows?: number;
}

export const ReadingsTable: React.FC<Props> = ({ points, unit, maxRows = 200 }) => {
  const reversedData = React.useMemo(
    () => [...points].reverse().slice(0, maxRows),
    [points, maxRows]
  );

  const formattedUnit = unit.replace('cm2', 'cm²');

  const renderItem = ({ item }: { item: Point }) => (
    <View style={styles.row}>
      <Text style={styles.cellTime}>
        {new Date(item.t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </Text>
      <Text style={styles.cellVal}>
        {item.v == null ? '—' : `${item.v.toFixed(2)} ${formattedUnit}`}
      </Text>
      <View style={styles.cellStatus}>
        <StatusBadge status={item.status} size="small" />
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={[styles.headerCell, styles.cellTime]}>Time</Text>
        <Text style={[styles.headerCell, styles.cellVal]}>Reading</Text>
        <Text style={[styles.headerCell, styles.cellStatus]}>Status</Text>
      </View>
      <FlatList
        data={reversedData}
        keyExtractor={(item: Point) => String(item.t)}
        renderItem={renderItem}
        style={styles.list}
        nestedScrollEnabled={true}
        initialNumToRender={15}
        maxToRenderPerBatch={20}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No historical data available</Text>
          </View>
        }
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.surface,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.grid,
    overflow: 'hidden',
    maxHeight: 260,
    marginVertical: 6,
  },
  headerRow: {
    flexDirection: 'row',
    backgroundColor: colors.page,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.grid,
  },
  headerCell: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.ink2,
    textTransform: 'uppercase',
  },
  list: {
    maxHeight: 220,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  cellTime: {
    flex: 1.2,
    fontSize: 12,
    color: colors.ink2,
  },
  cellVal: {
    flex: 1.2,
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
  },
  cellStatus: {
    flex: 1.1,
    alignItems: 'flex-start',
  },
  empty: {
    padding: 24,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 12,
    color: colors.muted,
  },
});
