import type { Alert, AlertAckReport, AlertDetails, Device, DeviceRegistration, Incident, IncidentChange, IncidentCreate, Point, UserProfile } from '../types/monitoring';
import type { DataSource } from './dataSource';
import { StorageService } from '../utils/storage';
import { defaultApiClient } from './apiClient';

function poll<T>(path: string, cb: (items: T[]) => void, intervalMs = 5000): () => void {
  let active = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const refresh = async () => {
    try {
      const items = await defaultApiClient.getApi<T[]>(path);
      if (active) cb(items);
    } catch (error) {
      if (active) console.warn(`PostgreSQL backend request failed (${path}):`, error);
    } finally {
      if (active) timer = setTimeout(refresh, intervalMs);
    }
  };
  void refresh();
  return () => { active = false; if (timer) clearTimeout(timer); };
}

export function createPostgresDataSource(): DataSource {
  let currentUser = '';
  let profile: UserProfile | null = null;

  return {
    mode: 'postgres',
    signedIn: () => currentUser !== '',
    userName: () => currentUser,
    getProfile: () => profile,

    async restoreSession(): Promise<boolean> {
      if (!await StorageService.getAuthToken()) return false;
      try {
        const user = await defaultApiClient.getApi<{ uid: string; email: string; displayName: string; role: 'staff' | 'admin'; onDuty: boolean }>('/api/v1/me');
        profile = { uid: user.uid, email: user.email, displayName: user.displayName || user.email, role: user.role, onDuty: user.onDuty };
        currentUser = profile.displayName;
        return true;
      } catch (error: any) {
        currentUser = '';
        profile = null;
        if (error?.response?.status === 401 || error?.response?.status === 403) {
          await StorageService.clearAuth();
        }
        return false;
      }
    },

    async signIn(email: string, password: string): Promise<void> {
      const result = await defaultApiClient.postApi<{ token: string; user: { uid: string; email: string; displayName: string; role: 'staff' | 'admin'; onDuty: boolean } }>(
        '/api/v1/auth/login', { email, password },
      );
      await StorageService.saveAuthToken(result.token);
      profile = { ...result.user, displayName: result.user.displayName || result.user.email };
      currentUser = profile.displayName;
    },

    async signOut(): Promise<void> {
      currentUser = '';
      profile = null;
      await StorageService.clearAuth();
    },

    onDevices(cb: (devices: Device[]) => void): () => void {
      return poll<Device>('/api/v1/devices', cb);
    },

    onAlerts(cb: (alerts: Alert[]) => void): () => void {
      return poll<Alert>('/api/v1/alerts', cb);
    },

    async getAlertDetails(alertId: string): Promise<AlertDetails> {
      return defaultApiClient.getApi<AlertDetails>(`/api/v1/alerts/${encodeURIComponent(alertId)}`);
    },

    onHistory(deviceId: string, cb: (points: Point[]) => void, rangeHours = 24): () => void {
      return poll<Point>(`/api/v1/devices/${encodeURIComponent(deviceId)}/readings?hours=${Math.max(1, Math.min(720, Math.round(rangeHours)))}`, cb, rangeHours > 24 ? 60_000 : 10_000);
    },

    onIncidents(cb: (items: Incident[]) => void): () => void {
      return poll<Incident>('/api/v1/incidents', cb);
    },

    async createIncident(input: IncidentCreate): Promise<void> {
      await defaultApiClient.postApi('/api/v1/incidents', input);
    },

    async updateIncident(id: string, input: IncidentChange): Promise<void> {
      await defaultApiClient.postApi(`/api/v1/incidents/${encodeURIComponent(id)}/updates`, input);
    },

    async acknowledge(alertId: string, report: AlertAckReport): Promise<void> {
      await defaultApiClient.postApi(`/api/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`, report);
    },

    async registerDevice(registration: DeviceRegistration): Promise<void> {
      await defaultApiClient.postApi('/api/v1/devices', registration);
    },
  };
}
