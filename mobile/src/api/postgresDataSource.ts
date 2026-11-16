import type { Alert, AlertAckReport, Device, DeviceRegistration, Point } from '../types/monitoring';
import type { DataSource } from './dataSource';
import { StorageService } from '../utils/storage';
import { defaultApiClient } from './apiClient';

function poll<T>(path: string, cb: (items: T[]) => void): () => void {
  let active = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const refresh = async () => {
    try {
      const items = await defaultApiClient.getApi<T[]>(path);
      if (active) cb(items);
    } catch (error) {
      if (active) console.warn(`PostgreSQL backend request failed (${path}):`, error);
    } finally {
      if (active) timer = setTimeout(refresh, 5000);
    }
  };
  void refresh();
  return () => { active = false; if (timer) clearTimeout(timer); };
}

export function createPostgresDataSource(): DataSource {
  let currentUser = '';

  return {
    mode: 'postgres',
    signedIn: () => currentUser !== '',
    userName: () => currentUser,

    async restoreSession(): Promise<boolean> {
      if (!await StorageService.getAuthToken()) return false;
      try {
        const user = await defaultApiClient.getApi<{ email: string }>('/api/v1/me');
        currentUser = user.email;
        return true;
      } catch (error: any) {
        currentUser = '';
        if (error?.response?.status === 401 || error?.response?.status === 403) {
          await StorageService.clearAuth();
        }
        return false;
      }
    },

    async signIn(email: string, password: string): Promise<void> {
      const result = await defaultApiClient.postApi<{ token: string; user: { email: string } }>(
        '/api/v1/auth/login', { email, password },
      );
      await StorageService.saveAuthToken(result.token);
      currentUser = result.user.email;
    },

    async signOut(): Promise<void> {
      currentUser = '';
      await StorageService.clearAuth();
    },

    onDevices(cb: (devices: Device[]) => void): () => void {
      return poll<Device>('/api/v1/devices', cb);
    },

    onAlerts(cb: (alerts: Alert[]) => void): () => void {
      return poll<Alert>('/api/v1/alerts', cb);
    },

    onHistory(deviceId: string, cb: (points: Point[]) => void): () => void {
      return poll<Point>(`/api/v1/devices/${encodeURIComponent(deviceId)}/readings`, cb);
    },

    async acknowledge(alertId: string, report: AlertAckReport): Promise<void> {
      await defaultApiClient.postApi(`/api/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`, report);
    },

    async registerDevice(registration: DeviceRegistration): Promise<void> {
      await defaultApiClient.postApi('/api/v1/devices', registration);
    },
  };
}
