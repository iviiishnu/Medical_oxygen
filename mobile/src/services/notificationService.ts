import { Alert as RNAlert } from 'react-native';
import { defaultApiClient } from '../api/apiClient';
import { SoundManager } from '../utils/sound';

type AlertRow = { id: string; state: string; type: string; deviceId: string; value: number | null; unit: string };

class AlertPollingService {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private active = false;
  private knownIds = new Set<string>();

  initialize(): void {
    if (this.active) return;
    this.active = true;
    void this.poll(true);
  }

  stop(): void {
    this.active = false;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    SoundManager.stopAlarm();
  }

  private async poll(seed: boolean): Promise<void> {
    try {
      const alerts = await defaultApiClient.getApi<AlertRow[]>('/api/v1/alerts');
      const open = alerts.filter(alert => alert.state === 'OPEN');
      if (!seed) {
        const newest = open.find(alert => !this.knownIds.has(alert.id));
        if (newest) {
          SoundManager.startAlarm(true);
          RNAlert.alert(
            `Oxygen alert: ${newest.type}`,
            `${newest.deviceId}: ${newest.value ?? 'Check panel'} ${newest.unit ?? ''}`.trim(),
          );
        }
      }
      this.knownIds = new Set(alerts.map(alert => alert.id));
      if (!open.length) SoundManager.stopAlarm();
    } catch (error) {
      console.warn('Could not refresh PostgreSQL alerts:', error);
    } finally {
      if (this.active) this.timer = setTimeout(() => void this.poll(false), 5000);
    }
  }
}

export const notificationService = new AlertPollingService();
