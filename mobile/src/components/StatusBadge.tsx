import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { label } from '../utils/logic';
import { colors as baseColors, type ThemePalette } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

const ICONS: Record<string, string> = {
  OK: '✓',
  LOW: '▼',
  CRITICAL: '⛔',
  UNCERTAIN: '?',
  MONITORING_LOST: '⚠',
  TABLET_OFFLINE: '⚠',
  TREND_FALLING: '↘',
  UNKNOWN: '•',
};

const STATUS_THEMES: Record<string, { bg: string; text: string }> = {
  OK: { bg: baseColors.good, text: '#ffffff' },
  LOW: { bg: baseColors.warning, text: baseColors.ink },
  CRITICAL: { bg: baseColors.critical, text: '#ffffff' },
  UNCERTAIN: { bg: baseColors.serious, text: '#ffffff' },
  MONITORING_LOST: { bg: baseColors.lost, text: '#ffffff' },
  TABLET_OFFLINE: { bg: baseColors.lost, text: '#ffffff' },
  TREND_FALLING: { bg: baseColors.warning, text: baseColors.ink },
  UNKNOWN: { bg: baseColors.muted, text: '#ffffff' },
};

interface Props {
  status: string;
  size?: 'small' | 'medium' | 'large';
}

export const StatusBadge: React.FC<Props> = ({ status, size = 'medium' }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const icon = ICONS[status] ?? '•';
  const textLabel = label(status);
  const theme = STATUS_THEMES[status] ?? STATUS_THEMES.UNKNOWN;

  const isSmall = size === 'small';
  const isLarge = size === 'large';

  return (
    <View
      style={[
        styles.badge,
        { backgroundColor: theme.bg },
        isSmall && styles.badgeSmall,
        isLarge && styles.badgeLarge,
      ]}
    >
      <Text
        style={[
          styles.icon,
          { color: theme.text },
          isSmall && styles.iconSmall,
          isLarge && styles.iconLarge,
        ]}
      >
        {icon}
      </Text>
      <Text
        style={[
          styles.label,
          { color: theme.text },
          isSmall && styles.labelSmall,
          isLarge && styles.labelLarge,
        ]}
      >
        {textLabel}
      </Text>
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999, // Pill shape mirroring dashboard .badge
    alignSelf: 'flex-start',
  },
  badgeSmall: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
  },
  badgeLarge: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
  },
  icon: {
    fontSize: 12,
    fontWeight: '700',
    marginRight: 5,
  },
  iconSmall: {
    fontSize: 10,
    marginRight: 4,
  },
  iconLarge: {
    fontSize: 14,
    marginRight: 6,
  },
  label: {
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
  labelSmall: {
    fontSize: 11,
  },
  labelLarge: {
    fontSize: 15,
  },
});
