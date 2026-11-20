import { useEffect, useState, useCallback, useMemo } from 'react';
import type { Device, Alert, AlertAckReport } from '../types/monitoring';
import type { DataSource } from '../api/dataSource';
import { effectiveStatus, needsSound } from '../utils/logic';
import { SoundManager } from '../utils/sound';
import { StorageService } from '../utils/storage';

export function useMonitoring(source: DataSource) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [now, setNow] = useState<number>(Date.now());
  const [soundEnabled, setSoundEnabledState] = useState<boolean>(true);
  const [ackError, setAckError] = useState<string | null>(null);

  // 1-second tick for real-time offline calculation
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    void StorageService.getSettings().then(settings => {
      setSoundEnabledState(settings.soundEnabled);
      SoundManager.setEnabled(settings.soundEnabled);
    });
  }, []);

  const setSoundEnabled = useCallback((enabled: boolean) => {
    setSoundEnabledState(enabled);
    SoundManager.setEnabled(enabled);
    void StorageService.saveSettings({ soundEnabled: enabled });
  }, []);

  // Listen to devices and alerts
  useEffect(() => {
    if (!source.signedIn()) return;
    const unsubDevices = source.onDevices(setDevices);
    const unsubAlerts = source.onAlerts(setAlerts);
    return () => {
      unsubDevices();
      unsubAlerts();
    };
  }, [source]);

  // Offline detection: tablet offline triggers alarm sound
  const offlineDevices = useMemo(
    () => devices.filter(d => effectiveStatus(d, now) === 'TABLET_OFFLINE'),
    [devices, now]
  );

  const openAlerts = useMemo(() => alerts.filter(a => a.state === 'OPEN'), [alerts]);

  const isRinging = useMemo(
    () => (needsSound(alerts) || offlineDevices.length > 0) && soundEnabled,
    [alerts, offlineDevices, soundEnabled]
  );

  useEffect(() => {
    if (isRinging) {
      SoundManager.startAlarm(true);
    } else {
      SoundManager.stopAlarm();
    }
  }, [isRinging]);

  const acknowledgeAlert = useCallback(
    async (alertId: string, report: AlertAckReport) => {
      try {
        setAckError(null);
        await source.acknowledge(alertId, report);
        return true;
      } catch (err: any) {
        setAckError(err?.message || 'Failed to acknowledge alert');
        return false;
      }
    },
    [source]
  );

  return {
    devices,
    alerts,
    openAlerts,
    offlineDevices,
    now,
    isRinging,
    soundEnabled,
    setSoundEnabled,
    acknowledgeAlert,
    ackError,
  };
}

