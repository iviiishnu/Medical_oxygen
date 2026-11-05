import type { Alert, Device, Point } from './logic.ts';

export interface DataSource {
  mode: 'firebase' | 'demo';
  signedIn(): boolean;
  userName(): string;
  signIn(email: string, password: string): Promise<void>;
  onDevices(cb: (d: Device[]) => void): () => void;
  onAlerts(cb: (a: Alert[]) => void): () => void;
  onHistory(deviceId: string, cb: (p: Point[]) => void): () => void;
  acknowledge(alertId: string): Promise<void>;
}

const env = import.meta.env;
export const hasFirebase = Boolean(env.VITE_FIREBASE_API_KEY && env.VITE_FIREBASE_PROJECT_ID);

export async function createSource(): Promise<DataSource> {
  if (hasFirebase) {
    const m = await import('./firebaseSource.ts');
    return m.firebaseSource({
      apiKey: env.VITE_FIREBASE_API_KEY, authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
      projectId: env.VITE_FIREBASE_PROJECT_ID, appId: env.VITE_FIREBASE_APP_ID,
    });
  }
  const m = await import('./demoSource.ts');
  return m.demoSource();
}
