/**
 * Core monitoring types and interfaces for the mobile application.
 * Corresponds to existing dashboard data models and contracts.
 */

export type Status =
  | 'OK'
  | 'LOW'
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

export interface AlertAckReport {
  reason: string;
  resolution: string;
  notes?: string;
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
  role: 'staff' | 'admin' | 'device';
  onDuty: boolean;
}

