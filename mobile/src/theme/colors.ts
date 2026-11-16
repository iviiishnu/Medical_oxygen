/**
 * Canonical color palette for the O2 Oxygen Monitor application.
 * Directly mirrored from dashboard/src/styles.css CSS custom properties.
 */

export const colors = {
  // Page & Surface canvas
  page: '#f9f9f7',
  surface: '#fcfcfb',

  // Typography
  ink: '#0b0b0b', // Primary text & solid dark buttons
  ink2: '#52514e', // Secondary text, subheadings, labels
  muted: '#898781', // Tick marks, stale readings, placeholders

  // Borders & Grid lines
  grid: '#e1e0d9', // Dividers, card borders, chart gridlines
  axis: '#c3c2b7', // Chart baseline and crosshair lines
  border: 'rgba(11, 11, 11, 0.10)',
  borderLight: '#f0efec',

  // Primary Clinical Accent
  series: '#2a78d6', // Chart telemetry polyline, links, active indicators
  seriesLight: '#eaf1f9', // Active item background pill

  // Clinical Status Badges & Edge Accents
  good: '#0ca30c', // OK
  warning: '#fab219', // LOW, TREND_FALLING
  serious: '#ec835a', // UNCERTAIN, DEMO
  critical: '#d03b3b', // CRITICAL alerts
  lost: '#6250d6', // MONITORING_LOST, TABLET_OFFLINE

  // Alert & Banner accents
  criticalLight: '#fae8e3',
  criticalBorder: '#edc8c2',

  // Status Edge Mapping (mirrors .st-*-edge from dashboard)
  statusEdges: {
    OK: '#0ca30c',
    LOW: '#fab219',
    CRITICAL: '#d03b3b',
    UNCERTAIN: '#ec835a',
    MONITORING_LOST: '#6250d6',
    TABLET_OFFLINE: '#6250d6',
    TREND_FALLING: '#fab219',
    UNKNOWN: '#898781',
  },

  // Dark Theme Palette (for prefers-color-scheme: dark / data-theme="dark")
  dark: {
    page: '#0d0d0d',
    surface: '#1a1a19',
    ink: '#f0efec',
    ink2: '#c3c2b7',
    muted: '#898781',
    grid: '#2c2c2a',
    axis: '#383835',
    border: 'rgba(255, 255, 255, 0.10)',
    series: '#3987e5',
    good: '#20b620',
    warning: '#fab219',
    critical: '#d03b3b',
    lost: '#9085e9',
    seriesLight: '#1d2b3d',
    borderLight: '#242423',
    criticalLight: '#392320',
    criticalBorder: '#60352f',
    serious: '#ec835a',
    statusEdges: {
      OK: '#20b620', LOW: '#fab219', CRITICAL: '#e35b5b', UNCERTAIN: '#ec835a',
      MONITORING_LOST: '#9085e9', TABLET_OFFLINE: '#9085e9', TREND_FALLING: '#fab219', UNKNOWN: '#898781',
    },
  },
} as const;

export interface ThemePalette {
  page: string; surface: string; ink: string; ink2: string; muted: string;
  grid: string; axis: string; border: string; borderLight: string;
  series: string; seriesLight: string; good: string; warning: string;
  serious: string; critical: string; lost: string; criticalLight: string;
  criticalBorder: string; statusEdges: Record<string, string>;
}
export type ThemeColors = typeof colors;

