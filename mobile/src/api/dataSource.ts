import type { Alert, AlertAckReport, Device, DeviceRegistration, Point } from '../types/monitoring';

export interface DataSource {
  mode: 'postgres' | 'demo';
  signedIn(): boolean;
  userName(): string;
  signIn(email: string, password: string): Promise<void>;
  restoreSession(): Promise<boolean>;
  signOut(): Promise<void>;
  onDevices(cb: (d: Device[]) => void): () => void;
  onAlerts(cb: (a: Alert[]) => void): () => void;
  onHistory(deviceId: string, cb: (p: Point[]) => void): () => void;
  acknowledge(alertId: string, report: AlertAckReport): Promise<void>;
  registerDevice(registration: DeviceRegistration): Promise<void>;
}

