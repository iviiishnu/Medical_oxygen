import React from 'react';
import { createDrawerNavigator } from '@react-navigation/drawer';
import type { TabletDrawerParamList } from '../types/navigation';
import type { DataSource } from '../api/dataSource';
import { TabletConsoleScreen } from '../screens/tablet/TabletConsoleScreen';
import { MobileAlertsScreen } from '../screens/mobile/MobileAlertsScreen';
import { MobileCameraScreen } from '../screens/mobile/MobileCameraScreen';
import { MobileSettingsScreen } from '../screens/mobile/MobileSettingsScreen';
import { IncidentsScreen } from '../screens/mobile/IncidentsScreen';
import { AnalyticsScreen } from '../screens/mobile/AnalyticsScreen';
import { useResponsive } from '../hooks/useResponsive';
import { colors } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

const Drawer = createDrawerNavigator<TabletDrawerParamList>();

interface Props {
  source: DataSource;
  onSignOut: () => void;
  onToggleDemoMode: (enabled: boolean) => void;
  darkMode?: boolean;
  onToggleDarkMode?: (enabled: boolean) => void;
}

export const TabletNavigator: React.FC<Props> = ({
  source,
  onSignOut,
  onToggleDemoMode,
  darkMode = false,
  onToggleDarkMode = () => {},
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
        options={{ title: 'Dashboard', headerShown: false }}
      >
        {({ navigation, route }: any) => <TabletConsoleScreen
          source={source}
          onSignOut={onSignOut}
          onRegisterDevice={() => navigation.navigate('Settings', { focusRegistration: true })}
          showDrawerButton={!isLandscape}
          onOpenDrawer={() => navigation.openDrawer()}
          initialDeviceId={route?.params?.deviceId}
          onInitialDeviceFocused={() => navigation.setParams({ deviceId: undefined })}
        />}
      </Drawer.Screen>

      <Drawer.Screen
        name="Alerts"
        options={{ title: 'Alerts' }}
      >
        {({ navigation }: any) => <MobileAlertsScreen source={source} onCreateIncident={alertId => navigation.navigate('Incidents', { alertId })} onOpenDevice={deviceId => navigation.navigate('Console', { deviceId })} />}
      </Drawer.Screen>

      <Drawer.Screen name="History" options={{ title: 'History & Analytics' }}>
        {() => <AnalyticsScreen source={source} />}
      </Drawer.Screen>

      <Drawer.Screen name="Incidents" options={{ title: 'Incident Management' }}>
        {({ route, navigation }: any) => <IncidentsScreen source={source} initialAlertId={route?.params?.alertId} onInitialAlertHandled={() => navigation.setParams({ alertId: undefined })} />}
      </Drawer.Screen>

      <Drawer.Screen
        name="Camera"
        options={{ title: 'Live Monitoring' }}
      >
        {({ navigation }: any) => <MobileCameraScreen source={source} onRegisterDevice={() => navigation.navigate('Settings', { focusRegistration: true })} />}
      </Drawer.Screen>

      <Drawer.Screen
        name="Settings"
        options={{ title: 'Profile & Settings' }}
      >
        {({ route, navigation }: any) => (
          <MobileSettingsScreen
            source={source}
            onSignOut={onSignOut}
            onToggleDemoMode={onToggleDemoMode}
            darkMode={darkMode}
            onToggleDarkMode={onToggleDarkMode}
            focusRegistration={route?.params?.focusRegistration}
            onRegistrationFocused={() => navigation.setParams({ focusRegistration: undefined })}
          />
        )}
      </Drawer.Screen>
    </Drawer.Navigator>
  );
};
