import React from 'react';
import { Text } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { MobileTabParamList, MobileStackParamList } from '../types/navigation';
import type { DataSource } from '../api/dataSource';
import { MobileDashboardScreen } from '../screens/mobile/MobileDashboardScreen';
import { MobileDeviceDetailScreen } from '../screens/mobile/MobileDeviceDetailScreen';
import { MobileAlertsScreen } from '../screens/mobile/MobileAlertsScreen';
import { MobileCameraScreen } from '../screens/mobile/MobileCameraScreen';
import { MobileSettingsScreen } from '../screens/mobile/MobileSettingsScreen';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

const Tab = createBottomTabNavigator<MobileTabParamList>();
const Stack = createNativeStackNavigator<MobileStackParamList>();

interface Props {
  source: DataSource;
  onSignOut: () => void;
  onToggleDemoMode: (enabled: boolean) => void;
  darkMode: boolean;
  onToggleDarkMode: (enabled: boolean) => void;
}

function MonitorStack({ source }: { source: DataSource }) {
  const palette = useThemeColors(colors);
  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: palette.surface },
        headerTintColor: palette.series,
        headerTitleStyle: { fontWeight: '700', color: palette.ink },
      }}
    >
      <Stack.Screen
        name="MainTabs"
        options={{ headerShown: false }}
      >
        {() => <MobileDashboardScreen source={source} />}
      </Stack.Screen>

      <Stack.Screen
        name="DeviceDetail"
        options={({ route }) => ({
          title: route.params.deviceName || 'Supply Panel Detail',
        })}
      >
        {() => <MobileDeviceDetailScreen source={source} />}
      </Stack.Screen>
    </Stack.Navigator>
  );
}

export const MobileNavigator: React.FC<Props> = ({
  source,
  onSignOut,
  onToggleDemoMode,
  darkMode,
  onToggleDarkMode,
}) => {
  const insets = useSafeAreaInsets();
  const palette = useThemeColors(colors);
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarActiveTintColor: palette.series,
        tabBarInactiveTintColor: palette.ink2,
        tabBarStyle: {
          backgroundColor: palette.surface,
          borderTopColor: palette.grid,
          height: 56 + Math.max(insets.bottom, 6),
          paddingBottom: Math.max(insets.bottom, 6),
          paddingTop: 6,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: '600',
        },
        headerStyle: { backgroundColor: palette.surface },
        headerTitleStyle: { fontWeight: '800', color: palette.ink },
        tabBarIcon: ({ color }) => {
          let icon = '📊';
          if (route.name === 'MonitorTab') icon = '📊';
          else if (route.name === 'AlertsTab') icon = '🔔';
          else if (route.name === 'CameraTab') icon = '📷';
          else if (route.name === 'SettingsTab') icon = '⚙️';
          return <Text style={{ fontSize: 18, color }}>{icon}</Text>;
        },
      })}
    >
      <Tab.Screen
        name="MonitorTab"
        options={{ title: 'Monitor', headerShown: false }}
      >
        {() => <MonitorStack source={source} />}
      </Tab.Screen>

      <Tab.Screen
        name="AlertsTab"
        options={{ title: 'Alerts' }}
      >
        {() => <MobileAlertsScreen source={source} />}
      </Tab.Screen>

      <Tab.Screen
        name="CameraTab"
        options={{ title: 'Live Stream' }}
      >
        {({ navigation }) => <MobileCameraScreen source={source} onRegisterDevice={() => navigation.navigate('SettingsTab', { focusRegistration: true })} />}
      </Tab.Screen>

      <Tab.Screen
        name="SettingsTab"
        options={{ title: 'Settings' }}
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
      </Tab.Screen>
    </Tab.Navigator>
  );
};
