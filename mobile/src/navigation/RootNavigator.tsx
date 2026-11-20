import React, { useState, useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { useResponsive } from '../hooks/useResponsive';
import type { DataSource } from '../api/dataSource';
import { createDemoDataSource } from '../api/demoDataSource';
import { createPostgresDataSource } from '../api/postgresDataSource';
import { MobileLoginScreen } from '../screens/mobile/MobileLoginScreen';
import { MobileNavigator } from './MobileNavigator';
import { TabletNavigator } from './TabletNavigator';
import { StorageService } from '../utils/storage';
import { notificationService } from '../services/notificationService';
import { ThemeProvider } from '../theme/ThemeContext';
import { colors } from '../theme/colors';
import { StatusBar } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

export const RootNavigator: React.FC = () => {
  const { isTablet } = useResponsive();
  const [source, setSource] = useState<DataSource>(() => createDemoDataSource());
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    // Load initial settings
    StorageService.getSettings().then(async settings => {
      if (settings.demoMode) {
        const demoSource = createDemoDataSource();
        setSource(demoSource);
        setIsAuthenticated(demoSource.signedIn());
      } else {
        const postgresSource = createPostgresDataSource();
        setSource(postgresSource);
        setIsAuthenticated(await postgresSource.restoreSession());
        if (postgresSource.signedIn()) notificationService.initialize();
      }
      setDarkMode(settings.darkMode);
    });
  }, []);

  const handleLoginSuccess = () => {
    setIsAuthenticated(true);
    if (source.mode === 'postgres') notificationService.initialize();
  };

  const handleSignOut = async () => {
    notificationService.stop();
    await source.signOut();
    setIsAuthenticated(false);
  };

  const handleToggleDemoMode = (demoEnabled: boolean) => {
    if (demoEnabled) {
      notificationService.stop();
      const demo = createDemoDataSource();
      setSource(demo);
      setIsAuthenticated(true);
    } else {
      const postgresSource = createPostgresDataSource();
      setSource(postgresSource);
      void postgresSource.restoreSession().then(restored => {
        setIsAuthenticated(restored);
        if (restored) notificationService.initialize();
      });
    }
  };

  return (
    <SafeAreaProvider>
    <ThemeProvider value={darkMode ? colors.dark : colors}>
    <StatusBar barStyle={darkMode ? 'light-content' : 'dark-content'} />
    <NavigationContainer theme={{
      dark: darkMode,
      colors: {
        primary: darkMode ? colors.dark.series : colors.series,
        background: darkMode ? colors.dark.page : colors.page,
        card: darkMode ? colors.dark.surface : colors.surface,
        text: darkMode ? colors.dark.ink : colors.ink,
        border: darkMode ? colors.dark.grid : colors.grid,
        notification: colors.critical,
      },
      fonts: {
        regular: { fontFamily: 'System', fontWeight: '400' },
        medium: { fontFamily: 'System', fontWeight: '500' },
        bold: { fontFamily: 'System', fontWeight: '700' },
        heavy: { fontFamily: 'System', fontWeight: '800' },
      },
    }}>
      <SafeAreaView style={{ flex: 1, backgroundColor: darkMode ? colors.dark.page : colors.page }} edges={['top', 'bottom']}>
      {!isAuthenticated ? (
        <MobileLoginScreen
          source={source}
          onLoginSuccess={handleLoginSuccess}
          onSwitchToDemo={() => handleToggleDemoMode(true)}
        />
      ) : isTablet ? (
        <TabletNavigator
          source={source}
          onSignOut={handleSignOut}
          onToggleDemoMode={handleToggleDemoMode}
          darkMode={darkMode}
          onToggleDarkMode={setDarkMode}
        />
      ) : (
        <MobileNavigator
          source={source}
          onSignOut={handleSignOut}
          onToggleDemoMode={handleToggleDemoMode}
          darkMode={darkMode}
          onToggleDarkMode={setDarkMode}
        />
      )}
      </SafeAreaView>
    </NavigationContainer>
    </ThemeProvider>
    </SafeAreaProvider>
  );
};

