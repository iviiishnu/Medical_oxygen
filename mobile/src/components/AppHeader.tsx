import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import Svg, { Path, Rect, Circle } from 'react-native-svg';
import { colors } from '../theme/colors';

interface Props {
  onOpenDrawer?: () => void;
  onPressAlerts?: () => void;
  unreadAlertCount?: number;
}

export const AppHeader: React.FC<Props> = ({
  onOpenDrawer,
  onPressAlerts,
  unreadAlertCount = 2,
}) => {
  return (
    <View style={styles.container}>
      {/* Left: Hamburger menu */}
      <TouchableOpacity
        style={styles.iconButton}
        onPress={onOpenDrawer}
        activeOpacity={0.7}
        accessibilityLabel="Open navigation menu"
      >
        <Svg width={22} height={22} viewBox="0 0 24 24" fill="none">
          <Path
            d="M3 12H21M3 6H21M3 18H21"
            stroke={colors.ink}
            strokeWidth={2.2}
            strokeLinecap="round"
          />
        </Svg>
      </TouchableOpacity>

      {/* Center/Left: Medigas Brand Logo */}
      <View style={styles.brandRow}>
        <View style={styles.logoBadge}>
          <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
            <Rect width={24} height={24} rx={6} fill="#ef4444" />
            <Path
              d="M12 5V19M5 12H19"
              stroke="#ffffff"
              strokeWidth={3}
              strokeLinecap="round"
            />
          </Svg>
        </View>
        <View style={styles.brandTextWrap}>
          <Text style={styles.brandTitle}>MEDIGAS</Text>
          <Text style={styles.brandSubtitle}>Doctor Portal</Text>
        </View>
      </View>

      {/* Right: Notification Bell & Profile Avatar */}
      <View style={styles.rightGroup}>
        <TouchableOpacity
          style={styles.iconButton}
          onPress={onPressAlerts}
          activeOpacity={0.7}
          accessibilityLabel="Alert notifications"
        >
          <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
            <Path
              d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0"
              stroke={colors.ink}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </Svg>
          {unreadAlertCount > 0 && (
            <View style={styles.badgeDot}>
              <Text style={styles.badgeText}>{unreadAlertCount}</Text>
            </View>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.avatarButton}
          onPress={onOpenDrawer}
          activeOpacity={0.7}
        >
          <Text style={styles.avatarText}>DS</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    height: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  iconButton: {
    padding: 6,
    position: 'relative',
    justifyContent: 'center',
    alignItems: 'center',
  },
  brandRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: 8,
  },
  logoBadge: {
    marginRight: 8,
    shadowColor: '#ef4444',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3,
    elevation: 2,
  },
  brandTextWrap: {
    justifyContent: 'center',
  },
  brandTitle: {
    fontSize: 14,
    fontWeight: '900',
    color: colors.ink,
    letterSpacing: 0.8,
  },
  brandSubtitle: {
    fontSize: 10,
    color: colors.ink2,
    fontWeight: '500',
    marginTop: -1,
  },
  rightGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  badgeDot: {
    position: 'absolute',
    top: 3,
    right: 3,
    backgroundColor: colors.critical,
    borderRadius: 8,
    minWidth: 14,
    height: 14,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 2,
  },
  badgeText: {
    color: '#ffffff',
    fontSize: 9,
    fontWeight: '800',
  },
  avatarButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#dbeafe',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: '#bfdbfe',
  },
  avatarText: {
    fontSize: 11,
    fontWeight: '800',
    color: colors.brandBlue,
  },
});
