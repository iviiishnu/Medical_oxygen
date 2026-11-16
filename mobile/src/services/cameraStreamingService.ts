import { ApiClient, defaultApiClient, VisionReadResponse } from '../api/apiClient';
import { CameraStreamConfig, CameraStreamStatus } from '../types/monitoring';

let CameraModule: any = null;
let RTCPeerConnectionModule: any = null;

try {
  CameraModule = require('react-native-vision-camera').Camera;
  const webrtc = require('react-native-webrtc');
  RTCPeerConnectionModule = webrtc.RTCPeerConnection;
} catch {
  // Expo Go or non-native environment
}

export type StreamStatusCallback = (status: CameraStreamStatus) => void;
export type FrameAnalysisCallback = (analysis: VisionReadResponse) => void;

export class CameraStreamingService {
  private config: CameraStreamConfig = {
    backendUrl: 'http://192.168.1.7:8000',
    fps: 1,
    quality: 0.85,
    facing: 'back',
  };

  private status: CameraStreamStatus = {
    isStreaming: false,
    fps: 0,
    latencyMs: 0,
    reconnectAttempts: 0,
    lastError: null,
    isConnected: false,
  };

  private intervalTimer: ReturnType<typeof setTimeout> | null = null;
  private statusListeners: Set<StreamStatusCallback> = new Set();
  private frameListeners: Set<FrameAnalysisCallback> = new Set();
  private peerConnection: any = null;
  private apiClient: ApiClient = defaultApiClient;

  constructor(customConfig?: Partial<CameraStreamConfig>) {
    if (customConfig) {
      this.config = { ...this.config, ...customConfig };
      this.apiClient.setBaseUrl(this.config.backendUrl);
    }
  }

  public async checkPermissions(): Promise<boolean> {
    if (!CameraModule) return true;
    try {
      const status = await CameraModule.getCameraPermissionStatus();
      if (status === 'granted') return true;
      const req = await CameraModule.requestCameraPermission();
      return req === 'granted';
    } catch {
      return true;
    }
  }

  public updateConfig(newConfig: Partial<CameraStreamConfig>) {
    this.config = { ...this.config, ...newConfig };
    if (newConfig.backendUrl) {
      this.apiClient.setBaseUrl(newConfig.backendUrl);
    }
  }

  public getStatus(): CameraStreamStatus {
    return { ...this.status };
  }

  public subscribeStatus(cb: StreamStatusCallback): () => void {
    this.statusListeners.add(cb);
    cb(this.getStatus());
    return () => this.statusListeners.delete(cb);
  }

  public subscribeFrames(cb: FrameAnalysisCallback): () => void {
    this.frameListeners.add(cb);
    return () => this.frameListeners.delete(cb);
  }

  private emitStatus() {
    const s = this.getStatus();
    this.statusListeners.forEach(cb => cb(s));
  }

  public startStreaming(cameraRef: any) {
    if (this.status.isStreaming) return;
    this.status.isStreaming = true;
    this.status.reconnectAttempts = 0;
    this.status.lastError = null;
    this.status.isConnected = true;
    this.emitStatus();

    const intervalMs = Math.round(1000 / (this.config.fps || 1));

    const loop = async () => {
      if (!this.status.isStreaming) return;

      const t0 = Date.now();
      try {
        if (cameraRef && typeof cameraRef.takePhoto === 'function') {
          const photo = await cameraRef.takePhoto({
            qualityPrioritization: 'speed',
            flash: 'off',
            enableShutterSound: false,
          });

          const filePayload = {
            uri: `file://${photo.path}`,
            type: 'image/jpeg',
            name: 'frame.jpg',
          };

          const result = await this.apiClient.uploadFrame(filePayload, this.config.maxScaleValue);
          const elapsed = Date.now() - t0;

          this.status.isConnected = true;
          this.status.latencyMs = elapsed;
          this.status.fps = Math.round(1000 / Math.max(elapsed, intervalMs));
          this.status.lastError = null;
          this.status.reconnectAttempts = 0;

          this.frameListeners.forEach(cb => cb(result));
        }
      } catch (err: any) {
        this.status.isConnected = false;
        this.status.reconnectAttempts += 1;
        this.status.lastError = err?.message || 'Transmission failed';
      } finally {
        this.emitStatus();
        if (this.status.isStreaming) {
          this.intervalTimer = setTimeout(loop, intervalMs);
        }
      }
    };

    loop();
  }

  public stopStreaming() {
    this.status.isStreaming = false;
    this.status.isConnected = false;
    if (this.intervalTimer) {
      clearTimeout(this.intervalTimer);
      this.intervalTimer = null;
    }
    if (this.peerConnection) {
      this.peerConnection.close();
      this.peerConnection = null;
    }
    this.emitStatus();
  }

  public async initWebRTC(stream: any, _signalingWsUrl: string): Promise<void> {
    if (!RTCPeerConnectionModule) return;
    const configuration = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };
    this.peerConnection = new RTCPeerConnectionModule(configuration);

    if (stream && stream.getTracks) {
      stream.getTracks().forEach((track: any) => {
        this.peerConnection?.addTrack(track, stream);
      });
    }

    const offer = await this.peerConnection.createOffer({
      offerToReceiveAudio: false,
      offerToReceiveVideo: false,
    });
    await this.peerConnection.setLocalDescription(offer);
  }
}

export const cameraStreamingService = new CameraStreamingService();
