import type { Alert, Device, Point } from './logic.ts';

export interface DataSource {
  mode: 'postgres' | 'demo';
  signedIn(): boolean;
  userName(): string;
  signIn(email: string, password: string): Promise<void>;
  restoreSession(): Promise<boolean>;
  onDevices(cb: (d: Device[]) => void): () => void;
  onAlerts(cb: (a: Alert[]) => void): () => void;
  onHistory(deviceId: string, cb: (p: Point[]) => void): () => void;
  acknowledge(alertId: string, report: { reason: string; resolution: string; notes?: string }): Promise<void>;
}

const env = import.meta.env;

export async function createSource(): Promise<DataSource> {
  if (env.VITE_DEMO_MODE === 'true') {
    const m = await import('./demoSource.ts');
    const source = m.demoSource();
    return source;
  }
  const m = await import('./postgresSource.ts');
  const source = m.postgresSource(env.VITE_BACKEND_URL || 'http://localhost:8765');
  await source.restoreSession();
  return source;
}
