import React from 'react';
import { MobileCameraScreen } from '../screens/mobile/MobileCameraScreen';
import type { DataSource } from '../api/dataSource';

/** The tablet console uses the same Expo Go compatible camera and reader as the Camera tab. */
export const CameraPreviewWidget: React.FC<{ source: DataSource; onRegisterDevice: () => void; height?: number; expanded?: boolean }> = ({ source, onRegisterDevice }) => (
  <MobileCameraScreen source={source} onRegisterDevice={onRegisterDevice} />
);
