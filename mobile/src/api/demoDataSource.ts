/**
 * DEMO mode: simulated oxygen supply devices and pressure trends. This is not live sensor data.
 * Provides multiple sample devices and realtime demo readings.
 * STRICT: Zero occurrences of the excluded terminology.
 */

import type { Alert, AlertAckReport, AlertDetails, Device, DeviceRegistration, Incident, IncidentChange, IncidentCreate, Point } from '../types/monitoring';
import type { DataSource } from './dataSource';
import { StorageService } from '../utils/storage';

export function createDemoDataSource(): DataSource {
  const t0 = Date.now();
  const user = 'Dr. Sharma';
  let isSignedIn = true;

  // Generate a 24-hour sample history for the demo-only panels.
  const deviceHistories: Record<string, Point[]> = {
    D001: [],
    D002: [],
    D003: [],
    D004: [],
  };

  // Populate 24 hours of points (every 2 minutes)
  for (let t = t0 - 24 * 3600_000; t <= t0; t += 120_000) {
    const minFromNow = (t0 - t) / 60_000;

    const v1 = 4.5 + Math.sin(t / 180000) * 0.25 + Math.cos(t / 600000) * 0.12;
    deviceHistories.D001.push({
      t,
      v: Math.round((minFromNow < 3 ? 2.8 : v1) * 100) / 100,
      status: minFromNow < 3 ? 'CRITICAL' : 'OK',
    });

    let v2 = 4.6 + Math.sin(t / 240000) * 0.18;
    if (minFromNow >= 2.5 && minFromNow <= 4.5) {
      v2 = 2.8 + Math.sin(minFromNow * 2) * 0.15;
    } else if (minFromNow < 2.5) {
      v2 = 4.6;
    }
    deviceHistories.D002.push({
      t,
      v: Math.round(v2 * 100) / 100,
      status: v2 < 3.5 ? 'LOW' : 'OK',
    });

    const v3 = 3.4 + Math.sin(t / 300000) * 0.08;
    deviceHistories.D003.push({
      t,
      v: Math.round(v3 * 100) / 100,
      status: 'LOW',
    });

    let v4 = 4.4 + Math.cos(t / 200000) * 0.18;
    if (minFromNow < 5) {
      v4 = 4.5 + (5 - minFromNow) * 0.25;
    }
    deviceHistories.D004.push({
      t,
      v: Math.round((minFromNow < 2 ? 5.8 : v4) * 100) / 100,
      status: minFromNow < 2 ? 'HIGH' : 'OK',
    });
  }

  const initialAlerts: Alert[] = [
    {
      id: 'alert-001',
      type: 'CRITICAL',
      state: 'OPEN',
      deviceId: 'D001',
      value: 2.8,
      unit: 'kg/cm2',
      createdMs: t0 - 2 * 60_000,
      ackedBy: null,
      ackedMs: null,
      resolvedMs: null,
      escalationLevel: 1,
    },
    {
      id: 'alert-004',
      type: 'HIGH',
      state: 'OPEN',
      deviceId: 'D004',
      value: 5.8,
      unit: 'kg/cm2',
      createdMs: t0 - 3 * 60_000,
      ackedBy: null,
      ackedMs: null,
      resolvedMs: null,
      escalationLevel: 1,
    },
    {
      id: 'alert-002',
      type: 'Normal',
      state: 'RESOLVED',
      deviceId: 'D002',
      value: 4.6,
      unit: 'kg/cm2',
      createdMs: t0 - 45 * 60_000,
      ackedBy: 'Dr. Sharma',
      ackedMs: t0 - 40 * 60_000,
      resolvedMs: t0 - 20 * 60_000,
      escalationLevel: 0,
    },
    {
      id: 'alert-003',
      type: 'Normal',
      state: 'RESOLVED',
      deviceId: 'D003',
      value: 3.4,
      unit: 'kg/cm2',
      createdMs: t0 - 120 * 60_000,
      ackedBy: 'Dr. Sharma',
      ackedMs: t0 - 110 * 60_000,
      resolvedMs: t0 - 60 * 60_000,
      escalationLevel: 0,
    },
  ];

  const alerts: Alert[] = [...initialAlerts];
  const incidents: Incident[] = [];
  const subsA = new Set<(a: Alert[]) => void>();
  const subsD = new Set<(d: Device[]) => void>();
  const subsH = new Map<string, Set<(p: Point[]) => void>>();
  const subsI = new Set<(items: Incident[]) => void>();
  let intervalId: ReturnType<typeof setInterval> | null = null;

  function getDevices(now: number): Device[] {
    return [
      {
        id: 'D001',
        name: 'D001',
        value: 2.8,
        unit: 'kg/cm2',
        status: 'CRITICAL',
        alarm: 'CRITICAL',
        trendFalling: false,
        lastHeartbeatMs: now - 3000,
        online: true,
        battery: 98,
        lowThreshold: 3.5,
        criticalThreshold: 3.0,
      },
      {
        id: 'D002',
        name: 'D002',
        value: 4.6,
        unit: 'kg/cm2',
        status: 'OK',
        alarm: 'OK',
        trendFalling: false,
        lastHeartbeatMs: now - 95000,
        online: true,
        battery: 92,
        lowThreshold: 3.5,
        criticalThreshold: 3.0,
      },
      {
        id: 'D003',
        name: 'D003',
        value: 3.4,
        unit: 'kg/cm2',
        status: 'LOW',
        alarm: 'LOW',
        trendFalling: false,
        lastHeartbeatMs: now - 450000,
        online: false,
        battery: 45,
        lowThreshold: 3.5,
        criticalThreshold: 3.0,
      },
      {
        id: 'D004',
        name: 'D004',
        value: 5.8,
        unit: 'kg/cm2',
        status: 'HIGH',
        alarm: 'HIGH',
        trendFalling: false,
        lastHeartbeatMs: now - 5000,
        online: true,
        battery: 88,
        lowThreshold: 3.5,
        criticalThreshold: 3.0,
        highThreshold: 5.5,
      },
    ];
  }

  function step() {
    const now = Date.now();
    const currentDevices = getDevices(now);

    // Notify device subscribers
    subsD.forEach(cb => cb(currentDevices));
    subsA.forEach(cb => cb([...alerts]));
    subsI.forEach(cb => cb([...incidents]));

    // Notify history subscribers
    subsH.forEach((set, devId) => {
      const hist = deviceHistories[devId] || deviceHistories.D001;
      set.forEach(cb => cb([...hist]));
    });
  }

  function stopIfUnused() {
    if (subsA.size || subsD.size || subsH.size || subsI.size || intervalId == null) return;
    clearInterval(intervalId);
    intervalId = null;
  }

  return {
    mode: 'demo',
    signedIn: () => isSignedIn,
    userName: () => (isSignedIn ? user : ''),
    getProfile: () => isSignedIn ? { uid: 'demo-staff', email: 'demo@hospital.org', displayName: user, role: 'staff', onDuty: true } : null,
    async signIn() {
      isSignedIn = true;
    },
    async restoreSession() {
      return isSignedIn;
    },
    async signOut() {
      isSignedIn = false;
    },
    onDevices(cb) {
      subsD.add(cb);
      if (intervalId == null) intervalId = setInterval(step, 2000);
      cb(getDevices(Date.now()));
      return () => {
        subsD.delete(cb);
        stopIfUnused();
      };
    },
    onAlerts(cb) {
      subsA.add(cb);
      if (intervalId == null) intervalId = setInterval(step, 2000);
      cb([...alerts]);
      return () => {
        subsA.delete(cb);
        stopIfUnused();
      };
    },
    async getAlertDetails(alertId: string): Promise<AlertDetails> {
      const alert = alerts.find(item => item.id === alertId);
      if (!alert) throw new Error('Alert not found.');
      const device = getDevices(Date.now()).find(item => item.id === alert.deviceId);
      return { ...alert, deviceName: device?.name ?? alert.deviceId, reason: 'Demonstration alert', evidenceImage: null,
        lowThreshold: device?.lowThreshold ?? null, criticalThreshold: device?.criticalThreshold ?? null,
        highThreshold: device?.highThreshold ?? null, recentReadings: deviceHistories[alert.deviceId] ?? [] };
    },
    onHistory(deviceId, cb, rangeHours = 24) {
      const devId = deviceId || 'D001';
      if (!subsH.has(devId)) {
        subsH.set(devId, new Set());
      }
      subsH.get(devId)!.add(cb);
      const hist = deviceHistories[devId] || deviceHistories.D001;
      cb(hist.filter(point => point.t >= Date.now() - rangeHours * 3600_000));
      return () => {
        const set = subsH.get(devId);
        if (set) {
          set.delete(cb);
          if (set.size === 0) subsH.delete(devId);
        }
        stopIfUnused();
      };
    },
    onIncidents(cb) {
      subsI.add(cb);
      cb([...incidents]);
      if (intervalId == null) intervalId = setInterval(step, 2000);
      return () => { subsI.delete(cb); stopIfUnused(); };
    },
    async createIncident(input: IncidentCreate) {
      const now = Date.now();
      incidents.unshift({
        id: `demo-incident-${now}`, title: input.title.trim(), deviceId: input.deviceId || null,
        alertId: input.alertId || null, description: input.description.trim(),
        possibleCause: input.possibleCause?.trim() || null, actionTaken: input.actionTaken?.trim() || null,
        assignedTo: input.assignedTo?.trim() || null, status: 'OPEN', createdBy: user,
        createdMs: now, updatedMs: now, updates: [],
      });
      subsI.forEach(cb => cb([...incidents]));
    },
    async updateIncident(id: string, input: IncidentChange) {
      const item = incidents.find(i => i.id === id);
      if (!item) throw new Error('Incident not found.');
      const now = Date.now();
      item.status = input.status ?? item.status;
      if (input.actionTaken?.trim()) item.actionTaken = input.actionTaken.trim();
      item.updatedMs = now;
      item.updates.push({ id: `demo-update-${now}`, note: input.note.trim(), actionTaken: input.actionTaken?.trim() || null, status: input.status ?? null, author: user, createdMs: now });
      subsI.forEach(cb => cb([...incidents]));
    },
    async acknowledge(alertId: string, report: AlertAckReport) {
      const a = alerts.find(x => x.id === alertId);
      if (a && a.state === 'OPEN') {
        a.state = 'ACKED';
        a.ackedBy = user;
        a.ackedMs = Date.now();
      }
      subsA.forEach(cb => cb([...alerts]));
    },
    async registerDevice(registration: DeviceRegistration) {
      await StorageService.saveRegisteredPanel(registration);
    },
  };
}
