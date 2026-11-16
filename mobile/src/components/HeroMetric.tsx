import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { StatusBadge } from './StatusBadge';
import { colors as baseColors, type ThemePalette } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

interface Props {
  value: number | null;
  unit: string;
  trendFalling?: boolean;
  isOffline?: boolean;
  size?: 'compact' | 'normal' | 'prominent';
}

export const HeroMetric: React.FC<Props> = ({
  value,
  unit,
  trendFalling = false,
  isOffline = false,
  size = 'normal',
}) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const displayVal = value == null ? '--' : value.toFixed(2);
  const formattedUnit = unit.replace('cm2', 'cm²');

  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <Text
          style={[
            styles.value,
            size === 'compact' && styles.valueCompact,
            size === 'prominent' && styles.valueProminent,
            isOffline && styles.valueOffline,
          ]}
        >
          {displayVal}
        </Text>
        <Text
          style={[
            styles.unit,
            size === 'compact' && styles.unitCompact,
            size === 'prominent' && styles.unitProminent,
          ]}
        >
          {formattedUnit}
        </Text>
      </View>
      {trendFalling && (
        <View style={styles.trendWrap}>
          <StatusBadge status="TREND_FALLING" size="small" />
        </View>
      )}
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    marginVertical: 4,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  value: {
    fontSize: 48,
    fontWeight: '700',
    color: colors.ink, // Mirroring dashboard .hero-num color: var(--ink)
    letterSpacing: -1,
  },
  valueCompact: {
    fontSize: 34,
  },
  valueProminent: {
    fontSize: 64, // Exact match to dashboard .hero-num 64px
  },
  valueOffline: {
    color: colors.muted, // Mirroring dashboard .hero-num.stale
    textDecorationLine: 'line-through',
  },
  unit: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.ink2, // Mirroring dashboard .hero-unit: var(--ink-2)
    marginLeft: 8,
  },
  unitCompact: {
    fontSize: 14,
    marginLeft: 4,
  },
  unitProminent: {
    fontSize: 20,
    marginLeft: 10,
  },
  trendWrap: {
    marginTop: 6,
  },
});
