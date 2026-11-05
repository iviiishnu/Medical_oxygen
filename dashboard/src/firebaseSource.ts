import { initializeApp } from 'firebase/app';
import { getAuth, onAuthStateChanged, signInWithEmailAndPassword, type User } from 'firebase/auth';
import {
  collection, doc, getFirestore, limit, onSnapshot, orderBy, query, serverTimestamp, Timestamp, updateDoc, where,
} from 'firebase/firestore';
import type { Alert, Device, Point } from './logic.ts';
import type { DataSource } from './source.ts';

const ms = (t: unknown): number | null => (t instanceof Timestamp ? t.toMillis() : null);

export function firebaseSource(cfg: Record<string, string>): DataSource {
  const app = initializeApp(cfg);
  const auth = getAuth(app);
  const db = getFirestore(app);
  let user: User | null = auth.currentUser;
  onAuthStateChanged(auth, u => { user = u; });

  return {
    mode: 'firebase',
    signedIn: () => user != null,
    userName: () => user?.email ?? '',
    async signIn(email, password) {
      const r = await signInWithEmailAndPassword(auth, email, password);
      user = r.user;
      await r.user.getIdToken(true);
    },
    onDevices(cb) {
      return onSnapshot(collection(db, 'devices'), snap => {
        cb(snap.docs.map(d => {
          const x = d.data();
          const lr = x.last_reading ?? {};
          const c = x.config ?? {};
          return {
            id: d.id, name: x.name ?? d.id,
            value: typeof lr.smoothed === 'number' ? lr.smoothed : typeof lr.value === 'number' ? lr.value : null,
            unit: lr.unit ?? 'kg/cm2', status: x.status ?? 'UNKNOWN', alarm: x.alarm ?? 'OK',
            trendFalling: !!x.trend_falling, lastHeartbeatMs: ms(x.last_heartbeat), online: x.online !== false,
            battery: typeof x.battery === 'number' ? x.battery : null,
            lowThreshold: c.low_threshold ?? 3.5, criticalThreshold: c.critical_threshold ?? 3.0,
          } satisfies Device;
        }).sort((a, b) => a.name.localeCompare(b.name)));
      }, err => console.error('devices', err));
    },
    onAlerts(cb) {
      const since = Timestamp.fromMillis(Date.now() - 24 * 3600_000);
      const q = query(collection(db, 'alerts'), where('created_at', '>', since), orderBy('created_at', 'desc'), limit(300));
      return onSnapshot(q, snap => {
        cb(snap.docs.map(d => {
          const x = d.data();
          return {
            id: d.id, type: x.type, state: x.state, deviceId: x.device_id ?? '', value: x.value ?? null,
            unit: x.unit ?? 'kg/cm2', createdMs: ms(x.created_at), ackedBy: x.acked_by_name ?? null,
            ackedMs: ms(x.acked_at), resolvedMs: ms(x.resolved_at), escalationLevel: x.escalation_level ?? 0,
          } satisfies Alert;
        }));
      }, err => console.error('alerts', err));
    },
    onHistory(deviceId, cb) {
      const since = Timestamp.fromMillis(Date.now() - 24 * 3600_000);
      const q = query(collection(db, 'devices', deviceId, 'readings'), where('server_ts', '>', since),
        orderBy('server_ts', 'asc'), limit(3000));
      return onSnapshot(q, snap => {
        cb(snap.docs.map(d => {
          const x = d.data();
          const v = typeof x.smoothed === 'number' ? x.smoothed : typeof x.value === 'number' ? x.value : null;
          return { t: ms(x.server_ts) ?? Date.parse(x.ts), v, status: x.status ?? 'OK' } satisfies Point;
        }));
      }, err => console.error('history', err));
    },
    async acknowledge(alertId) {
      if (!user) throw new Error('not signed in');
      await updateDoc(doc(db, 'alerts', alertId), {
        state: 'ACKED', acked_by: user.uid, acked_by_name: user.email ?? 'desk', acked_at: serverTimestamp(),
      });
    },
  };
}
