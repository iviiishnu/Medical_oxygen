import { useEffect, useState, useMemo } from 'react';
import type { Point } from '../types/monitoring';
import type { DataSource } from '../api/dataSource';
import { decimate } from '../utils/logic';

const SPAN_24H_MS = 24 * 3600_000;

export function useDeviceHistory(source: DataSource, deviceId: string, nowMs: number) {
  const [history, setHistory] = useState<Point[]>([]);
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');

  useEffect(() => {
    if (!deviceId) return;
    const unsub = source.onHistory(deviceId, setHistory);
    return () => unsub();
  }, [source, deviceId]);

  const t0 = nowMs - SPAN_24H_MS;

  const filteredHistory = useMemo(
    () => history.filter(p => p.t >= t0),
    [history, t0]
  );

  const decimatedPoints = useMemo(
    () => decimate(filteredHistory, 400),
    [filteredHistory]
  );

  return {
    rawHistory: history,
    filteredHistory,
    decimatedPoints,
    viewMode,
    setViewMode,
  };
}

