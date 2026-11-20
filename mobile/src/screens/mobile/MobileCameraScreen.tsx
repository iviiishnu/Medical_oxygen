import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { defaultApiClient, type VisionReadResponse } from '../../api/apiClient';
import { StorageService } from '../../utils/storage';
import { useResponsive } from '../../hooks/useResponsive';
import { useIsFocused } from '@react-navigation/native';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';
import type { DataSource } from '../../api/dataSource';
import { useMonitoring } from '../../hooks/useMonitoring';

interface Props { source: DataSource; onRegisterDevice: () => void; }

function readingHelp(reasons: string[]): string {
  const friendly: Record<string, string> = {
    frame_too_dark: 'The photo is too dark. Add steady light and avoid shadows.',
    frame_blown_out: 'The photo is washed out. Turn away from direct light or glare.',
    frame_uniform_camera_blocked: 'The camera view looks blocked. Clean the lens and uncover it.',
    no_needle_peak: 'The needle is unclear. Move closer and keep the camera steady.',
    dial_outside_frame: 'Keep the whole gauge face inside the camera frame.',
  };
  const useful = reasons.map(reason => friendly[reason] ?? reason).join(' · ');
  return `${useful}. Keep the gauge sharp and avoid reflections.`;
}

export const MobileCameraScreen: React.FC<Props> = ({ source, onRegisterDevice }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const { isLandscape } = useResponsive();
  const isFocused = useIsFocused();
  const camera = useRef<CameraView>(null);
  const busy = useRef(false);
  const discoveryTask = useRef<Promise<string> | null>(null);
  const connectionReady = useRef(false);
  const alertLatched = useRef(false);
  const liveReadFailed = useRef(false);
  const [permission, requestPermission] = useCameraPermissions();
  const [running, setRunning] = useState(false);
  const [facing, setFacing] = useState<'back' | 'front'>('back');
  const [reading, setReading] = useState<VisionReadResponse | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [alertEvidence, setAlertEvidence] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'checking' | 'connected' | 'unavailable'>('checking');
  const [serverAddress, setServerAddress] = useState(defaultApiClient.getBaseUrl());
  const { devices } = useMonitoring(source);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const selectedDevice = devices.find(device => device.id === selectedDeviceId) ?? null;

  useEffect(() => {
    if (selectedDeviceId && !devices.some(device => device.id === selectedDeviceId)) {
      setSelectedDeviceId('');
      setRunning(false);
    }
  }, [devices, selectedDeviceId]);
  useEffect(() => { setRunning(false); setReading(null); setPreview(null); setAlertEvidence(null); alertLatched.current = false; }, [selectedDeviceId]);

  const autoConnect = React.useCallback(async () => {
    if (discoveryTask.current) return discoveryTask.current;
    const task = (async () => {
      setConnectionStatus('checking');
      try {
        const settings = await StorageService.getSettings();
        const url = await defaultApiClient.autoConfigure(settings.visionApiUrl);
        connectionReady.current = true;
        setServerAddress(url);
        setConnectionStatus('connected');
        return url;
      } catch (e) {
        connectionReady.current = false;
        setServerAddress(defaultApiClient.getBaseUrl());
        setConnectionStatus('unavailable');
        setError(e instanceof Error ? e.message : 'Could not connect to the model server.');
        throw e;
      }
    })();
    discoveryTask.current = task;
    try {
      return await task;
    } finally {
      if (discoveryTask.current === task) discoveryTask.current = null;
    }
  }, []);

  const refreshConnection = React.useCallback(async () => {
    if (discoveryTask.current) {
      await discoveryTask.current;
      return;
    }
    if (connectionReady.current) {
      try {
        await defaultApiClient.checkConnection();
        return;
      } catch {
        connectionReady.current = false;
      }
    }
    await autoConnect();
  }, [autoConnect]);

  useEffect(() => {
    if (!isFocused) return;
    let active = true;
    const check = () => { if (active) void refreshConnection().catch(() => {}); };
    check();
    const timer = setInterval(check, 15000);
    const appStateListener = AppState.addEventListener('change', (state: any) => {
      if (state === 'active') check();
    });
    return () => {
      active = false;
      clearInterval(timer);
      appStateListener.remove();
    };
  }, [isFocused, refreshConnection]);

  useEffect(() => {
    if (!running || !isFocused) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const capture = async () => {
      if (!active) return;
      const cycleStartedAt = Date.now();
      if (!busy.current && camera.current) {
        busy.current = true;
        try {
          const photo = await camera.current.takePictureAsync({ quality: 0.55, skipProcessing: true });
          if (photo?.uri) await submit(photo.uri, false, true);
        } catch (e) {
          if (active) setError(e instanceof Error ? e.message : 'Camera capture failed');
        } finally { busy.current = false; }
      }
      // Cap capture frequency to one frame per second. Slow inference naturally
      // spaces frames further apart; never abandon a request while the server works.
      if (active && !liveReadFailed.current) {
        timer = setTimeout(capture, Math.max(0, 1000 - (Date.now() - cycleStartedAt)));
      }
    };
    timer = setTimeout(capture, 300);
    return () => { active = false; clearTimeout(timer); };
  }, [running, isFocused, selectedDeviceId]);

  useEffect(() => { if (!isFocused) setRunning(false); }, [isFocused]);

  const submit = async (uri: string, showPreview = true, live = false) => {
    // Live frames are processed in the background; keep the visible reading stable
    // until the user requests a photo read or a threshold alert needs attention.
    if (!live) setLoading(true);
    if (!live) setError('');
    if (showPreview) setPreview(uri);
    try {
      if (!connectionReady.current) await autoConnect();
      const gaugeConfig = selectedDevice?.gauges?.map(gauge => ({
        number: gauge.number,
        ignored: !!gauge.ignored,
        low_threshold: gauge.lowThreshold,
        critical_threshold: gauge.criticalThreshold,
        high_threshold: gauge.highThreshold,
      }));
      // Demo panels live only in AsyncStorage. Send their gauge settings for analysis,
      // but don't present their local IDs as PostgreSQL records to the authenticated API.
      const backendDeviceId = source.mode === 'postgres' ? selectedDeviceId : undefined;
      const result = await defaultApiClient.uploadFrame(
        { uri, type: 'image/jpeg', name: `${selectedDevice?.id ?? 'panel'}-reading.jpg` },
        undefined,
        { includeImage: live ? (alertLatched.current ? 'never' : 'on_alert') : 'always', deviceId: backendDeviceId, gauges: gaugeConfig, timeoutMs: live ? 30000 : undefined },
      );
      if (live) {
        if (result.alert) {
          setReading(result);
          if (!alertLatched.current) setAlertEvidence(result.image ?? uri);
          alertLatched.current = true;
        } else {
          alertLatched.current = false;
        }
      } else {
        setReading(result);
        if (result.image) setPreview(result.image);
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not reach the vision model';
      setError(message);
      // Keep the first live failure visible and stop retries until the user restarts.
      if (live) {
        liveReadFailed.current = true;
        setRunning(false);
      }
      if (e instanceof Error && e.message.startsWith('Cannot reach')) {
        connectionReady.current = false;
        void autoConnect().catch(() => {});
      }
    } finally { if (!live) setLoading(false); }
  };

  const chooseImage = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.85 });
      if (!result.canceled && result.assets[0]?.uri) {
        setRunning(false);
        await submit(result.assets[0].uri);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not open the image picker.');
    }
  };

  const captureOnce = async () => {
    if (!camera.current || busy.current) return;
    busy.current = true;
    try {
      const photo = await camera.current.takePictureAsync({ quality: 0.85 });
      if (photo?.uri) await submit(photo.uri);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Photo capture failed';
      setError(message);
      if (running) {
        liveReadFailed.current = true;
        setRunning(false);
      }
    }
    finally { busy.current = false; }
  };

  return (
    <ScrollView nestedScrollEnabled contentContainerStyle={styles.page}>
      <View style={styles.heading}>
        <Text style={styles.title}>Camera reader</Text>
        <Text style={styles.subtitle}>Live panel feed and image readings from the vision model</Text>
        <View style={styles.connectionRow}>
          <View style={[styles.connectionDot, connectionStatus === 'connected' ? styles.connectionDotReady : connectionStatus === 'unavailable' ? styles.connectionDotFailed : null]} />
          <Text style={styles.connectionLabel}>
            {connectionStatus === 'checking' ? 'Finding model server…' : connectionStatus === 'connected' ? `Connected · ${serverAddress}` : 'Model server not found · retrying automatically'}
          </Text>
          {connectionStatus === 'unavailable' && <TouchableOpacity onPress={() => void autoConnect().catch(() => {})}><Text style={styles.retryText}>Retry</Text></TouchableOpacity>}
        </View>
      </View>
      <View style={styles.card}>
        <Text style={styles.selectorTitle}>Monitoring panel</Text>
        {devices.length ? (
          <View style={styles.deviceChoices}>
            {devices.map(device => (
              <TouchableOpacity key={device.id} style={[styles.deviceChoice, selectedDeviceId === device.id && styles.deviceChoiceSelected]} onPress={() => setSelectedDeviceId(device.id)}>
                <Text style={[styles.deviceChoiceName, selectedDeviceId === device.id && styles.deviceChoiceTextSelected]} numberOfLines={1}>{device.name}</Text>
                <Text style={[styles.deviceChoiceMeta, selectedDeviceId === device.id && styles.deviceChoiceTextSelected]}>{device.id}</Text>
              </TouchableOpacity>
            ))}
          </View>
        ) : <Text style={styles.meta}>No registered panels found.</Text>}
        <TouchableOpacity style={styles.registerButton} onPress={onRegisterDevice}>
          <Text style={styles.registerButtonText}>＋ Register a new panel</Text>
        </TouchableOpacity>
        {selectedDevice && <Text style={styles.meta}>Selected: {selectedDevice.name}{selectedDevice.gauges?.length ? ` · ${selectedDevice.gauges.filter(g => !g.ignored).length} gauge(s) included` : ''}{source.mode === 'demo' ? ' · demo analysis only; readings are not saved' : ''}</Text>}
        {permission?.granted ? (
          <View style={[styles.cameraFrame, isLandscape && styles.cameraLandscape]}>
            {isFocused && <CameraView ref={camera} style={StyleSheet.absoluteFill} facing={facing} mode="picture" autofocus="on" />}
            {preview && !running && <Image source={{ uri: preview }} style={styles.preview} resizeMode="contain" />}
            <View style={styles.livePill}><View style={[styles.dot, running && styles.dotLive]} /><Text style={styles.liveText}>{running ? 'LIVE · model reading' : 'CAMERA READY'}</Text></View>
          </View>
        ) : (
          <View style={styles.permissionBox}>
            <Text style={styles.permissionTitle}>Camera access</Text>
            <Text style={styles.subtitle}>Allow camera access to stream the panel to the reading model.</Text>
            <TouchableOpacity style={styles.primaryButton} onPress={requestPermission}><Text style={styles.primaryText}>Allow camera</Text></TouchableOpacity>
          </View>
        )}
        <View style={styles.actions}>
          <TouchableOpacity style={[styles.primaryButton, running && styles.stopButton]} onPress={() => {
            setPreview(null);
            alertLatched.current = false;
            if (running) setRunning(false);
            else { liveReadFailed.current = false; setError(''); setRunning(true); }
          }} disabled={!permission?.granted || !selectedDevice}>
            <Text style={styles.primaryText}>{running ? 'Stop live reading' : 'Start live reading'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryButton} onPress={captureOnce} disabled={!permission?.granted || loading || running}>
            <Text style={styles.secondaryText}>Read photo</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryButton} onPress={chooseImage} disabled={loading || running}>
            <Text style={styles.secondaryText}>Upload image</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.flipButton} onPress={() => setFacing(v => v === 'back' ? 'front' : 'back')}><Text style={styles.secondaryText}>Flip camera</Text></TouchableOpacity>
        </View>
      </View>

      <View style={styles.card}>
        <View style={styles.resultHead}><Text style={styles.sectionTitle}>Latest reading</Text>{loading && !running && <ActivityIndicator color={colors.series} />}</View>
        {error ? <View style={styles.errorNotice}><Text style={styles.error}>{error}</Text><TouchableOpacity onPress={() => setError('')}><Text style={styles.errorDismiss}>Dismiss</Text></TouchableOpacity></View> : reading ? (
          <>
            <View style={styles.resultRow}><Text style={styles.reading}>{reading.reading == null ? '—' : reading.reading.toFixed(2)}</Text><Text style={styles.unit}>{reading.unit ?? ''}</Text><Text style={[styles.verdict, reading.verdict === 'NORMAL' ? styles.normal : reading.verdict === 'ABNORMAL' ? styles.abnormal : styles.uncertain]}>{reading.verdict}</Text></View>
            {alertEvidence && <View><Text style={styles.alertEvidenceLabel}>Image captured for the latest alert</Text><Image source={{ uri: alertEvidence }} style={styles.alertEvidence} resizeMode="contain" /></View>}
            <Text style={styles.meta}>{reading.gauge_type ?? 'Gauge'}{reading.gas ? ` · ${reading.gas}` : ''} · {reading.confidence_pct}% confidence · {reading.ms} ms</Text>
            {!!reading.reasons?.length && reading.verdict === "CAN'T TELL" && <Text style={styles.readHelp}>{readingHelp(reading.reasons)}</Text>}
            {!!reading.gauges?.length && reading.gauges.length > 1 && reading.gauges.map(g => <Text key={g.number} style={styles.meta}>Gauge {g.number}{g.gas ? ` · ${g.gas}` : ''}: {g.reading == null ? 'No reading' : `${g.reading.toFixed(2)} ${g.unit}`} · {g.status}</Text>)}
            {!!reading.lamps?.length && <Text style={styles.meta}>Panel lamps: {reading.lamps.map(l => `${l.color} ${Math.round(l.strength * 100)}%`).join(' · ')}</Text>}
          </>
        ) : <Text style={styles.subtitle}>{selectedDevice ? 'Start live reading, take a photo, or upload an image to see the model result.' : 'Upload an image or take a photo for model analysis. Select a registered panel to save readings or start live reading. Keep the whole gauge in frame, steady the camera, and use even light without glare.'}</Text>}
      </View>
      <Text style={styles.note}>The vision server must be running and reachable from this device. Set its computer’s local network address in Settings.</Text>
    </ScrollView>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  page: { padding: 16, gap: 16, backgroundColor: colors.page, flexGrow: 1 },
  heading: { gap: 4 }, title: { fontSize: 24, fontWeight: '700', color: colors.ink }, subtitle: { fontSize: 14, color: colors.ink2, lineHeight: 20 },
  connectionRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginTop: 4 }, connectionDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.warning }, connectionDotReady: { backgroundColor: colors.good }, connectionDotFailed: { backgroundColor: colors.critical }, connectionLabel: { flex: 1, color: colors.ink2, fontSize: 12 }, retryText: { color: colors.series, fontSize: 12, fontWeight: '700', padding: 4 },
  card: { backgroundColor: colors.surface, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border, gap: 14 },
  selectorTitle: { color: colors.ink, fontSize: 14, fontWeight: '800', marginTop: 3 },
  deviceChoices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  deviceChoice: { maxWidth: '100%', borderWidth: 1, borderColor: colors.grid, borderRadius: 10, paddingHorizontal: 11, paddingVertical: 8, backgroundColor: colors.page },
  deviceChoiceSelected: { backgroundColor: colors.series, borderColor: colors.series },
  deviceChoiceName: { color: colors.ink, fontSize: 13, fontWeight: '700' },
  deviceChoiceMeta: { color: colors.ink2, fontSize: 10, marginTop: 2 },
  deviceChoiceTextSelected: { color: '#fff' },
  registerButton: { borderWidth: 1, borderStyle: 'dashed', borderColor: colors.series, borderRadius: 9, padding: 10, alignItems: 'center' },
  registerButtonText: { color: colors.series, fontWeight: '700', fontSize: 13 },
  cameraFrame: { height: 360, minHeight: 230, backgroundColor: '#111', borderRadius: 8, overflow: 'hidden', position: 'relative' }, cameraLandscape: { height: 230 }, preview: { ...StyleSheet.absoluteFill, width: '100%', height: '100%' },
  alertEvidence: { width: '100%', height: 210, borderRadius: 8, backgroundColor: '#111', marginTop: 8 },
  alertEvidenceLabel: { color: colors.critical, fontSize: 12, fontWeight: '700', marginTop: 8 }, readHelp: { color: colors.warning, fontSize: 13, lineHeight: 19 },
  livePill: { position: 'absolute', top: 12, left: 12, flexDirection: 'row', alignItems: 'center', gap: 7, borderRadius: 20, backgroundColor: 'rgba(11,11,11,0.75)', paddingHorizontal: 12, paddingVertical: 7 }, dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#898781' }, dotLive: { backgroundColor: '#0ca30c' }, liveText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  permissionBox: { minHeight: 230, justifyContent: 'center', alignItems: 'center', gap: 10, backgroundColor: colors.page, borderRadius: 8, padding: 22 }, permissionTitle: { fontSize: 18, fontWeight: '700', color: colors.ink },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, primaryButton: { backgroundColor: colors.ink, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 11, alignItems: 'center' }, stopButton: { backgroundColor: colors.critical }, primaryText: { color: colors.surface, fontWeight: '700', fontSize: 13 }, secondaryButton: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 11, backgroundColor: colors.surface }, secondaryText: { color: colors.ink, fontWeight: '600', fontSize: 13 }, flipButton: { paddingHorizontal: 8, justifyContent: 'center' },
  resultHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, sectionTitle: { fontSize: 17, fontWeight: '700', color: colors.ink }, resultRow: { flexDirection: 'row', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }, reading: { fontSize: 48, lineHeight: 56, fontWeight: '700', color: colors.ink, fontVariant: ['tabular-nums'] }, unit: { fontSize: 16, color: colors.ink2 }, verdict: { marginLeft: 'auto', overflow: 'hidden', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5, color: '#fff', fontWeight: '700', fontSize: 12 }, normal: { backgroundColor: colors.good }, abnormal: { backgroundColor: colors.critical }, uncertain: { backgroundColor: colors.serious }, meta: { color: colors.ink2, fontSize: 13, marginTop: 3 }, errorNotice: { gap: 8, alignItems: 'flex-start' }, error: { color: colors.critical, lineHeight: 20 }, errorDismiss: { color: colors.series, fontWeight: '700', paddingVertical: 4 }, note: { color: colors.muted, fontSize: 12, lineHeight: 18 },
});
