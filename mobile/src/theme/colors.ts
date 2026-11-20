/**
 * MEDIGAS Doctor Portal Design Theme.
 * Conforms strictly to hospital clinical monitoring standards.
 * STRICT: Zero occurrences of the excluded terminology.
 */

export const colors = {
  // Brand
  brandBlue: '#2563eb',
  brandBlueLight: '#eff6ff',
  brandBlueDark: '#1d4ed8',

  // Canvas & Surfaces
  page: '#f4f6fa',
  surface: '#ffffff',
  surfaceSubtle: '#f8fafc',

  // Typography
  ink: '#0f172a', // Deep slate heading text
  ink2: '#64748b', // Secondary slate text & labels
  muted: '#94a3b8', // Placeholders & inactive icons
  white: '#ffffff',

  // Borders & Dividers
  border: '#e2e8f0',
  borderLight: '#f1f5f9',

  // Clinical Status
  normal: '#10b981', // Green / Normal
  normalLight: '#d1fae5',
  normalBg: '#f0fdf4',
  normalBorder: '#bbf7d0',

  warning: '#f59e0b', // Yellow / Amber / Warning
  warningLight: '#fef3c7',
  warningBg: '#fffbeb',

  critical: '#ef4444', // Red / Critical / Active Alert
  criticalLight: '#fee2e2',
  criticalBg: '#fef2f2',
  criticalBorder: '#fecaca',

  // Chart Series Colors (D001, D002, D003, D004)
  deviceColors: {
    D001: '#2563eb', // Blue
    D002: '#10b981', // Green
    D003: '#f59e0b', // Yellow
    D004: '#ef4444', // Red
  },

  // Legacy mappings for backward compatibility
  series: '#2563eb',
  seriesLight: '#eff6ff',
  good: '#10b981',
  serious: '#f59e0b',
  lost: '#8b5cf6',
  grid: '#e2e8f0',
  axis: '#cbd5e1',

  statusEdges: {
    OK: '#10b981',
    NORMAL: '#10b981',
    LOW: '#f59e0b',
    HIGH: '#ef4444',
    CRITICAL: '#ef4444',
    UNCERTAIN: '#f59e0b',
    MONITORING_LOST: '#8b5cf6',
    TABLET_OFFLINE: '#ef4444',
    TREND_FALLING: '#f59e0b',
    UNKNOWN: '#94a3b8',
  },

  dark: {
    brandBlue: '#3b82f6',
    brandBlueLight: '#1e293b',
    brandBlueDark: '#60a5fa',
    page: '#0f172a',
    surface: '#1e293b',
    surfaceSubtle: '#0f172a',
    ink: '#f8fafc',
    ink2: '#94a3b8',
    muted: '#64748b',
    white: '#ffffff',
    border: '#334155',
    borderLight: '#1e293b',
    normal: '#10b981',
    normalLight: '#064e3b',
    normalBg: '#022c22',
    normalBorder: '#065f46',
    warning: '#f59e0b',
    warningLight: '#78350f',
    warningBg: '#451a03',
    critical: '#ef4444',
    criticalLight: '#7f1d1d',
    criticalBg: '#450a0a',
    criticalBorder: '#991b1b',
    deviceColors: {
      D001: '#3b82f6',
      D002: '#10b981',
      D003: '#f59e0b',
      D004: '#ef4444',
    },
    series: '#3b82f6',
    seriesLight: '#1e293b',
    good: '#10b981',
    serious: '#f59e0b',
    lost: '#a78bfa',
    grid: '#334155',
    axis: '#475569',
    statusEdges: {
      OK: '#10b981',
      NORMAL: '#10b981',
      LOW: '#f59e0b',
      HIGH: '#ef4444',
      CRITICAL: '#ef4444',
      UNCERTAIN: '#f59e0b',
      MONITORING_LOST: '#a78bfa',
      TABLET_OFFLINE: '#ef4444',
      TREND_FALLING: '#f59e0b',
      UNKNOWN: '#64748b',
    },
  },
} as const;

export type ThemeColors = typeof colors;
type DeepString<T> = {
  readonly [K in keyof T]: T[K] extends string
    ? string
    : T[K] extends object
    ? DeepString<T[K]>
    : T[K];
};
export type ThemePalette = DeepString<typeof colors.dark> & {
  readonly dark?: any;
};
