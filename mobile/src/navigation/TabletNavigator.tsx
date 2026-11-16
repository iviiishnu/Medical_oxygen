import React from 'react';
import { createDrawerNavigator } from '@react-navigation/drawer';
import type { TabletDrawerParamList } from '../types/navigation';
import type { DataSource } from '../api/dataSource';
import { TabletConsoleScreen } from '../screens/tablet/TabletConsoleScreen';
import { TabletAlertHistoryScreen } from '../screens/tablet/TabletAlertHistoryScreen';
import { MobileCameraScreen } from '../screens/mobile/MobileCameraScreen';
import { MobileSettingsScreen } from '../screens/mobile/MobileSettingsScreen';
import { useResponsive } from '../hooks/useResponsive';
import { colors } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

const Drawer = createDrawerNavigator<TabletDrawerParamList>();

interface Props {
  source: DataSource;
  onSignOut: () => void;
  onToggleDemoMode: (enabled: boolean) => void;
  darkMode: boolean;
  onToggleDarkMode: (enabled: boolean) => void;
}

export const TabletNavigator: React.FC<Props> = ({
  source,
  onSignOut,
  onToggleDemoMode,
  darkMode,
  onToggleDarkMode,
}) => {
  const { isLandscape } = useResponsive();
  const palette = useThemeColors(colors);
  return (
    <Drawer.Navigator
      screenOptions={{
        drawerType: isLandscape ? 'permanent' : 'front',
        drawerStyle: {
          width: 240,
          backgroundColor: palette.surface,
          borderRightColor: palette.grid,
        },
        headerStyle: { backgroundColor: palette.surface },
        headerTitleStyle: { fontWeight: '800', color: palette.ink },
        drawerActiveTintColor: palette.series,
        drawerActiveBackgroundColor: palette.seriesLight,
        drawerInactiveTintColor: palette.ink2,
        drawerLabelStyle: { fontWeight: '700', fontSize: 13 },
      }}
    >
      <Drawer.Screen
        name="Console"
        options={{ title: 'Clinical Console', headerShown: false }}
      >
        {({ navigation }) => <TabletConsoleScreen
          source={source}
          onSignOut={onSignOut}
          onRegisterDevice={() => navigation.navigate('Settings', { focusRegistration: true })}
          showDrawerButton={!isLandscape}
          onOpenDrawer={() => navigation.openDrawer()}
        />}
      </Drawer.Screen>

      <Drawer.Screen
        name="Alerts"
        options={{ title: 'Alert Audit Log' }}
      >
        {() => <TabletAlertHistoryScreen source={source} />}
      </Drawer.Screen>

      <Drawer.Screen
        name="Camera"
        options={{ title: 'Panel Camera Feed' }}
      >
        {({ navigation }) => <MobileCameraScreen source={source} onRegisterDevice={() => navigation.navigate('Settings', { focusRegistration: true })} />}
      </Drawer.Screen>

      <Drawer.Screen
        name="Settings"
        options={{ title: 'Console Settings' }}
      >
        {({ route, navigation }) => (
          <MobileSettingsScreen
            source={source}
            onSignOut={onSignOut}
            onToggleDemoMode={onToggleDemoMode}
            darkMode={darkMode}
            onToggleDarkMode={onToggleDarkMode}
            focusRegistration={route.params?.focusRegistration}
            onRegistrationFocused={() => navigation.setParams({ focusRegistration: undefined })}
          />
        )}
      </Drawer.Screen>
    </Drawer.Navigator>
  );
};
