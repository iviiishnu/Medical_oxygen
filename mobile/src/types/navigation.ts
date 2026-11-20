/**
 * Navigation type definitions for Mobile and Tablet navigation hierarchies.
 */

export type MobileTabParamList = {
  HomeTab: undefined;
  DevicesTab: undefined;
  AnalyticsTab: undefined;
  AlertsTab: undefined;
  MoreTab: undefined;
};

export type MobileStackParamList = {
  Login: undefined;
  MainTabs: undefined;
  DeviceDetail: { deviceId: string; deviceName: string };
  CameraStream: undefined;
  AlertDetail: { alertId: string };
};

export type TabletDrawerParamList = {
  Console: { deviceId?: string } | undefined;
  Alerts: undefined;
  History: undefined;
  Incidents: { alertId?: string } | undefined;
  Camera: undefined;
  Settings: { focusRegistration?: boolean } | undefined;
};

