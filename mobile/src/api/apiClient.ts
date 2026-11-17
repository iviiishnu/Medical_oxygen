import axios, { AxiosInstance } from 'axios';
import Constants from 'expo-constants';
import { StorageService } from '../utils/storage';

function getExpoComputerHost(): string | null {
  const hostUri = Constants.expoConfig?.hostUri;
  if (!hostUri) return null;
  const authority = hostUri.replace(/^[a-z][a-z0-9+.-]*:\/\//i, '').split('/')[0];
  const host = authority.startsWith('[')
    ? authority.slice(0, authority.indexOf(']') + 1)
    : authority.replace(/:\d+$/, '');
  if (!host || host === 'localhost' || host === '127.0.0.1' || host.includes('exp.direct')) return null;
  return host;
}

function getConfiguredVisionPort(): number {
  const port = Number(Constants.expoConfig?.extra?.o2VisionPort);
  return Number.isInteger(port) && port > 0 && port < 65536 ? port : 8765;
}

function getConfiguredBackendUrl(): string | null {
  const configured = Constants.expoConfig?.extra?.o2BackendUrl;
  return typeof configured === 'string' && configured.trim() ? configured.trim().replace(/\/+$/, '') : null;
}

function getExpoComputerUrl(): string | null {
  const host = getExpoComputerHost();
  return host ? `http://${host}:${getConfiguredVisionPort()}` : null;
}

export interface VisionReadResponse {
  verdict: 'NORMAL' | 'ABNORMAL' | "CAN'T TELL";
  confidence_pct: number;
  reading: number | null;
  unit: string | null;
  reading_confidence_pct: number | null;
  gauge_type: string | null;
  scale: number | null;
  low_limit: number;
  main_gauge: number | null;
  gas: string | null;
  gauges: Array<{
    number: number;
    gas: string;
    reading: number | null;
    unit: string;
    scale: number;
    confidence_pct: number;
    status: string;
    main: boolean;
    kind: string;
    scale_source?: string;
    low_threshold?: number;
    critical_threshold?: number;
    ignored?: boolean;
  }>;
  lamps: Array<{
    color: string;
    strength: number;
  }>;
  ms: number;
  image?: string;
  error?: string;
  alert?: boolean;
}

export class ApiClient {
  private client: AxiosInstance;
  private baseUrl: string;

  constructor(baseUrl: string = getConfiguredBackendUrl() ?? getExpoComputerUrl() ?? 'http://10.0.2.2:8000') {
    this.baseUrl = baseUrl;
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 30000,
    });

    this.client.interceptors.request.use(async config => {
      const token = await StorageService.getAuthToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });
  }

  public setBaseUrl(url: string) {
    let normalizedUrl = url.trim().replace(/\/+$/, '');
    if (normalizedUrl && !/^https?:\/\//i.test(normalizedUrl)) normalizedUrl = `http://${normalizedUrl}`;
    normalizedUrl = normalizedUrl.replace(/\/api(?:\/(?:read|health))?$/i, '');
    this.baseUrl = normalizedUrl;
    this.client.defaults.baseURL = normalizedUrl;
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  public async getApi<T>(path: string): Promise<T> {
    const response = await this.client.get<T>(path);
    return response.data;
  }

  public async postApi<T>(path: string, body: unknown): Promise<T> {
    const response = await this.client.post<T>(path, body);
    return response.data;
  }

  /** Uses Expo Go's packager host first; the model server normally runs on that same computer. */
  public async autoConfigure(savedUrl?: string): Promise<string> {
    const expoHost = getExpoComputerHost();
    const candidates = [...new Set([
      getConfiguredBackendUrl(),
      ...(expoHost ? [...new Set([getConfiguredVisionPort(), 8765, 8766, 8767, 8000, 8001, 8002, 8003, 8088, 9000])].map(port => `http://${expoHost}:${port}`) : []),
      savedUrl?.trim().replace(/\/+$/, ''),
      'http://10.0.2.2:8000',
    ].filter((url): url is string => Boolean(url)))];

    for (const url of candidates) {
      this.setBaseUrl(url);
      try {
        if (!await this.checkConnection(1500)) continue;
        await StorageService.saveSettings({ visionApiUrl: url });
        return url;
      } catch (error) {
        if (error instanceof Error && error.message.includes('PostgreSQL is not ready')) throw error;
        // Try the saved address or Android emulator host before reporting failure.
      }
    }

    this.setBaseUrl(getConfiguredBackendUrl() ?? getExpoComputerUrl() ?? savedUrl ?? 'http://10.0.2.2:8000');
    throw new Error(`Could not find the model server. Checked ${candidates.join(', ')}. Keep Expo and the model server running on the same computer, then retry.`);
  }

  public async checkConnection(timeoutMs = 5000): Promise<boolean> {
    try {
      const response = await this.client.get<{ ok: boolean; service?: string; postgres_ready?: boolean }>('/api/health', { timeout: timeoutMs });
      // Vision reachability is independent of PostgreSQL readiness. Image analysis for
      // panel registration does not need a database; device readings report persistence
      // errors separately when the API cannot save them.
      return response.data?.ok === true && response.data.service === 'o2-vision';
    } catch (error) {
      if (axios.isAxiosError(error)) {
        if (error.response) {
          if (error.response.status === 404) {
            throw new Error(`The server at ${this.baseUrl} is an old or unrelated service (missing /api/health). Restart with “npm start -- --clear” to select the current model server.`);
          }
          const detail = typeof error.response.data?.error === 'string'
            ? `: ${error.response.data.error}`
            : '';
          throw new Error(`Model server returned HTTP ${error.response.status}${detail}`);
        }
        if (error.code === 'ECONNABORTED') {
          throw new Error(`Timed out connecting to ${this.baseUrl}. Check the address and computer firewall.`);
        }
        throw new Error(`Cannot reach ${this.baseUrl}. Start the server with --host 0.0.0.0, then check the computer's LAN IP, Wi-Fi isolation, and firewall.`);
      }
      throw error;
    }
  }

  /**
   * Upload camera frame to backend Vision API /api/read
   */
  public async uploadFrame(
    imageBlob: Blob | { uri: string; type: string; name: string },
    maxScale?: number,
    options?: { includeImage?: 'never' | 'always' | 'on_alert'; deviceId?: string; gauges?: Array<{ number: number; ignored?: boolean; low_threshold?: number; critical_threshold?: number }> }
  ): Promise<VisionReadResponse> {
    const formData = new FormData();
    // @ts-ignore React Native FormData accepts uri object
    formData.append('image', imageBlob);
    if (maxScale !== undefined) {
      formData.append('max', String(maxScale));
    }
    if (options?.includeImage) formData.append('include_image', options.includeImage);
    if (options?.deviceId) formData.append('device_id', options.deviceId);
    if (options?.gauges) formData.append('gauges', JSON.stringify(options.gauges));

    try {
      // Leave Content-Type unset so React Native's networking layer adds the multipart boundary.
      const res = await this.client.post<VisionReadResponse>('/api/read', formData);
      return res.data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        if (error.response) {
          if (error.response.status === 404) {
            throw new Error(`The server at ${this.baseUrl} does not provide /api/read. Restart with “npm start -- --clear” so the current model server is selected.`);
          }
          const detail = typeof error.response.data?.error === 'string'
            ? `: ${error.response.data.error}`
            : '';
          throw new Error(`Model server returned HTTP ${error.response.status}${detail}`);
        }
        if (error.code === 'ECONNABORTED') {
          throw new Error('The model took too long to respond. Try again or use a smaller image.');
        }
        throw new Error(`Cannot reach ${this.baseUrl}. Start the server with --host 0.0.0.0, then check the address, Wi-Fi, and computer firewall.`);
      }
      throw error;
    }
  }
}

export const defaultApiClient = new ApiClient();

