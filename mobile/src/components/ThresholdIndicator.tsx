import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors as baseColors, type ThemePalette } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

interface Props {
  lowThreshold: number;
  criticalThreshold: number;
  highThreshold?: number | null;
  unit: string;
}

export const ThresholdIndicator: React.FC<Props> = ({
  lowThreshold,
  criticalThreshold,
  highThreshold,
  unit,
}) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const formattedUnit = unit.replace('cm2', 'cm²');

  return (
    <View style={styles.container}>
      <Text style={styles.text}>
        LOW below <Text style={styles.bold}>{lowThreshold}</Text> · CRITICAL below{' '}
        <Text style={styles.bold}>{criticalThreshold}</Text>{highThreshold != null ? <> · HIGH above <Text style={styles.bold}>{highThreshold}</Text></> : null} {formattedUnit}
      </Text>
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    paddingVertical: 4,
  },
  text: {
    fontSize: 12,
    color: colors.ink2, // Mirroring dashboard .muted: var(--ink-2)
  },
  bold: {
    fontWeight: '700',
    color: colors.ink,
  },
});
