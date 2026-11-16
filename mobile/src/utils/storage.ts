import AsyncStorage from '@react-native-async-storage/async-storage';
import type { DeviceRegistration } from '../types/monitoring';

const TOKEN_KEY = '@o2_auth_token';
const USER_KEY = '@o2_user_profile';
const SETTINGS_KEY = '@o2_app_settings';
const REGISTRATIONS_KEY = '@o2_registered_panels';

export interface AppSettings {
  demoMode: boolean;
  soundEnabled: boolean;
  visionApiUrl: string;
  darkMode: boolean;
}

export const defaultSettings: AppSettings = {
  demoMode: false,
  soundEnabled: true,
  visionApiUrl: 'http://10.0.2.2:8000', // Change to the computer's LAN address on a physical device.
  darkMode: false,
};

export const StorageService = {
  async saveAuthToken(token: string): Promise<void> {
    try {
      await AsyncStorage.setItem(TOKEN_KEY, token);
    } catch (e) {
      console.warn('Storage: failed to save auth token', e);
    }
  },

  async getAuthToken(): Promise<string | null> {
    try {
      return await AsyncStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },

  async clearAuth(): Promise<void> {
    try {
      await AsyncStorage.multiRemove([TOKEN_KEY, USER_KEY]);
    } catch (e) {
      console.warn('Storage: failed to clear auth', e);
    }
  },

  async saveSettings(settings: Partial<AppSettings>): Promise<void> {
    try {
      const existing = await this.getSettings();
      const updated = { ...existing, ...settings };
      await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(updated));
    } catch (e) {
      console.warn('Storage: failed to save settings', e);
    }
  },

  async getSettings(): Promise<AppSettings> {
    try {
      const val = await AsyncStorage.getItem(SETTINGS_KEY);
      if (!val) return defaultSettings;
      return { ...defaultSettings, ...JSON.parse(val) };
    } catch {
      return defaultSettings;
    }
  },

  async getRegisteredPanels(): Promise<DeviceRegistration[]> {
    try {
      const value = await AsyncStorage.getItem(REGISTRATIONS_KEY);
      return value ? JSON.parse(value) as DeviceRegistration[] : [];
    } catch {
      return [];
    }
  },

  async saveRegisteredPanel(registration: DeviceRegistration): Promise<void> {
    const registrations = await this.getRegisteredPanels();
    const next = registrations.filter(item => item.id !== registration.id);
    next.unshift(registration);
    await AsyncStorage.setItem(REGISTRATIONS_KEY, JSON.stringify(next));
  },
};

