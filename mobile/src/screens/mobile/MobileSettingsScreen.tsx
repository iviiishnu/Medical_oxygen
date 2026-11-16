import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Switch,
  Alert,
  type ScrollViewInstance,
} from 'react-native';
import type { DataSource } from '../../api/dataSource';
import { StorageService, AppSettings } from '../../utils/storage';
import * as ImagePicker from 'expo-image-picker';
import { Image, ActivityIndicator } from 'react-native';
import { defaultApiClient } from '../../api/apiClient';
import type { RegisteredGauge } from '../../types/monitoring';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';

interface Props {
  source: DataSource;
  onSignOut: () => void;
  onToggleDemoMode: (enabled: boolean) => void;
  darkMode: boolean;
  onToggleDarkMode: (enabled: boolean) => void;
  focusRegistration?: boolean;
  onRegistrationFocused?: () => void;
}

type GaugeDraft = RegisteredGauge & { lowText: string; criticalText: string };

export const MobileSettingsScreen: React.FC<Props> = ({
  source,
  onSignOut,
  onToggleDemoMode,
  darkMode,
  onToggleDarkMode,
  focusRegistration,
  onRegistrationFocused,
}) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const palette = colors;
  const [settings, setSettings] = useState<AppSettings>({
    demoMode: source.mode === 'demo',
    soundEnabled: true,
    visionApiUrl: defaultApiClient.getBaseUrl(),
    darkMode: false,
  });
  const [visionUrlInput, setVisionUrlInput] = useState(defaultApiClient.getBaseUrl());
  const [checkingVision, setCheckingVision] = useState(false);
  const [visionConnection, setVisionConnection] = useState<string | null>(null);
  const [registrationName, setRegistrationName] = useState('');
  const [registrationPhoto, setRegistrationPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [detectedGauges, setDetectedGauges] = useState<GaugeDraft[]>([]);
  const [readingPhoto, setReadingPhoto] = useState(false);
  const [savingDevice, setSavingDevice] = useState(false);
  const settingsScroll = useRef<ScrollViewInstance>(null);
  const [registrationOffset, setRegistrationOffset] = useState(0);

  useEffect(() => {
    StorageService.getSettings().then(s => {
      setSettings(s);
      setVisionUrlInput(s.visionApiUrl);
    });
  }, []);

  useEffect(() => {
    if (focusRegistration && registrationOffset > 0) {
      settingsScroll.current?.scrollTo({ y: registrationOffset, animated: true });
      onRegistrationFocused?.();
    }
  }, [focusRegistration, registrationOffset, onRegistrationFocused]);

  const handleSaveUrl = async () => {
    defaultApiClient.setBaseUrl(visionUrlInput);
    const normalizedUrl = defaultApiClient.getBaseUrl();
    setVisionUrlInput(normalizedUrl);
    await StorageService.saveSettings({ visionApiUrl: normalizedUrl });
    Alert.alert('Settings Saved', `Backend URL set to: ${normalizedUrl}`);
  };

  const handleTestVision = async () => {
    defaultApiClient.setBaseUrl(visionUrlInput);
    setVisionUrlInput(defaultApiClient.getBaseUrl());
    setCheckingVision(true);
    setVisionConnection(null);
    try {
      const reachable = await defaultApiClient.checkConnection();
      if (!reachable) throw new Error(`The server at ${defaultApiClient.getBaseUrl()} did not identify as the O2 model service.`);
      setVisionConnection(`Connected to ${defaultApiClient.getBaseUrl()}`);
    } catch (error) {
      setVisionConnection(error instanceof Error ? error.message : 'Could not connect to the model server.');
    } finally {
      setCheckingVision(false);
    }
  };

  const handleToggleDemo = (val: boolean) => {
    setSettings(prev => ({ ...prev, demoMode: val }));
    StorageService.saveSettings({ demoMode: val });
    onToggleDemoMode(val);
  };

  const handleSelectRegistrationPhoto = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'], quality: 0.45, base64: true, allowsEditing: false,
    });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    if (!asset.base64) {
      Alert.alert('Image unavailable', 'Please choose a JPG or PNG image and try again.');
      return;
    }
    setRegistrationPhoto(asset);
    setDetectedGauges([]);
    setReadingPhoto(true);
    try {
      const saved = await StorageService.getSettings();
      await defaultApiClient.autoConfigure(saved.visionApiUrl);
      const result = await defaultApiClient.uploadFrame({
        uri: asset.uri, type: asset.mimeType ?? 'image/jpeg', name: asset.fileName ?? 'registration.jpg',
      });
      const gauges = result.gauges ?? [];
      if (!gauges.length) throw new Error('No gauges were detected. Try a clearer, well-lit photo of the whole panel.');
      setDetectedGauges(gauges.map((g, index) => ({
        number: g.number,
        name: g.gas?.trim() || `Gauge ${index + 1}`,
        unit: g.unit?.trim() || 'Unit not recognized',
        kind: g.kind || 'analog',
        scale: g.scale,
        reading: g.reading,
        confidencePct: g.confidence_pct,
        ignored: false,
        lowText: '',
        criticalText: '',
      })));
      if (result.verdict === "CAN'T TELL") {
        Alert.alert('Review the detected gauges', 'The model found gauge candidates, but confidence is low. Confirm each gauge name and unit before entering thresholds.');
      }
    } catch (error) {
      Alert.alert('Could not read this image', error instanceof Error ? error.message : 'Check the model server connection and try again.');
    } finally {
      setReadingPhoto(false);
    }
  };

  const updateGauge = (index: number, field: 'lowText' | 'criticalText', value: string) => {
    setDetectedGauges(current => current.map((gauge, i) => i === index ? { ...gauge, [field]: value } : gauge));
  };

  const handleRegisterDevice = async () => {
    const name = registrationName.trim();
    if (!name || !registrationPhoto?.base64 || !detectedGauges.length) {
      Alert.alert('Incomplete registration', 'Enter a panel name, add a photo, and read its gauges first.');
      return;
    }
    if (registrationPhoto.base64.length > 650_000) {
      Alert.alert('Image is too large', 'Choose a smaller photo. The saved registration image must be under 500 KB.');
      return;
    }
    if (!detectedGauges.some(g => !g.ignored)) {
      Alert.alert('Select a gauge', 'At least one detected gauge must remain enabled for reading.');
      return;
    }
    const gauges: RegisteredGauge[] = [];
    for (let i = 0; i < detectedGauges.length; i++) {
      const g = detectedGauges[i];
      if (g.ignored) {
        gauges.push({ number: g.number, name: g.name, unit: g.unit, kind: g.kind, scale: g.scale, reading: g.reading,
          confidencePct: g.confidencePct, ignored: true });
        continue;
      }
      const lowThreshold = Number(g.lowText);
      const criticalThreshold = Number(g.criticalText);
      if (g.lowText.trim() === '' || g.criticalText.trim() === '' || !Number.isFinite(lowThreshold) || !Number.isFinite(criticalThreshold) || criticalThreshold >= lowThreshold) {
        Alert.alert('Check gauge thresholds', `${g.name}: enter numeric values and set Critical below Low.`);
        return;
      }
      gauges.push({ number: g.number, name: g.name, unit: g.unit, kind: g.kind, scale: g.scale, reading: g.reading,
        confidencePct: g.confidencePct, lowThreshold, criticalThreshold });
    }
    setSavingDevice(true);
    try {
      const imageType = registrationPhoto.mimeType ?? 'image/jpeg';
      await source.registerDevice({
        id: `panel-${Date.now()}`, name, createdBy: source.userName(), gauges,
        registrationImage: `data:${imageType};base64,${registrationPhoto.base64}`,
      });
      setRegistrationName(''); setRegistrationPhoto(null); setDetectedGauges([]);
      const includedCount = gauges.filter(gauge => !gauge.ignored).length;
      Alert.alert('Panel registered', `${name} was saved with ${includedCount} included gauge${includedCount === 1 ? '' : 's'}; ignored gauges will be skipped in live reading.`);
    } catch (error) {
      Alert.alert('Could not save panel', error instanceof Error ? error.message : 'Check your database connection and try again.');
    } finally {
      setSavingDevice(false);
    }
  };

  return (
    <ScrollView ref={settingsScroll} contentContainerStyle={styles.scroll}>
      {/* Account Info */}
      <View style={styles.card}>
        <Text style={styles.sectionHeader}>Staff Account</Text>
        <Text style={styles.emailText}>Signed in as: {source.userName() || 'Demo User'}</Text>
        <Text style={styles.metaText}>Source Provider: {source.mode.toUpperCase()}</Text>

        <TouchableOpacity style={styles.signOutBtn} onPress={onSignOut}>
          <Text style={styles.signOutBtnText}>Sign Out</Text>
        </TouchableOpacity>
      </View>

      {/* Backend & Network Settings */}
      <View style={styles.card}>
        <Text style={styles.sectionHeader}>Backend Connectivity</Text>
        <Text style={styles.inputLabel}>Vision Inference API Endpoint:</Text>
        <TextInput
          style={styles.input}
          value={visionUrlInput}
          onChangeText={setVisionUrlInput}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="http://10.0.2.2:8000"
          placeholderTextColor={colors.muted}
        />
        <View style={styles.buttonRow}>
          <TouchableOpacity style={styles.saveBtn} onPress={handleSaveUrl}>
            <Text style={styles.saveBtnText}>Update URL</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.testBtn} onPress={handleTestVision} disabled={checkingVision}>
            <Text style={styles.testBtnText}>{checkingVision ? 'Checking…' : 'Test server'}</Text>
          </TouchableOpacity>
        </View>
        {!!visionConnection && <Text style={styles.connectionText}>{visionConnection}</Text>}

        <View style={styles.switchRow}>
          <View style={styles.switchLabelWrap}>
            <Text style={styles.switchTitle}>Offline Demo Mode</Text>
            <Text style={styles.switchSubtitle}>
              Simulate clinical telemetry and threshold leaks locally
            </Text>
          </View>
          <Switch
            value={settings.demoMode}
            onValueChange={handleToggleDemo}
            trackColor={{ false: colors.grid, true: colors.seriesLight }}
            thumbColor={settings.demoMode ? colors.series : colors.muted}
          />
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionHeader}>Appearance</Text>
        <View style={styles.switchRow}>
          <View style={styles.switchLabelWrap}>
            <Text style={styles.switchTitle}>Dark theme</Text>
            <Text style={styles.switchSubtitle}>Use a low-glare palette across the app</Text>
          </View>
          <Switch
            value={darkMode}
            onValueChange={async enabled => {
              await StorageService.saveSettings({ darkMode: enabled });
              onToggleDarkMode(enabled);
            }}
            trackColor={{ false: palette.grid, true: palette.seriesLight }}
            thumbColor={darkMode ? palette.series : palette.muted}
          />
        </View>
      </View>

      <View style={styles.card} onLayout={event => setRegistrationOffset(event.nativeEvent.layout.y)}>
        <Text style={styles.sectionHeader}>Register a monitoring panel</Text>
        <Text style={styles.metaText}>Upload a clear panel photo. The vision model identifies gauge names, types, units, scales, and current readings; enter the Low and Critical thresholds for each one.</Text>
        <TextInput style={styles.input} value={registrationName} onChangeText={setRegistrationName} placeholder="Panel name (e.g. Ward 3 oxygen panel)" placeholderTextColor={colors.muted} />
        <View style={styles.buttonRow}>
          <TouchableOpacity style={styles.saveBtn} onPress={handleSelectRegistrationPhoto} disabled={readingPhoto}>
            <Text style={styles.saveBtnText}>{readingPhoto ? 'Reading image…' : registrationPhoto ? 'Choose another image' : 'Choose panel image'}</Text>
          </TouchableOpacity>
          {readingPhoto && <ActivityIndicator color={colors.series} />}
        </View>
        {registrationPhoto && <Image source={{ uri: registrationPhoto.uri }} style={styles.registrationPreview} resizeMode="cover" />}
        {detectedGauges.map((gauge, index) => (
          <View key={`${gauge.name}-${index}`} style={styles.gaugeDraft}>
            <Text style={styles.gaugeTitle}>{gauge.name} · {gauge.kind}</Text>
            <Text style={styles.metaText}>Unit: {gauge.unit} · Scale: {Number.isFinite(gauge.scale) ? `0–${gauge.scale}` : 'not recognized'} · Current: {gauge.reading == null ? 'not read' : `${gauge.reading} ${gauge.unit}`} · Confidence: {gauge.confidencePct}%</Text>
            <View style={styles.ignoreRow}>
              <Text style={styles.metaText}>{gauge.ignored ? 'Excluded from live reading' : 'Include in live reading'}</Text>
              <Switch value={!!gauge.ignored} onValueChange={ignored => setDetectedGauges(current => current.map((item, i) => i === index ? { ...item, ignored } : item))} />
            </View>
            {!gauge.ignored && <View style={styles.thresholdRow}>
              <TextInput style={[styles.input, styles.thresholdInput]} value={gauge.lowText} onChangeText={v => updateGauge(index, 'lowText', v)} keyboardType="decimal-pad" placeholder="Low threshold" placeholderTextColor={colors.muted} />
              <TextInput style={[styles.input, styles.thresholdInput]} value={gauge.criticalText} onChangeText={v => updateGauge(index, 'criticalText', v)} keyboardType="decimal-pad" placeholder="Critical threshold" placeholderTextColor={colors.muted} />
            </View>}
          </View>
        ))}
        {detectedGauges.length > 0 && <TouchableOpacity style={styles.saveBtn} onPress={handleRegisterDevice} disabled={savingDevice}>
          <Text style={styles.saveBtnText}>{savingDevice ? 'Saving panel…' : 'Save registered panel'}</Text>
        </TouchableOpacity>}
        <Text style={styles.metaText}>{source.mode === 'postgres' ? 'Registered panels, readings, and acknowledgement reports are saved in PostgreSQL through the monitoring backend.' : 'Demo mode stores registered panels on this device in AsyncStorage. Sign in to connect to the shared PostgreSQL backend.'}</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionHeader}>Alert delivery</Text>
        <Text style={styles.metaText}>Alerts are read from PostgreSQL while the app is open. Background push notifications are not configured.</Text>
      </View>
    </ScrollView>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  scroll: {
    padding: 14,
    backgroundColor: colors.page,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: colors.grid,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  sectionHeader: {
    fontSize: 15,
    fontWeight: '800',
    color: colors.ink,
    marginBottom: 8,
  },
  emailText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.ink2,
  },
  metaText: {
    fontSize: 12,
    color: colors.ink2,
    marginTop: 2,
  },
  signOutBtn: {
    marginTop: 12,
    backgroundColor: colors.criticalLight,
    paddingVertical: 8,
    borderRadius: 6,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.criticalBorder,
  },
  signOutBtnText: {
    color: colors.critical,
    fontWeight: '700',
    fontSize: 12,
  },
  inputLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.ink2,
    marginTop: 6,
    marginBottom: 4,
  },
  input: {
    backgroundColor: colors.borderLight,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 13,
    color: colors.ink,
    borderWidth: 1,
    borderColor: colors.grid,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
  },
  saveBtn: {
    flex: 1,
    backgroundColor: colors.ink, // Mirroring dashboard primary button
    paddingVertical: 8,
    borderRadius: 6,
    alignItems: 'center',
  },
  saveBtnText: {
    color: colors.surface,
    fontWeight: '700',
    fontSize: 12,
  },
  testBtn: {
    flex: 1,
    backgroundColor: colors.surface,
    paddingVertical: 8,
    borderRadius: 6,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.grid,
  },
  testBtnText: {
    color: colors.ink,
    fontWeight: '700',
    fontSize: 12,
  },
  connectionText: {
    marginTop: 8,
    color: colors.ink2,
    fontSize: 12,
  },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 14,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  switchLabelWrap: {
    flex: 1,
    marginRight: 10,
  },
  switchTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
  },
  switchSubtitle: {
    fontSize: 11,
    color: colors.ink2,
    marginTop: 2,
  },
  registrationPreview: { width: '100%', height: 190, borderRadius: 10, marginTop: 10, backgroundColor: colors.borderLight },
  gaugeDraft: { backgroundColor: colors.page, borderColor: colors.grid, borderWidth: 1, borderRadius: 10, padding: 11, marginTop: 10 },
  gaugeTitle: { fontSize: 14, fontWeight: '800', color: colors.ink, marginBottom: 4 },
  thresholdRow: { flexDirection: 'row', gap: 8, marginTop: 9 },
  ignoreRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 },
  thresholdInput: { flex: 1, minWidth: 120 },
});
