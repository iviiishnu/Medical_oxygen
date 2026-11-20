import React from 'react';
import { useNavigation } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import Svg, { Path, Rect, Circle } from 'react-native-svg';
import type { DataSource } from '../api/dataSource';
import { MobileDashboardScreen } from '../screens/mobile/MobileDashboardScreen';
import { MobileAlertsScreen } from '../screens/mobile/MobileAlertsScreen';
import { AnalyticsScreen } from '../screens/mobile/AnalyticsScreen';
import { MoreScreen } from '../screens/mobile/MoreScreen';
import { MobileDeviceDetailScreen } from '../screens/mobile/MobileDeviceDetailScreen';
import { MobileCameraScreen } from '../screens/mobile/MobileCameraScreen';
import { MobileSettingsScreen } from '../screens/mobile/MobileSettingsScreen';
import { IncidentsScreen } from '../screens/mobile/IncidentsScreen';
import { colors } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

interface Props {
  source: DataSource;
  onSignOut: () => void;
  onToggleDemoMode: (enabled: boolean) => void;
  darkMode?: boolean;
  onToggleDarkMode?: (enabled: boolean) => void;
}

function HomeStackNavigator({ source, onSignOut }: { source: DataSource; onSignOut: () => void }) {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="HomeScreen">
        {() => <MobileDashboardScreen source={source} onSignOut={onSignOut} />}
      </Stack.Screen>
      <Stack.Screen name="DeviceDetail">
        {() => <MobileDeviceDetailScreen source={source} />}
      </Stack.Screen>
    </Stack.Navigator>
  );
}

function LiveMonitoringScreen({ source }: { source: DataSource }) {
  const navigation = useNavigation<any>();
  return <MobileCameraScreen source={source} onRegisterDevice={() => navigation.navigate('MoreTab', { screen: 'SettingsScreen', params: { focusRegistration: true } })} />;
}

function MoreStackNavigator({
  source,
  onSignOut,
  onToggleDemoMode,
  darkMode,
  onToggleDarkMode,
}: {
  source: DataSource;
  onSignOut: () => void;
  onToggleDemoMode: (enabled: boolean) => void;
  darkMode?: boolean;
  onToggleDarkMode?: (enabled: boolean) => void;
}) {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="MoreMain">
        {() => (
          <MoreScreen
            source={source}
            onSignOut={onSignOut}
            onToggleDemoMode={onToggleDemoMode}
          />
        )}
      </Stack.Screen>
      <Stack.Screen name="Incidents">
        {({ route, navigation }: any) => <IncidentsScreen source={source} initialAlertId={route?.params?.alertId} onInitialAlertHandled={() => navigation.setParams({ alertId: undefined })} />}
      </Stack.Screen>
      <Stack.Screen name="CameraStream">
        {({ navigation }: any) => <MobileCameraScreen source={source} onRegisterDevice={() => navigation.navigate('SettingsScreen', { focusRegistration: true })} />}
      </Stack.Screen>
      <Stack.Screen name="SettingsScreen">
        {({ route, navigation }: any) => (
          <MobileSettingsScreen
            source={source}
            onSignOut={onSignOut}
            onToggleDemoMode={onToggleDemoMode}
            darkMode={!!darkMode}
            onToggleDarkMode={onToggleDarkMode || (() => {})}
            focusRegistration={route?.params?.focusRegistration}
            onRegistrationFocused={() => navigation.setParams({ focusRegistration: undefined })}
          />
        )}
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
  const palette = useThemeColors(colors);
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: palette.series,
        tabBarInactiveTintColor: palette.ink2,
        tabBarStyle: {
          backgroundColor: palette.surface,
          borderTopColor: palette.grid,
          height: 60,
          paddingBottom: 8,
          paddingTop: 6,
        },
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: '700',
        },
      }}
    >
      {/* 1. Home Tab */}
      <Tab.Screen
        name="HomeTab"
        options={{
          title: 'Home',
          tabBarIcon: ({ color, focused }: { color: string; focused: boolean }) => (
            <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
              <Path
                d="M3 9.5L12 3L21 9.5V20C21 20.5523 20.5523 21 20 21H4C3.44772 21 3 20.5523 3 20V9.5Z"
                stroke={color}
                strokeWidth={focused ? 2.4 : 1.8}
                fill={focused ? palette.seriesLight : 'none'}
              />
              <Path d="M9 21V12H15V21" stroke={color} strokeWidth={focused ? 2.4 : 1.8} />
            </Svg>
          ),
        }}
      >
        {() => <HomeStackNavigator source={source} onSignOut={onSignOut} />}
      </Tab.Screen>

      {/* 2. Devices Tab */}
      <Tab.Screen
        name="DevicesTab"
        options={{
          title: 'Monitor',
          tabBarIcon: ({ color, focused }: { color: string; focused: boolean }) => (
            <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
              <Rect
                x="2"
                y="3"
                width="20"
                height="14"
                rx="2"
                stroke={color}
                strokeWidth={focused ? 2.4 : 1.8}
              />
              <Path
                d="M8 21H16M12 17V21"
                stroke={color}
                strokeWidth={focused ? 2.4 : 1.8}
                strokeLinecap="round"
              />
            </Svg>
          ),
        }}
      >
        {() => <LiveMonitoringScreen source={source} />}
      </Tab.Screen>

      {/* 3. Alerts Tab */}
      <Tab.Screen
        name="AlertsTab"
        options={{
          title: 'Alerts',
          tabBarIcon: ({ color, focused }: { color: string; focused: boolean }) => (
            <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
              <Path
                d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0"
                stroke={color}
                strokeWidth={focused ? 2.4 : 1.8}
                strokeLinecap="round"
                strokeLinejoin="round"
                fill={focused ? palette.seriesLight : 'none'}
              />
            </Svg>
          ),
        }}
      >
        {() => <MobileAlertsScreen source={source} />}
      </Tab.Screen>

      {/* 4. History Tab */}
      <Tab.Screen
        name="AnalyticsTab"
        options={{
          title: 'History',
          tabBarIcon: ({ color, focused }: { color: string; focused: boolean }) => (
            <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
              <Path d="M18 20V10M12 20V4M6 20V14" stroke={color} strokeWidth={focused ? 2.6 : 2} strokeLinecap="round" />
            </Svg>
          ),
        }}
      >
        {() => <AnalyticsScreen source={source} />}
      </Tab.Screen>

      {/* 5. More Tab */}
      <Tab.Screen
        name="MoreTab"
        options={{
          title: 'More',
          tabBarIcon: ({ color, focused }: { color: string; focused: boolean }) => (
            <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
              <Circle cx="5" cy="12" r="1.8" fill={color} />
              <Circle cx="12" cy="12" r="1.8" fill={color} />
              <Circle cx="19" cy="12" r="1.8" fill={color} />
            </Svg>
          ),
        }}
      >
        {() => (
          <MoreStackNavigator
            source={source}
            onSignOut={onSignOut}
            onToggleDemoMode={onToggleDemoMode}
            darkMode={darkMode}
            onToggleDarkMode={onToggleDarkMode}
          />
        )}
      </Tab.Screen>
    </Tab.Navigator>
  );
};
