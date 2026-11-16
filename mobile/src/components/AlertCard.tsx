import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { Alert } from '../types/monitoring';
import { StatusBadge } from './StatusBadge';
import { colors as baseColors, type ThemePalette } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

interface Props {
  alert: Alert;
}

export const AlertCard: React.FC<Props> = ({ alert }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const formattedUnit = alert.unit.replace('cm2', 'cm²');
  const dateStr = alert.createdMs ? new Date(alert.createdMs).toLocaleString() : '';

  return (
    <View style={styles.card}>
      <View style={styles.topRow}>
        <StatusBadge status={alert.type} size="small" />
        <Text style={styles.timestamp}>{dateStr}</Text>
      </View>

      <View style={styles.mainRow}>
        <Text style={styles.device}>{alert.deviceId}</Text>
        <Text style={styles.value}>
          {alert.value == null ? '--' : `${alert.value.toFixed(2)} ${formattedUnit}`}
        </Text>
      </View>

      <View style={styles.stateRow}>
        <View style={styles.stateTag}>
          <Text style={styles.stateText}>{alert.state}</Text>
        </View>
        <Text style={styles.metaText}>
          {alert.ackedMs ? `Acked by ${alert.ackedBy || 'Staff'}` : 'Unacknowledged'}
        </Text>
      </View>

      {alert.ackReason || alert.ackResolution ? (
        <View style={styles.reportBox}>
          <Text style={styles.reportTitle}>Acknowledgement report</Text>
          {!!alert.ackReason && <Text style={styles.reportText}>Reason: {alert.ackReason}</Text>}
          {!!alert.ackResolution && <Text style={styles.reportText}>Resolution: {alert.ackResolution}</Text>}
          {!!alert.ackNotes && <Text style={styles.reportText}>Notes: {alert.ackNotes}</Text>}
        </View>
      ) : null}

      {alert.resolvedMs ? (
        <Text style={styles.resolvedText}>
          Resolved: {new Date(alert.resolvedMs).toLocaleTimeString()}
        </Text>
      ) : null}
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: 8,
    padding: 12,
    marginVertical: 4,
    borderWidth: 1,
    borderColor: colors.grid,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  timestamp: {
    fontSize: 12,
    color: colors.ink2,
  },
  mainRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 6,
  },
  device: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.ink,
  },
  value: {
    fontSize: 15,
    fontWeight: '800',
    color: colors.series,
  },
  stateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  stateTag: {
    backgroundColor: colors.borderLight,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  stateText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.ink2,
  },
  metaText: {
    fontSize: 11,
    color: colors.ink2,
  },
  resolvedText: {
    fontSize: 11,
    color: colors.good,
    marginTop: 4,
  },
  reportBox: { marginTop: 9, padding: 9, borderRadius: 8, backgroundColor: colors.borderLight },
  reportTitle: { color: colors.ink, fontWeight: '700', fontSize: 12, marginBottom: 3 },
  reportText: { color: colors.ink2, fontSize: 11, lineHeight: 16 },
});
