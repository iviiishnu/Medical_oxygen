import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import type { DataSource } from '../../api/dataSource';
import type { Incident, IncidentStatus } from '../../types/monitoring';
import { useMonitoring } from '../../hooks/useMonitoring';
import { useResponsive } from '../../hooks/useResponsive';
import { useThemeColors } from '../../theme/ThemeContext';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';

interface Props { source: DataSource; initialAlertId?: string; onInitialAlertHandled?: () => void; }

export const IncidentsScreen: React.FC<Props> = ({ source, initialAlertId, onInitialAlertHandled }) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const { isTablet, isLandscape } = useResponsive();
  const { devices, alerts } = useMonitoring(source);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [possibleCause, setPossibleCause] = useState('');
  const [actionTaken, setActionTaken] = useState('');
  const [assignedTo, setAssignedTo] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [alertId, setAlertId] = useState('');
  const [updateNote, setUpdateNote] = useState('');
  const [updateAction, setUpdateAction] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => source.onIncidents(setIncidents), [source]);
  useEffect(() => {
    if (!initialAlertId) return;
    const alert = alerts.find(item => item.id === initialAlertId);
    if (!alert) return;
    setAlertId(alert.id);
    setDeviceId(alert.deviceId);
    onInitialAlertHandled?.();
  }, [initialAlertId, alerts, onInitialAlertHandled]);
  const selected = incidents.find(item => item.id === selectedId) ?? incidents[0] ?? null;
  const activeIncidents = useMemo(() => incidents.filter(i => i.status !== 'CLOSED'), [incidents]);

  const create = async () => {
    if (!title.trim() || !description.trim()) { setError('Enter an incident title and brief description.'); return; }
    setBusy(true); setError('');
    try {
      await source.createIncident({ title, description, deviceId: deviceId || undefined, alertId: alertId || undefined,
        possibleCause: possibleCause || undefined, actionTaken: actionTaken || undefined, assignedTo: assignedTo || undefined });
      setTitle(''); setDescription(''); setPossibleCause(''); setActionTaken(''); setAssignedTo(''); setAlertId('');
      setError('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not create the incident.'); }
    finally { setBusy(false); }
  };

  const update = async (status?: IncidentStatus) => {
    if (!selected) return;
    if (!updateNote.trim()) { setError('Add a short note to record this update.'); return; }
    setBusy(true); setError('');
    try {
      await source.updateIncident(selected.id, { status, note: updateNote, actionTaken: updateAction || undefined });
      setUpdateNote(''); setUpdateAction('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not update the incident.'); }
    finally { setBusy(false); }
  };

  const field = (value: string, set: (v: string) => void, placeholder: string, multiline = false) => (
    <TextInput value={value} onChangeText={set} placeholder={placeholder} placeholderTextColor={colors.muted}
      multiline={multiline} style={[styles.input, multiline && styles.multiline]} />
  );
  const createPane = (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Record an incident</Text>
      <Text style={styles.hint}>Link an alert or device and record the cause and corrective action.</Text>
      {field(title, setTitle, 'Incident title')}
      <Text style={styles.label}>Related device</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
        <TouchableOpacity onPress={() => setDeviceId('')} style={[styles.chip, !deviceId && styles.chipActive]}><Text style={[styles.chipText, !deviceId && styles.chipTextActive]}>None</Text></TouchableOpacity>
        {devices.map(d => <TouchableOpacity key={d.id} onPress={() => { setDeviceId(d.id); setAlertId(''); }} style={[styles.chip, deviceId === d.id && styles.chipActive]}><Text style={[styles.chipText, deviceId === d.id && styles.chipTextActive]}>{d.name}</Text></TouchableOpacity>)}
      </ScrollView>
      {deviceId ? <>
        <Text style={styles.label}>Related alert (optional)</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
          <TouchableOpacity onPress={() => setAlertId('')} style={[styles.chip, !alertId && styles.chipActive]}><Text style={[styles.chipText, !alertId && styles.chipTextActive]}>None</Text></TouchableOpacity>
          {alerts.filter(a => a.deviceId === deviceId).map(a => <TouchableOpacity key={a.id} onPress={() => setAlertId(a.id)} style={[styles.chip, alertId === a.id && styles.chipActive]}><Text style={[styles.chipText, alertId === a.id && styles.chipTextActive]}>{a.type} · {a.value ?? '—'} {a.unit}</Text></TouchableOpacity>)}
        </ScrollView>
      </> : null}
      {field(description, setDescription, 'What happened?', true)}
      {field(possibleCause, setPossibleCause, 'Possible cause (optional)')}
      <View style={styles.chips}>{['Supply interruption', 'Empty cylinder', 'Regulator/valve fault', 'Gauge/sensor fault', 'Accidental isolation', 'Maintenance'].map(option => <TouchableOpacity key={option} onPress={() => setPossibleCause(option)} style={[styles.chip, possibleCause === option && styles.chipActive]}><Text style={[styles.chipText, possibleCause === option && styles.chipTextActive]}>{option}</Text></TouchableOpacity>)}</View>
      {field(actionTaken, setActionTaken, 'Action taken (optional)', true)}
      <View style={styles.chips}>{['Switched to backup supply', 'Replaced cylinder', 'Reset/repaired regulator', 'Reconnected sensor', 'Escalated to maintenance'].map(option => <TouchableOpacity key={option} onPress={() => setActionTaken(option)} style={[styles.chip, actionTaken === option && styles.chipActive]}><Text style={[styles.chipText, actionTaken === option && styles.chipTextActive]}>{option}</Text></TouchableOpacity>)}</View>
      {field(assignedTo, setAssignedTo, 'Assigned to (optional)')}
      <TouchableOpacity style={styles.primaryButton} onPress={create} disabled={busy}>
        {busy ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.primaryText}>Create incident</Text>}
      </TouchableOpacity>
    </View>
  );

  const detailPane = (
    <View style={styles.card}>
      <View style={styles.detailHeading}>
        <Text style={styles.sectionTitle}>Incident details</Text>
        {selected && <Text style={styles.status}>{selected.status.replace('_', ' ')}</Text>}
      </View>
      {!selected ? <Text style={styles.hint}>Choose an incident to view its timeline and add updates.</Text> : <>
        <Text style={styles.incidentTitle}>{selected.title}</Text>
        <Text style={styles.hint}>{selected.deviceId ?? 'No device'}{selected.alertId ? ` · Alert ${selected.alertId.slice(0, 8)}` : ''} · {new Date(selected.createdMs).toLocaleString()}</Text>
        <Text style={styles.bodyText}>{selected.description}</Text>
        {!!selected.possibleCause && <Text style={styles.bodyText}>Possible cause: {selected.possibleCause}</Text>}
        {!!selected.actionTaken && <Text style={styles.bodyText}>Corrective action: {selected.actionTaken}</Text>}
        {!!selected.assignedTo && <Text style={styles.hint}>Assigned to {selected.assignedTo}</Text>}
        <Text style={styles.label}>Update timeline</Text>
        {selected.updates.map(u => <View key={u.id} style={styles.updateRow}>
          <Text style={styles.updateMeta}>{new Date(u.createdMs).toLocaleString()} · {u.author}{u.status ? ` · ${u.status.replace('_', ' ')}` : ''}</Text>
          <Text style={styles.bodyText}>{u.note}</Text>
          {!!u.actionTaken && <Text style={styles.hint}>Action: {u.actionTaken}</Text>}
        </View>)}
        {selected.status !== 'CLOSED' ? <>
          {field(updateNote, setUpdateNote, 'Update note', true)}
          {field(updateAction, setUpdateAction, 'Corrective action (optional)', true)}
          <View style={styles.actions}>
            <TouchableOpacity style={styles.secondaryButton} onPress={() => void update('IN_PROGRESS')} disabled={busy}><Text style={styles.secondaryText}>Mark in progress</Text></TouchableOpacity>
            <TouchableOpacity style={styles.primaryButton} onPress={() => void update('CLOSED')} disabled={busy}><Text style={styles.primaryText}>Close incident</Text></TouchableOpacity>
            {selected.status !== 'OPEN' && <TouchableOpacity style={styles.secondaryButton} onPress={() => void update('OPEN')} disabled={busy}><Text style={styles.secondaryText}>Reopen</Text></TouchableOpacity>}
            <TouchableOpacity style={styles.secondaryButton} onPress={() => void update()} disabled={busy}><Text style={styles.secondaryText}>Add note</Text></TouchableOpacity>
          </View>
        </> : <>
          {field(updateNote, setUpdateNote, 'Add a note before reopening', true)}
          <TouchableOpacity style={styles.secondaryButton} onPress={() => void update('OPEN')} disabled={busy}><Text style={styles.secondaryText}>Reopen incident</Text></TouchableOpacity>
        </>}
      </>}
    </View>
  );

  return <ScrollView contentContainerStyle={styles.page}>
    <View style={styles.header}><Text style={styles.title}>Incidents</Text><Text style={styles.hint}>{activeIncidents.length} open or in progress · {incidents.filter(i => i.status === 'CLOSED').length} closed</Text></View>
    {!!error && <Text style={styles.error}>{error}</Text>}
    <View style={[styles.content, isTablet && isLandscape && styles.contentWide]}>
      <View style={[styles.column, isTablet && isLandscape && styles.sideColumn]}>
        {createPane}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Incident log</Text>
          {!incidents.length ? <Text style={styles.hint}>No incidents recorded yet.</Text> : incidents.map(i => <TouchableOpacity key={i.id} onPress={() => setSelectedId(i.id)} style={[styles.listItem, selected?.id === i.id && styles.listItemSelected]}>
            <View style={styles.detailHeading}><Text style={styles.incidentTitle} numberOfLines={1}>{i.title}</Text><Text style={styles.status}>{i.status.replace('_', ' ')}</Text></View>
            <Text style={styles.hint}>{i.deviceId ?? 'No device'} · {new Date(i.updatedMs).toLocaleString()}</Text>
          </TouchableOpacity>)}
        </View>
      </View>
      <View style={styles.column}>{detailPane}</View>
    </View>
  </ScrollView>;
};

const createStyles = (c: ThemePalette) => StyleSheet.create({
  page: { flexGrow: 1, padding: 16, gap: 12, backgroundColor: c.page },
  header: { gap: 3 }, title: { fontSize: 24, fontWeight: '800', color: c.ink },
  content: { gap: 12 }, contentWide: { flexDirection: 'row', alignItems: 'flex-start' }, column: { flex: 1, gap: 12 }, sideColumn: { flex: 0.9 },
  card: { backgroundColor: c.surface, borderColor: c.border, borderWidth: 1, borderRadius: 14, padding: 14, gap: 9 },
  sectionTitle: { color: c.ink, fontSize: 16, fontWeight: '800' }, hint: { color: c.ink2, fontSize: 12, lineHeight: 18 }, label: { color: c.ink, fontSize: 12, fontWeight: '700', marginTop: 3 },
  input: { minHeight: 42, borderWidth: 1, borderColor: c.grid, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, color: c.ink, backgroundColor: c.page, fontSize: 13 }, multiline: { minHeight: 72, textAlignVertical: 'top' },
  chips: { flexDirection: 'row', gap: 7 }, chip: { borderRadius: 18, borderWidth: 1, borderColor: c.grid, paddingHorizontal: 11, paddingVertical: 7 }, chipActive: { backgroundColor: c.series, borderColor: c.series }, chipText: { color: c.ink2, fontSize: 11, fontWeight: '600' }, chipTextActive: { color: '#fff' },
  primaryButton: { minHeight: 40, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 12, backgroundColor: c.series, borderRadius: 8 }, primaryText: { color: '#fff', fontWeight: '700', fontSize: 12 }, secondaryButton: { minHeight: 38, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 10, borderWidth: 1, borderColor: c.grid, borderRadius: 8 }, secondaryText: { color: c.ink, fontWeight: '700', fontSize: 11 }, actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  detailHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }, status: { color: c.series, fontSize: 10, fontWeight: '800' }, incidentTitle: { flex: 1, color: c.ink, fontSize: 14, fontWeight: '800' }, bodyText: { color: c.ink, fontSize: 13, lineHeight: 19 }, updateRow: { borderLeftWidth: 2, borderLeftColor: c.series, paddingLeft: 9, gap: 3 }, updateMeta: { color: c.muted, fontSize: 10 }, listItem: { paddingVertical: 9, borderTopWidth: 1, borderTopColor: c.grid, gap: 3 }, listItemSelected: { backgroundColor: c.borderLight, paddingHorizontal: 8, borderRadius: 8 }, error: { color: c.critical, fontSize: 12, lineHeight: 18 },
});
