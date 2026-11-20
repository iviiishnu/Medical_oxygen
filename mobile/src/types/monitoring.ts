/**
 * Core monitoring types and interfaces for the mobile application.
 * Corresponds to existing dashboard data models and contracts.
 */

export type Status =
  | 'OK'
  | 'LOW'
  | 'HIGH'
  | 'CRITICAL'
  | 'UNCERTAIN'
  | 'MONITORING_LOST'
  | 'TABLET_OFFLINE'
  | 'UNKNOWN';

export interface Device {
  id: string;
  name: string;
  value: number | null;
  unit: string;
  status: string;
  alarm: string;
  trendFalling: boolean;
  lastHeartbeatMs: number | null;
  online: boolean;
  battery: number | null;
  lowThreshold: number;
  criticalThreshold: number;
  highThreshold?: number | null;
  gauges?: RegisteredGauge[];
}

export interface Alert {
  id: string;
  type: string;
  state: 'OPEN' | 'ACKED' | 'RESOLVED' | string;
  deviceId: string;
  value: number | null;
  unit: string;
  createdMs: number | null;
  ackedBy: string | null;
  ackedMs: number | null;
  resolvedMs: number | null;
  escalationLevel: number;
  ackReason?: string | null;
  ackResolution?: string | null;
  ackNotes?: string | null;
}

export interface AlertDetails extends Alert {
  deviceName: string;
  reason: string | null;
  evidenceImage: string | null;
  lowThreshold: number | null;
  criticalThreshold: number | null;
  highThreshold: number | null;
  recentReadings: Point[];
}

export interface AlertAckReport {
  reason: string;
  resolution: string;
  notes?: string;
}

export type IncidentStatus = 'OPEN' | 'IN_PROGRESS' | 'CLOSED';

export interface IncidentUpdate {
  id: string;
  note: string;
  actionTaken: string | null;
  status: IncidentStatus | null;
  author: string;
  createdMs: number;
}

export interface Incident {
  id: string;
  title: string;
  deviceId: string | null;
  alertId: string | null;
  description: string;
  possibleCause: string | null;
  actionTaken: string | null;
  assignedTo: string | null;
  status: IncidentStatus;
  createdBy: string;
  createdMs: number;
  updatedMs: number;
  updates: IncidentUpdate[];
}

export interface IncidentCreate {
  title: string;
  deviceId?: string;
  alertId?: string;
  description: string;
  possibleCause?: string;
  actionTaken?: string;
  assignedTo?: string;
}

export interface IncidentChange {
  status?: IncidentStatus;
  note: string;
  actionTaken?: string;
}

export interface RegisteredGauge {
  number: number;
  name: string;
  unit: string;
  kind: string;
  scale: number;
  reading: number | null;
  confidencePct: number;
  lowThreshold?: number;
  criticalThreshold?: number;
  highThreshold?: number;
  ignored?: boolean;
}

export interface DeviceRegistration {
  id: string;
  name: string;
  createdBy: string;
  gauges: RegisteredGauge[];
  registrationImage: string;
}

export interface Point {
  t: number;
  v: number | null;
  status: string;
}

export interface CameraStreamConfig {
  backendUrl: string;
  fps: number;
  quality: number;
  facing: 'back' | 'front';
  maxScaleValue?: number;
}

export interface CameraStreamStatus {
  isStreaming: boolean;
  fps: number;
  latencyMs: number;
  reconnectAttempts: number;
  lastError: string | null;
  isConnected: boolean;
}

export interface UserProfile {
  uid: string;
  email: string;
  displayName: string;
  role: 'staff' | 'admin' | 'device';
  onDuty: boolean;
}

