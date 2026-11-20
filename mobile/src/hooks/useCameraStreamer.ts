declare const require: any;

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  cameraStreamingService,
} from '../services/cameraStreamingService';
import type { CameraStreamStatus } from '../types/monitoring';
import type { VisionReadResponse } from '../api/apiClient';

let useCameraDevicesHook: any = () => ({});
try {
  const vc = require('react-native-vision-camera');
  useCameraDevicesHook = vc.useCameraDevices;
} catch {
  // Expo Go fallback
}

export function useCameraStreamer() {
  const [hasPermission, setHasPermission] = useState<boolean>(true);
  const [facing, setFacing] = useState<'back' | 'front'>('back');
  const [status, setStatus] = useState<CameraStreamStatus>(() =>
    cameraStreamingService.getStatus()
  );
  const [lastAnalysis, setLastAnalysis] = useState<VisionReadResponse | null>(null);

  const cameraRef = useRef<any>(null);

  const devices = useCameraDevicesHook();
  const device = facing === 'back' ? devices?.back : devices?.front;

  useEffect(() => {
    try {
      cameraStreamingService.checkPermissions().then(setHasPermission).catch(() => setHasPermission(true));
    } catch {
      setHasPermission(true);
    }

    const unsubStatus = cameraStreamingService.subscribeStatus((newStatus: CameraStreamStatus) => {
      setStatus(newStatus);
    });

    const unsubFrames = cameraStreamingService.subscribeFrames((analysis: VisionReadResponse) => {
      setLastAnalysis(analysis);
    });

    return () => {
      unsubStatus();
      unsubFrames();
      cameraStreamingService.stopStreaming();
    };
  }, []);

  const toggleFacing = useCallback(() => {
    setFacing(prev => (prev === 'back' ? 'front' : 'back'));
  }, []);

  const startStreaming = useCallback(() => {
    if (cameraRef.current) {
      cameraStreamingService.startStreaming(cameraRef.current);
    }
  }, []);

  const stopStreaming = useCallback(() => {
    cameraStreamingService.stopStreaming();
  }, []);

  return {
    cameraRef,
    device,
    hasPermission,
    facing,
    toggleFacing,
    status,
    lastAnalysis,
    startStreaming,
    stopStreaming,
  };
}
