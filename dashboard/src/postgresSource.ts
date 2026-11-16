import type { Alert, Device, Point } from './logic.ts';
import type { DataSource } from './source.ts';

const SESSION_KEY = 'o2-monitor-session';

export function postgresSource(backendUrl: string): DataSource {
  const baseUrl = backendUrl.trim().replace(/\/+$/, '');
  let user = '';
  let token = localStorage.getItem(SESSION_KEY) || '';

  async function request<T>(path: string, body?: unknown, allowSignedOut = false): Promise<T> {
    if (!token && !allowSignedOut) throw new Error('Sign in before connecting to the monitoring backend.');
    const response = await fetch(`${baseUrl}${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw Object.assign(new Error(data.error || `Monitoring backend returned HTTP ${response.status}`), {
        status: response.status,
      });
    }
    return data as T;
  }

  function poll<T>(path: string, cb: (value: T) => void): () => void {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = async () => {
      try { const result = await request<T>(path); if (active) cb(result); }
      catch (error) { if (active) console.warn(`PostgreSQL backend request failed (${path}):`, error); }
      finally { if (active) timer = setTimeout(refresh, 5000); }
    };
    void refresh();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }

  return {
    mode: 'postgres',
    signedIn: () => Boolean(token && user),
    userName: () => user,
    async restoreSession() {
      if (!token) return false;
      try { const me = await request<{ email: string }>('/api/v1/me'); user = me.email; return true; }
      catch (error) {
        user = '';
        const status = (error as Error & { status?: number }).status;
        if (status === 401 || status === 403) {
          token = '';
          localStorage.removeItem(SESSION_KEY);
        }
        return false;
      }
    },
    async signIn(email, password) {
      const result = await request<{ token: string; user: { email: string } }>(
        '/api/v1/auth/login', { email, password }, true,
      );
      token = result.token;
      user = result.user.email;
      localStorage.setItem(SESSION_KEY, token);
    },
    onDevices(cb) { return poll<Device[]>('/api/v1/devices', cb); },
    onAlerts(cb) { return poll<Alert[]>('/api/v1/alerts', cb); },
    onHistory(deviceId, cb) { return poll<Point[]>(`/api/v1/devices/${encodeURIComponent(deviceId)}/readings`, cb); },
    async acknowledge(alertId, report) {
      await request(`/api/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`, report);
    },
  };
}
