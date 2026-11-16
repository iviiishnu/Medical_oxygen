import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors as baseColors, type ThemePalette } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

interface Props {
  mode: 'postgres' | 'demo';
  online: boolean;
}

export const ConnectionIndicator: React.FC<Props> = ({ mode, online }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  return (
    <View style={styles.pill}>
      <View
        style={[
          styles.dot,
          mode === 'demo' ? styles.dotDemo : online ? styles.dotOnline : styles.dotOffline,
        ]}
      />
      <Text style={styles.text}>
        {mode === 'demo' ? 'DEMO MODE' : online ? 'CONNECTED' : 'DISCONNECTED'}
      </Text>
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.borderLight, // #f0efec
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 5,
  },
  dotOnline: {
    backgroundColor: colors.good, // Mirroring dashboard --good: #0ca30c
  },
  dotDemo: {
    backgroundColor: colors.serious, // Mirroring dashboard .demo: var(--serious) #ec835a
  },
  dotOffline: {
    backgroundColor: colors.critical, // Mirroring dashboard --critical: #d03b3b
  },
  text: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.ink2, // Mirroring dashboard --ink-2: #52514e
    letterSpacing: 0.5,
  },
});
