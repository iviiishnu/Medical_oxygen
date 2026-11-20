import type { Alert, AlertAckReport, AlertDetails, Device, DeviceRegistration, Incident, IncidentChange, IncidentCreate, Point, UserProfile } from '../types/monitoring';

export interface DataSource {
  mode: 'postgres' | 'demo';
  signedIn(): boolean;
  userName(): string;
  getProfile(): UserProfile | null;
  signIn(email: string, password: string): Promise<void>;
  restoreSession(): Promise<boolean>;
  signOut(): Promise<void>;
  onDevices(cb: (d: Device[]) => void): () => void;
  onAlerts(cb: (a: Alert[]) => void): () => void;
  getAlertDetails(alertId: string): Promise<AlertDetails>;
  onHistory(deviceId: string, cb: (p: Point[]) => void, rangeHours?: number): () => void;
  onIncidents(cb: (incidents: Incident[]) => void): () => void;
  createIncident(input: IncidentCreate): Promise<void>;
  updateIncident(id: string, input: IncidentChange): Promise<void>;
  acknowledge(alertId: string, report: AlertAckReport): Promise<void>;
  registerDevice(registration: DeviceRegistration): Promise<void>;
}

