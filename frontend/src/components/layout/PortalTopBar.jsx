/**
 * PortalTopBar.jsx
 * ================
 * Top bar for the Oxygen Flow Check portal.
 * Shows: page title, system status chip, bell with active alert count,
 * user name and logout.
 */
import { useState, useEffect, useRef } from 'react';
import { Bell, ChevronDown, X, ArrowLeft } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useNavigate, useLocation } from 'react-router-dom';

const PAGE_TITLES = {
  '/':           'Dashboard',
  '/live':       'Live Monitoring',
  '/alerts':     'Alerts',
  '/incidents':  'Incident Management',
  '/analytics':  'Analytics & Reports',
  '/settings':   'Settings',
};

function deriveSystemStatus(summary) {
  if (!summary) return { label: 'Tablet: Loading…', color: '#8A94A6', bg: '#F4F7FC' };
  const { devices = {} } = summary;
  if (devices.critical > 0)
    return { label: 'Tablet: Critical', color: '#EF4444', bg: '#FEF2F2' };
  if (devices.offline > 0)
    return { label: 'Tablet: Offline',  color: '#F59E0B', bg: '#FFFBEB' };
  return   { label: 'Tablet: Normal',   color: '#22C55E', bg: '#F0FDF4' };
}

/** Summarise an alert into one short line: "2.5 kg/cm2 · oxygen" */
function alertDetail(a) {
  const gauges = a.gauges || [];
  if (gauges.length > 0) {
    const g = gauges[0];
    const parts = [];
    if (g.reading != null) parts.push(`${g.reading} ${g.unit || ''}`.trim());
    if (g.gas) parts.push(g.gas.toLowerCase());
    if (parts.length) return parts.join(' · ');
  }
  if (a.worst_status) return a.worst_status;
  return (a.alert_type || '').replace(/_/g, ' ');
}

function AlertDropdown({ alerts, onClose }) {
  const navigate = useNavigate();
  const active   = (alerts || []).slice(0, 6);

  return (
    <div className="absolute right-0 top-12 w-80 bg-white rounded-2xl z-50 overflow-hidden"
      style={{ boxShadow: '0 8px 32px rgba(80,110,180,0.18)', border: '1px solid #E8EEFA' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-50">
        <span className="text-sm font-semibold text-navy">
          Active Alerts
          {active.length > 0 && (
            <span className="ml-2 text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-red-100 text-red-600">
              {active.length}
            </span>
          )}
        </span>
        <button onClick={onClose} aria-label="Close alerts dropdown"
          className="text-muted hover:text-navy p-1 rounded-lg hover:bg-slate-50 transition-colors">
          <X size={14} />
        </button>
      </div>

      {/* Alert rows */}
      {active.length === 0
        ? <p className="px-4 py-8 text-sm text-muted text-center">No active alerts</p>
        : (
          <ul className="divide-y divide-slate-50 max-h-64 overflow-y-auto">
            {active.map(a => (
              <li key={a.id}
                className="px-4 py-3 hover:bg-slate-50 transition-colors cursor-pointer"
                onClick={() => { navigate('/alerts'); onClose(); }}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs font-bold text-navy">{a.device_id}</span>
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-red-100 text-red-600">
                        {a.severity || 'ALERT'}
                      </span>
                    </div>
                    <p className="text-[11px] text-muted mt-0.5 truncate">{alertDetail(a)}</p>
                  </div>
                  <span className="text-[10px] text-muted shrink-0 mt-0.5">
                    {a.started_at ? new Date(a.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )
      }

      {/* Footer link */}
      <div className="border-t border-slate-50 p-2">
        <button
          onClick={() => { navigate('/alerts'); onClose(); }}
          className="w-full text-xs font-semibold text-primary py-2 hover:bg-blue-50 rounded-xl transition-colors">
          View all alerts →
        </button>
      </div>
    </div>
  );
}

export function PortalTopBar({ summary, alerts = [] }) {
  const [showAlerts, setShowAlerts] = useState(false);
  const { user, logout } = useAuth();
  const navigate  = useNavigate();
  const location  = useLocation();
  const bellRef   = useRef(null);

  const title       = PAGE_TITLES[location.pathname] ?? 'Portal';
  const activeCount = (alerts || []).length;
  const sysStatus   = deriveSystemStatus(summary);
  const isHome      = location.pathname === '/';

  function handleBack() {
    if (window.history.state?.idx > 0) navigate(-1);
    else navigate('/');
  }

  const initials = user?.name
    ? user.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : 'U';

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showAlerts) return;
    function handleClick(e) {
      if (bellRef.current && !bellRef.current.contains(e.target)) {
        setShowAlerts(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showAlerts]);

  async function handleLogout() {
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <header className="flex items-center justify-between gap-4 px-6 py-3.5 bg-white border-b border-slate-100">
      {/* Page title with optional back button */}
      <div className="flex items-center gap-2 min-w-0">
        {!isHome && (
          <button
            onClick={handleBack}
            title="Back"
            aria-label="Back"
            className="flex items-center justify-center w-8 h-8 rounded-full text-muted hover:bg-slate-50 hover:text-navy transition-colors shrink-0"
          >
            <ArrowLeft size={18} />
          </button>
        )}
        <h1 className="text-base font-bold text-navy truncate">{title}</h1>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-3 shrink-0">
        {/* System status chip */}
        <div
          className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold cursor-default"
          style={{ background: sysStatus.bg, color: sysStatus.color }}
          title="Status of the monitoring tablets"
          aria-label={sysStatus.label}
        >
          <span className="w-2 h-2 rounded-full" style={{ background: sysStatus.color }} aria-hidden="true" />
          {sysStatus.label}
        </div>

        {/* Bell with red badge */}
        <div className="relative" ref={bellRef}>
          <button
            onClick={() => setShowAlerts(v => !v)}
            aria-label={`${activeCount} active alert${activeCount !== 1 ? 's' : ''}`}
            aria-expanded={showAlerts}
            className="relative p-2 rounded-xl hover:bg-slate-50 transition-colors text-muted hover:text-navy"
          >
            <Bell size={19} />
            {activeCount > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full text-white text-[10px] font-bold flex items-center justify-center"
                style={{ background: '#EF4444' }}
                aria-hidden="true"
              >
                {activeCount > 9 ? '9+' : activeCount}
              </span>
            )}
          </button>
          {showAlerts && (
            <AlertDropdown alerts={alerts} onClose={() => setShowAlerts(false)} />
          )}
        </div>

        <div className="w-px h-6 bg-slate-100" aria-hidden="true" />

        {/* User menu */}
        <div className="relative group">
          <button
            className="flex items-center gap-2 px-2 py-1.5 rounded-xl hover:bg-slate-50 transition-colors"
            aria-label="User menu"
          >
            <div
              className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-blue-400 flex items-center justify-center text-white text-xs font-bold shrink-0"
              aria-hidden="true"
            >
              {initials}
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-xs font-semibold text-navy leading-none">{user?.name ?? 'User'}</p>
              <p className="text-[10px] text-muted mt-0.5 capitalize">
                {(user?.role ?? '').toLowerCase().replace('_', ' ')}
              </p>
            </div>
            <ChevronDown size={14} className="text-muted" aria-hidden="true" />
          </button>

          {/* Dropdown */}
          <div className="absolute right-0 top-11 w-44 bg-white rounded-2xl shadow-hover border border-slate-100 z-50 overflow-hidden opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-150">
            <div className="px-4 py-3 border-b border-slate-50">
              <p className="text-xs font-bold text-navy truncate">{user?.name}</p>
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-600 capitalize">
                {(user?.role ?? '').toLowerCase().replace('_', ' ')}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="w-full text-left px-4 py-2.5 text-xs font-semibold text-red-500 hover:bg-red-50 transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
