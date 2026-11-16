/**
 * Navigation type definitions for Mobile and Tablet navigation hierarchies.
 */

export type MobileTabParamList = {
  MonitorTab: undefined;
  AlertsTab: undefined;
  CameraTab: undefined;
  SettingsTab: { focusRegistration?: boolean } | undefined;
};

export type MobileStackParamList = {
  Login: undefined;
  MainTabs: undefined;
  DeviceDetail: { deviceId: string; deviceName: string };
  CameraStream: undefined;
  AlertDetail: { alertId: string };
};

export type TabletDrawerParamList = {
  Console: undefined;
  Devices: undefined;
  DeviceDetail: { deviceId: string };
  Alerts: undefined;
  Camera: undefined;
  Settings: { focusRegistration?: boolean } | undefined;
};

