import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Svg, { Path, Rect } from 'react-native-svg';
import type { DataSource } from '../../api/dataSource';
import { colors } from '../../theme/colors';
import { useMonitoring } from '../../hooks/useMonitoring';
import { useThemeColors } from '../../theme/ThemeContext';
import type { ThemePalette } from '../../theme/colors';

interface Props {
  source: DataSource;
  onSignOut: () => void;
  onToggleDemoMode: (enabled: boolean) => void;
}

export const MoreScreen: React.FC<Props> = ({ source, onSignOut, onToggleDemoMode }) => {
  const navigation = useNavigation<any>();
  const palette = useThemeColors(colors);
  const styles = createStyles(palette);
  const { devices } = useMonitoring(source);
  const onlineCount = devices.filter(d => d.online).length;

  const moreItems = [
    {
      title: 'Incidents',
      subtitle: 'Record causes, actions and follow-up',
      icon: '📝',
      onPress: () => navigation.navigate('Incidents'),
    },
    {
      title: 'Live Monitoring',
      subtitle: 'Select a panel, read a frame and start camera monitoring',
      icon: '📷',
      onPress: () => navigation.navigate('CameraStream'),
    },
    {
      title: 'Profile & Settings',
      subtitle: 'Account, appearance and backend connection',
      icon: '⚙️',
      onPress: () => navigation.navigate('SettingsScreen'),
    },
  ];

  return (
    <View style={styles.container}>
      {/* Top Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>More Options</Text>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Doctor Profile Banner */}
        <View style={styles.profileCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{source.userName().slice(0, 1).toUpperCase() || 'S'}</Text>
          </View>
          <View style={styles.profileInfo}>
            <Text style={styles.profileName}>{source.userName() || 'Staff'}</Text>
            <Text style={styles.profileSub}>Oxygen monitoring staff account</Text>
            <View style={styles.liveTag}>
              <View style={[styles.liveDot, !onlineCount && { backgroundColor: palette.muted }]} />
              <Text style={[styles.liveText, !onlineCount && { color: palette.muted }]}>{devices.length ? `${onlineCount} of ${devices.length} devices online` : 'No registered devices'}</Text>
            </View>
          </View>
        </View>

        {/* Menu Items */}
        <View style={styles.menuCard}>
          {moreItems.map((item, index) => (
            <React.Fragment key={item.title}>
              {index > 0 && <View style={styles.divider} />}
              <TouchableOpacity style={styles.menuItem} onPress={item.onPress} activeOpacity={0.7}>
                <Text style={styles.menuIcon}>{item.icon}</Text>
                <View style={styles.menuTextWrap}>
                  <Text style={styles.menuTitle}>{item.title}</Text>
                  <Text style={styles.menuSubtitle}>{item.subtitle}</Text>
                </View>
                <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
                  <Path d="M9 18L15 12L9 6" stroke={palette.muted} strokeWidth="2" strokeLinecap="round" />
                </Svg>
              </TouchableOpacity>
            </React.Fragment>
          ))}
        </View>

        {/* Sign Out Button */}
        <TouchableOpacity style={styles.signOutButton} onPress={onSignOut} activeOpacity={0.8}>
          <Text style={styles.signOutText}>Sign out</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.page,
  },
  header: {
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.ink,
  },
  scroll: {
    padding: 16,
    paddingBottom: 32,
    gap: 14,
  },
  profileCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.brandBlueLight,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  avatarText: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.brandBlue,
  },
  profileInfo: {
    flex: 1,
  },
  profileName: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.ink,
  },
  profileSub: {
    fontSize: 12,
    color: colors.ink2,
    marginTop: 2,
  },
  liveTag: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 6,
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.normal,
    marginRight: 5,
  },
  liveText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.normal,
  },
  menuCard: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 14,
  },
  menuIcon: {
    fontSize: 20,
    marginRight: 14,
  },
  menuTextWrap: {
    flex: 1,
  },
  menuTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.ink,
  },
  menuSubtitle: {
    fontSize: 11,
    color: colors.ink2,
    marginTop: 2,
  },
  divider: {
    height: 1,
    backgroundColor: colors.borderLight,
  },
  signOutButton: {
    backgroundColor: colors.criticalBg,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.criticalBorder,
    marginTop: 8,
  },
  signOutText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.critical,
  },
});
