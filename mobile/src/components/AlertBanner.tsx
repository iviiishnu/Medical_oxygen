import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Modal, TextInput, ScrollView } from 'react-native';
import type { Alert, AlertAckReport } from '../types/monitoring';
import { StatusBadge } from './StatusBadge';
import { ago } from '../utils/logic';
import { colors as baseColors, type ThemePalette } from '../theme/colors';
import { useThemeColors } from '../theme/ThemeContext';

interface Props {
  alerts: Alert[];
  now: number;
  ackError?: string | null;
  onAcknowledge: (id: string, report: AlertAckReport) => Promise<boolean | void>;
}

const REASONS = ['Supply interruption', 'Empty cylinder', 'Regulator or valve fault', 'Gauge/sensor fault', 'Routine maintenance', 'Accidental isolation', 'Other'];
const RESOLUTIONS = ['Supply restored', 'Cylinder replaced', 'Regulator reset/repaired', 'Sensor reconnected', 'Maintenance completed', 'False alarm confirmed', 'Other'];

export const AlertBanner: React.FC<Props> = ({
  alerts,
  now,
  onAcknowledge,
  ackError,
}) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const [ackingId, setAckingId] = React.useState<string | null>(null);
  const [selectedAlert, setSelectedAlert] = React.useState<Alert | null>(null);
  const [reason, setReason] = React.useState('');
  const [resolution, setResolution] = React.useState('');
  const [notes, setNotes] = React.useState('');

  if (!alerts || alerts.length === 0) {
    return null;
  }

  const handleAck = async () => {
    const needsDetails = reason === 'Other' || resolution === 'Other';
    if (!selectedAlert || !reason || !resolution || (needsDetails && !notes.trim())) return;
    try {
      setAckingId(selectedAlert.id);
      const saved = await onAcknowledge(selectedAlert.id, { reason, resolution, notes: notes.trim() });
      if (saved === false) return;
      setSelectedAlert(null);
      setReason(''); setResolution(''); setNotes('');
    } finally {
      setAckingId(null);
    }
  };

  return (
    <View style={styles.banner}>
      {alerts.map(a => {
        const isAcking = ackingId === a.id;
        return (
          <View key={a.id} style={styles.row}>
            <View style={styles.statusCol}>
              <StatusBadge status={a.type} size="small" />
            </View>
            <View style={styles.infoCol}>
              <Text style={styles.deviceText} numberOfLines={1}>
                {a.deviceId}
              </Text>
              <Text style={styles.timeText}>
                Active since {ago(a.createdMs ?? now, now)} · {a.state}
              </Text>
            </View>
            <TouchableOpacity
              style={[styles.ackBtn, isAcking && styles.ackBtnDisabled]}
              onPress={() => setSelectedAlert(a)}
              disabled={isAcking}
              activeOpacity={0.8}
            >
              <Text style={styles.ackBtnText}>ACK</Text>
            </TouchableOpacity>
          </View>
        );
      })}
      {ackError ? <Text style={styles.errorText}>{ackError}</Text> : null}
      <Modal visible={!!selectedAlert} transparent animationType="fade" onRequestClose={() => setSelectedAlert(null)}>
        <View style={styles.modalBackdrop}>
          <ScrollView style={styles.modalCard} contentContainerStyle={styles.modalContent} keyboardShouldPersistTaps="handled">
            <Text style={styles.modalTitle}>Acknowledge alert</Text>
            <Text style={styles.modalSubtitle}>{selectedAlert?.deviceId} · {selectedAlert?.type}</Text>
            <Text style={styles.fieldLabel}>Likely reason</Text>
            <View style={styles.choiceWrap}>{REASONS.map(value => (
              <TouchableOpacity key={value} style={[styles.choice, reason === value && styles.choiceSelected]} onPress={() => setReason(value)}>
                <Text style={[styles.choiceText, reason === value && styles.choiceTextSelected]}>{value}</Text>
              </TouchableOpacity>
            ))}</View>
            <Text style={styles.fieldLabel}>How was it resolved?</Text>
            <View style={styles.choiceWrap}>{RESOLUTIONS.map(value => (
              <TouchableOpacity key={value} style={[styles.choice, resolution === value && styles.choiceSelected]} onPress={() => setResolution(value)}>
                <Text style={[styles.choiceText, resolution === value && styles.choiceTextSelected]}>{value}</Text>
              </TouchableOpacity>
            ))}</View>
            <TextInput style={styles.notesInput} value={notes} onChangeText={setNotes} placeholder="Brief notes (optional)" placeholderTextColor={colors.muted} multiline maxLength={500} />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.cancelButton} onPress={() => setSelectedAlert(null)}><Text style={styles.cancelText}>Cancel</Text></TouchableOpacity>
              <TouchableOpacity style={[styles.confirmButton, (!reason || !resolution || ((reason === 'Other' || resolution === 'Other') && !notes.trim()) || !!ackingId) && styles.confirmDisabled]} disabled={!reason || !resolution || ((reason === 'Other' || resolution === 'Other') && !notes.trim()) || !!ackingId} onPress={handleAck}>
                {ackingId ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.confirmText}>Save report & acknowledge</Text>}
              </TouchableOpacity>
            </View>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  banner: {
    backgroundColor: colors.surface,
    borderWidth: 2,
    borderColor: colors.critical, // Mirroring dashboard .banner: 2px solid var(--critical)
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginHorizontal: 12,
    marginTop: 8,
    marginBottom: 4,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 4,
    backgroundColor: colors.surface,
    borderRadius: 8,
    padding: 6,
  },
  statusCol: {
    marginRight: 8,
  },
  infoCol: {
    flex: 1,
    marginRight: 8,
  },
  deviceText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
  },
  timeText: {
    fontSize: 11,
    color: colors.ink2,
    marginTop: 2,
  },
  ackBtn: {
    backgroundColor: colors.critical,
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 8,
    minWidth: 58,
    alignItems: 'center',
  },
  ackBtnDisabled: {
    opacity: 0.6,
  },
  ackBtnText: {
    color: colors.surface,
    fontWeight: '700',
    fontSize: 12,
  },
  errorText: {
    fontSize: 11,
    color: colors.critical,
    marginTop: 4,
    textAlign: 'center',
  },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.58)', justifyContent: 'center', padding: 18 },
  modalCard: { maxHeight: '92%', backgroundColor: colors.surface, borderRadius: 18, borderWidth: 1, borderColor: colors.grid, padding: 18 },
  modalContent: { paddingBottom: 4 },
  modalTitle: { color: colors.ink, fontSize: 20, fontWeight: '800' },
  modalSubtitle: { color: colors.ink2, marginTop: 4, marginBottom: 14, fontSize: 13 },
  fieldLabel: { color: colors.ink, fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 7 },
  choiceWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  choice: { borderColor: colors.grid, borderWidth: 1, borderRadius: 18, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: colors.page },
  choiceSelected: { backgroundColor: colors.series, borderColor: colors.series },
  choiceText: { color: colors.ink2, fontSize: 12, fontWeight: '600' },
  choiceTextSelected: { color: '#fff' },
  notesInput: { minHeight: 64, maxHeight: 110, textAlignVertical: 'top', borderColor: colors.grid, borderWidth: 1, borderRadius: 9, padding: 10, color: colors.ink, backgroundColor: colors.page, marginTop: 12 },
  modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 9, marginTop: 14 },
  cancelButton: { borderColor: colors.grid, borderWidth: 1, borderRadius: 9, paddingHorizontal: 14, paddingVertical: 10 },
  cancelText: { color: colors.ink, fontWeight: '700' },
  confirmButton: { backgroundColor: colors.critical, borderRadius: 9, paddingHorizontal: 14, paddingVertical: 10, minWidth: 150, alignItems: 'center' },
  confirmDisabled: { opacity: 0.45 },
  confirmText: { color: '#fff', fontWeight: '700', fontSize: 12 },
});
