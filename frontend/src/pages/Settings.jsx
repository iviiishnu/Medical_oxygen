/**
 * pages/Settings.jsx
 * ==================
 * Settings page — four cards:
 *   1. Profile (name, username, email, role badge, change password, sign out)
 *   2. System status (WebSocket, backend, tablet summary, last data, version)
 *   3. Notification settings (alert sound + browser notifications, stored in localStorage)
 *   4. User management (admin only — table, add modal, role/status controls)
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../hooks/useAuth';
import {
  changePassword, getUsers, createUser, patchUser, getSummary,
} from '../api/portal';
import {
  User as UserIcon, Bell, Server, Users as UsersIcon,
  Activity, Volume2, LogOut, Plus, X, Shield,
  Wifi, WifiOff, Clock, AlertTriangle, CheckCircle, BellRing,
} from 'lucide-react';
import { Skeleton } from '../components/ui/Skeleton';
import { Toggle } from '../components/ui/Toggle';

// ── Constants ────────────────────────────────────────────────────────────────
const CARD = { boxShadow: '0 4px 24px rgba(80,110,180,0.08)' };
const APP_VERSION = '2.0.0';
const SOUND_KEY   = 'medigas_notif_sound';
const BROWSER_KEY = 'medigas_notif_browser';

// ── Helpers ──────────────────────────────────────────────────────────────────
function safeDate(raw) {
  if (!raw) return null;
  const d = raw instanceof Date ? raw : new Date(raw);
  return isNaN(d.getTime()) ? null : d;
}

function timeAgo(raw) {
  const d = safeDate(raw);
  if (!d) return '—';
  const diff = Date.now() - d.getTime();
  if (diff < 0) return 'just now';
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ── Role badge ────────────────────────────────────────────────────────────────
const ROLE_STYLES = {
  ADMINISTRATOR:    { bg: '#EFF6FF', color: '#2563EB', label: 'Administrator' },
  MONITORING_STAFF: { bg: '#F0FDF4', color: '#16A34A', label: 'Monitoring Staff' },
  VIEWER:           { bg: '#F4F7FC', color: '#8A94A6', label: 'Viewer' },
};

function RoleBadge({ role }) {
  const cfg = ROLE_STYLES[role] || { bg: '#F4F7FC', color: '#8A94A6', label: role || '—' };
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold"
      style={{ background: cfg.bg, color: cfg.color }}>
      {cfg.label}
    </span>
  );
}

// ── Local toast ──────────────────────────────────────────────────────────────
function LocalToast({ toast, onDismiss }) {
  if (!toast) return null;
  const cfg = {
    success: { bg: '#F0FDF4', border: '#BBF7D0', text: '#166534', Icon: CheckCircle, iconColor: 'text-green-500' },
    danger:  { bg: '#FEF2F2', border: '#FECACA', text: '#991B1B', Icon: AlertTriangle, iconColor: 'text-red-500' },
    info:    { bg: '#EFF6FF', border: '#BFDBFE', text: '#1E40AF', Icon: Bell, iconColor: 'text-blue-500' },
  };
  const c = cfg[toast.type] || cfg.danger;
  const { Icon } = c;
  return (
    <div className="fixed bottom-6 right-6 z-[80] flex items-center gap-3 px-4 py-3 rounded-2xl border shadow-xl max-w-sm toast-in"
      style={{ background: c.bg, borderColor: c.border }}>
      <Icon size={15} className={c.iconColor + ' shrink-0'} />
      <p className="text-xs font-semibold flex-1" style={{ color: c.text }}>{toast.message}</p>
      <button onClick={onDismiss} className="text-muted hover:text-navy shrink-0">
        <X size={14} />
      </button>
    </div>
  );
}

// ── Play beep (unconditional, for test button) ───────────────────────────────
function playTestBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.4);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.4);
  } catch { /* AudioContext unavailable */ }
}

// ── 1. Profile card ──────────────────────────────────────────────────────────
function ProfileCard({ onToast, onLogout }) {
  const { user, role } = useAuth();
  const [form, setForm] = useState({ current: '', next: '', confirm: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    if (form.next.length < 8) { setError('New password must be at least 8 characters'); return; }
    if (form.next !== form.confirm) { setError('Passwords do not match'); return; }
    setSaving(true);
    try {
      await changePassword(form.current, form.next);
      setForm({ current: '', next: '', confirm: '' });
      onToast('success', 'Password changed successfully');
    } catch (e) {
      setError(e.message || 'Failed to change password');
    } finally {
      setSaving(false);
    }
  }

  function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

  return (
    <div className="bg-white rounded-2xl p-5 flex flex-col gap-4" style={CARD}>
      <div className="flex items-center gap-2">
        <UserIcon size={16} className="text-primary" />
        <h2 className="text-sm font-semibold text-navy">Profile</h2>
      </div>

      {/* User info */}
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center shrink-0">
          <UserIcon size={20} className="text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-bold text-navy truncate">{user?.name || '—'}</p>
            <RoleBadge role={role} />
          </div>
          <p className="text-xs text-muted mt-0.5">@{user?.username || '—'}</p>
          {user?.email && <p className="text-xs text-muted truncate">{user.email}</p>}
        </div>
      </div>

      {/* Change password form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <p className="text-xs font-semibold text-navy">Change Password</p>
        {error && (
          <p className="text-[11px] text-red-600 flex items-center gap-1.5">
            <AlertTriangle size={11} /> {error}
          </p>
        )}
        <input type="password" placeholder="Current password" value={form.current}
          onChange={e => set('current', e.target.value)} className="inp" required autoComplete="current-password" />
        <input type="password" placeholder="New password (min 8 chars)" value={form.next}
          onChange={e => set('next', e.target.value)} className="inp" required autoComplete="new-password" />
        <input type="password" placeholder="Confirm new password" value={form.confirm}
          onChange={e => set('confirm', e.target.value)} className="inp" required autoComplete="new-password" />
        <button type="submit" disabled={saving}
          className="self-start px-4 py-2 rounded-xl text-xs font-semibold text-white disabled:opacity-60"
          style={{ background: '#2F80ED' }}>
          {saving ? 'Saving…' : 'Change password'}
        </button>
      </form>

      {/* Sign out */}
      <div className="pt-2 border-t border-slate-100">
        <button onClick={onLogout}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-colors hover:bg-red-50"
          style={{ color: '#EF4444' }}>
          <LogOut size={14} /> Sign out
        </button>
      </div>
    </div>
  );
}

// ── 3. Notifications card ─────────────────────────────────────────────────────
function NotificationsCard() {
  const [soundOn, setSoundOn] = useState(() => {
    try { return localStorage.getItem(SOUND_KEY) !== 'off'; } catch { return true; }
  });
  const [browserOn, setBrowserOn] = useState(() => {
    try { return localStorage.getItem(BROWSER_KEY) === 'on'; } catch { return false; }
  });

  function toggleSound(v) {
    setSoundOn(v);
    try { localStorage.setItem(SOUND_KEY, v ? 'on' : 'off'); } catch {}
  }

  function toggleBrowser(v) {
    if (v && typeof Notification !== 'undefined') {
      if (Notification.permission === 'denied') return; // Can't re-request after denial
      if (Notification.permission !== 'granted') {
        Notification.requestPermission().then(perm => {
          const allowed = perm === 'granted';
          setBrowserOn(allowed);
          try { localStorage.setItem(BROWSER_KEY, allowed ? 'on' : 'off'); } catch {}
        });
        return;
      }
    }
    setBrowserOn(v);
    try { localStorage.setItem(BROWSER_KEY, v ? 'on' : 'off'); } catch {}
  }

  return (
    <div className="bg-white rounded-2xl p-5 flex flex-col gap-4" style={CARD}>
      <div className="flex items-center gap-2">
        <Bell size={16} className="text-primary" />
        <h2 className="text-sm font-semibold text-navy">Notification Settings</h2>
      </div>

      {/* Alert sound toggle */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <Volume2 size={16} className="text-muted shrink-0" />
          <div>
            <p className="text-xs font-semibold text-navy">Alert sound</p>
            <p className="text-[10px] text-muted">Beep when a new active alert arrives</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={playTestBeep}
            className="px-3 py-1.5 rounded-xl text-[10px] font-semibold text-primary bg-blue-50 hover:bg-blue-100 transition-colors">
            Test sound
          </button>
          <Toggle checked={soundOn} onChange={toggleSound} />
        </div>
      </div>

      {/* Browser notifications toggle */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <BellRing size={16} className="text-muted shrink-0" />
          <div>
            <p className="text-xs font-semibold text-navy">Browser notifications</p>
            <p className="text-[10px] text-muted">System notification for critical alerts</p>
          </div>
        </div>
        <Toggle checked={browserOn} onChange={toggleBrowser} />
      </div>
    </div>
  );
}

// ── 4. System status card ────────────────────────────────────────────────────
function SystemStatusCard({ wsConnected, summary, lastDataAt }) {
  const [backendOk, setBackendOk] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getSummary().then(() => { if (!cancelled) setBackendOk(true); })
      .catch(() => { if (!cancelled) setBackendOk(false); });
    return () => { cancelled = true; };
  }, [lastDataAt]);

  const devStats = summary?.devices || {};

  const items = [
    {
      label: 'Portal connection (WebSocket)',
      value: wsConnected ? 'Connected' : 'Disconnected',
      ok: wsConnected,
      Icon: wsConnected ? Wifi : WifiOff,
      color: wsConnected ? '#16A34A' : '#EF4444',
    },
    {
      label: 'Backend (GET /api/summary)',
      value: backendOk === null ? 'Checking…' : backendOk ? 'OK' : 'Unreachable',
      ok: backendOk === true,
      Icon: Server,
      color: backendOk === false ? '#EF4444' : '#16A34A',
    },
    {
      label: 'Tablet status summary',
      value: `Normal ${devStats.normal ?? 0} · Critical ${devStats.critical ?? 0} · Offline ${devStats.offline ?? 0}`,
      ok: (devStats.critical ?? 0) === 0,
      Icon: Shield,
      color: '#2F80ED',
    },
    {
      label: 'Last data received',
      value: lastDataAt ? timeAgo(lastDataAt) : '—',
      ok: true,
      Icon: Clock,
      color: '#8A94A6',
    },
    {
      label: 'App version',
      value: `v${APP_VERSION}`,
      ok: true,
      Icon: Activity,
      color: '#8A94A6',
    },
  ];

  return (
    <div className="bg-white rounded-2xl p-5 flex flex-col gap-4 flex-1" style={CARD}>
      <div className="flex items-center gap-2">
        <Server size={16} className="text-primary" />
        <h2 className="text-sm font-semibold text-navy">System Status</h2>
      </div>

      <div className="flex flex-col gap-3 flex-1 justify-center">
        {items.map((item, i) => {
          const { Icon } = item;
          return (
            <div key={i} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5 min-w-0">
                <Icon size={14} className="shrink-0" style={{ color: item.color }} />
                <p className="text-xs text-muted truncate">{item.label}</p>
              </div>
              <span className="text-xs font-semibold text-navy text-right shrink-0">{item.value}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── 5. User management card (admin only) ─────────────────────────────────────
function AddUserModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ username: '', name: '', email: '', password: '', role: 'VIEWER' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const ref = useRef(null);

  useEffect(() => { ref.current?.focus(); }, []);
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const created = await createUser({
        username: form.username.trim(),
        name: form.name.trim(),
        email: form.email.trim() || null,
        password: form.password,
        role: form.role,
      });
      onCreated(created);
    } catch (e) {
      setError(e.message || 'Failed to create user');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div className="relative bg-white rounded-2xl w-full max-w-md flex flex-col"
        style={{ boxShadow: '0 20px 60px rgba(0,0,0,0.20)' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 shrink-0">
          <h3 className="text-sm font-bold text-navy">Add User</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted hover:bg-slate-100 hover:text-navy">
            <X size={16} />
          </button>
        </div>

        <form id="add-user-form" onSubmit={handleSubmit}
          className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3">
          {error && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {error}
            </div>
          )}
          <Field label="Username *">
            <input ref={ref} value={form.username} onChange={e => set('username', e.target.value)}
              placeholder="e.g. j.doe" className="inp" required autoComplete="off" />
          </Field>
          <Field label="Full name *">
            <input value={form.name} onChange={e => set('name', e.target.value)}
              placeholder="e.g. Jane Doe" className="inp" required />
          </Field>
          <Field label="Email">
            <input type="email" value={form.email} onChange={e => set('email', e.target.value)}
              placeholder="jane@hospital.gov" className="inp" />
          </Field>
          <Field label="Password *">
            <input type="password" value={form.password} onChange={e => set('password', e.target.value)}
              className="inp" required />
          </Field>
          <Field label="Role">
            <select value={form.role} onChange={e => set('role', e.target.value)} className="inp">
              <option value="ADMINISTRATOR">Administrator</option>
              <option value="MONITORING_STAFF">Monitoring Staff</option>
              <option value="VIEWER">Viewer</option>
            </select>
          </Field>
        </form>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-4 border-t border-slate-100 shrink-0">
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-muted hover:bg-slate-100 transition-colors">
            Cancel
          </button>
          <button type="submit" form="add-user-form" disabled={saving}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white disabled:opacity-60"
            style={{ background: '#2F80ED' }}>
            {saving ? 'Creating…' : 'Create user'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-semibold text-navy">{label}</label>
      {children}
    </div>
  );
}

function UserManagementCard({ onToast }) {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getUsers();
      setUsers(data || []);
    } catch (e) {
      onToast('danger', e.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, [onToast]);

  useEffect(() => { load(); }, [load]);

  async function handleRoleChange(u, newRole) {
    if (u.role === newRole) return;
    try {
      await patchUser(u.id, { role: newRole });
      onToast('success', `Role updated for ${u.username}`);
      load();
    } catch (e) {
      onToast('danger', e.message || 'Failed to update role');
    }
  }

  async function handleToggleActive(u) {
    try {
      await patchUser(u.id, { is_active: !u.is_active });
      onToast('success', `${u.username} ${u.is_active ? 'deactivated' : 'activated'}`);
      load();
    } catch (e) {
      onToast('danger', e.message || 'Failed to update status');
    }
  }

  return (
    <div className="bg-white rounded-2xl p-5 flex flex-col gap-4" style={CARD}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <UsersIcon size={16} className="text-primary" />
          <h2 className="text-sm font-semibold text-navy">User Management</h2>
        </div>
        <button onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white"
          style={{ background: '#2F80ED' }}>
          <Plus size={13} /> Add user
        </button>
      </div>

      {loading ? (
        <div className="flex flex-col gap-2">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-12" />)}
        </div>
      ) : users && users.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="py-2 pr-3 text-[10px] font-bold uppercase tracking-widest text-muted">Name</th>
                <th className="py-2 pr-3 text-[10px] font-bold uppercase tracking-widest text-muted">Username</th>
                <th className="py-2 pr-3 text-[10px] font-bold uppercase tracking-widest text-muted">Role</th>
                <th className="py-2 pr-3 text-[10px] font-bold uppercase tracking-widest text-muted">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {users.map(u => {
                const isSelf = u.id === currentUser?.id;
                return (
                  <tr key={u.id} className="hover:bg-slate-50/50">
                    <td className="py-2.5 pr-3 text-xs font-semibold text-navy">{u.name}</td>
                    <td className="py-2.5 pr-3 text-xs text-muted">@{u.username}</td>
                    <td className="py-2.5 pr-3">
                      <select
                        value={u.role}
                        onChange={e => handleRoleChange(u, e.target.value)}
                        disabled={isSelf}
                        className="text-[10px] rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 outline-none focus:border-blue-400 disabled:opacity-50"
                      >
                        <option value="ADMINISTRATOR">Administrator</option>
                        <option value="MONITORING_STAFF">Monitoring Staff</option>
                        <option value="VIEWER">Viewer</option>
                      </select>
                    </td>
                    <td className="py-2.5 pr-3">
                      <Toggle
                        checked={u.is_active}
                        onChange={() => handleToggleActive(u)}
                        disabled={isSelf}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted text-center py-4">No users found.</p>
      )}

      {showAdd && (
        <AddUserModal
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            setShowAdd(false);
            onToast('success', 'User created');
            load();
          }}
        />
      )}
    </div>
  );
}

// ── Main Settings component ─────────────────────────────────────────────────
export default function Settings({ wsConnected = false, summary = null }) {
  const { role, logout } = useAuth();
  const isAdmin = role === 'ADMINISTRATOR';
  const [toast, setToast] = useState(null);

  function showToast(type, message) {
    const id = Date.now();
    setToast({ id, type, message });
    setTimeout(() => setToast(null), 4000);
  }

  return (
    <>
      <style>{`
        .inp {
          width: 100%;
          padding: 8px 12px;
          font-size: 13px;
          border-radius: 12px;
          border: 1px solid #E2E8F0;
          background: #F8FAFF;
          outline: none;
        }
        .inp:focus { border-color: #60A5FA; }
      `}</style>

      <div className="p-5 flex flex-col gap-5 page-fade-in">
        {/* Page title */}
        <div>
          <h1 className="text-lg font-bold text-navy">Settings</h1>
          <p className="text-xs text-muted mt-0.5">Manage your profile, preferences, and system</p>
        </div>

        {/* Two-column grid with equal heights */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-stretch">
          {/* Left column: Profile only */}
          <div className="flex flex-col">
            <ProfileCard onToast={showToast} onLogout={logout} />
          </div>
          {/* Right column: System status then Notification settings */}
          <div className="flex flex-col gap-5 flex-1">
            <SystemStatusCard wsConnected={wsConnected} summary={summary} lastDataAt={null} />
            <NotificationsCard />
          </div>
        </div>

        {/* Full-width: User management (admin only) */}
        {isAdmin && <UserManagementCard onToast={showToast} />}
      </div>

      <LocalToast toast={toast} onDismiss={() => setToast(null)} />
    </>
  );
}
