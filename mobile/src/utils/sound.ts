import { Vibration, Platform } from 'react-native';

/**
 * Mobile Sound and Alarm Manager.
 * Coordinates audio playback and rhythmic pattern vibration for high-severity alerts.
 */

let isAlarmActive = false;
let alarmEnabled = true;
let vibrationTimer: ReturnType<typeof setInterval> | null = null;

// Pattern: 500ms vibrate, 300ms pause, 500ms vibrate, 700ms pause
const ALARM_VIBRATION_PATTERN = [500, 300, 500, 700];

export const SoundManager = {
  setEnabled(enabled: boolean): void {
    alarmEnabled = enabled;
    if (!enabled) this.stopAlarm();
  },

  isAlarming(): boolean {
    return isAlarmActive;
  },

  startAlarm(enabled: boolean = true): void {
    if (isAlarmActive || !enabled || !alarmEnabled) return;
    isAlarmActive = true;

    if (Platform.OS === 'android') {
      Vibration.vibrate(ALARM_VIBRATION_PATTERN, true);
    } else {
      // iOS repeats manually via interval
      Vibration.vibrate();
      vibrationTimer = setInterval(() => {
        if (isAlarmActive) {
          Vibration.vibrate();
        }
      }, 1500);
    }
  },

  stopAlarm(): void {
    if (!isAlarmActive) return;
    isAlarmActive = false;
    Vibration.cancel();
    if (vibrationTimer) {
      clearInterval(vibrationTimer);
      vibrationTimer = null;
    }
  },
};

