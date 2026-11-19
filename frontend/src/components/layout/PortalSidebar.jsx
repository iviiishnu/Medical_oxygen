/**
 * PortalSidebar.jsx
 * =================
 * Sidebar for the new Oxygen Flow Check portal.
 * 6 tabs: Dashboard, Live Monitoring, Alerts, Incidents, Analytics, Settings.
 * Reuses the existing sidebar styling from Sidebar.jsx.
 */
import { useState, useEffect } from 'react';
import { LayoutDashboard, Monitor, Bell, FileText, BarChart2, Settings, LogOut, Sun, Moon } from 'lucide-react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

const THEME_KEY = 'medigas_theme';

const NAV = [
  { path: '/',           label: 'Dashboard',      Icon: LayoutDashboard, end: true  },
  { path: '/live',       label: 'Live Monitoring', Icon: Monitor                     },
  { path: '/alerts',     label: 'Alerts',          Icon: Bell                        },
  { path: '/incidents',  label: 'Incidents',       Icon: FileText                    },
  { path: '/analytics',  label: 'Analytics',       Icon: BarChart2                   },
  { path: '/settings',   label: 'Settings',        Icon: Settings                    },
];

export function PortalSidebar({ activeAlertCount = 0, connected = false, collapsed = false }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem(THEME_KEY) || 'light'; } catch { return 'light'; }
  });

  useEffect(() => {
    if (theme === 'dark') document.documentElement.dataset.theme = 'dark';
    else delete document.documentElement.dataset.theme;
  }, [theme]);

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch {}
  }

  const initials = user?.name
    ? user.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : 'U';

  async function handleLogout() {
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <aside
      className={`flex flex-col h-full bg-white border-r border-slate-100 transition-all duration-300 shrink-0 ${collapsed ? 'w-16' : 'w-52'}`}
      style={{ boxShadow: '4px 0 24px rgba(80,110,180,0.06)' }}
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className={`flex items-center gap-2.5 px-4 py-5 border-b border-slate-50 ${collapsed ? 'justify-center' : ''}`}>
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-blue-400 flex items-center justify-center shrink-0 shadow-sm">
          <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
            <circle cx="12" cy="12" r="8" stroke="white" strokeWidth="1.5" opacity="0.7" />
            <path d="M12 7v5l3 3" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        {!collapsed && (
          <div className="leading-none min-w-0">
            <p className="text-navy font-bold text-sm tracking-tight">Oxygen Flow Check</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-4 flex flex-col gap-1" aria-label="Portal sections">
        {NAV.map(({ path, label, Icon, end }) => (
          <NavLink
            key={path}
            to={path}
            end={end}
            aria-label={label}
            className={({ isActive }) =>
              `relative flex items-center gap-3 px-3 py-2.5 rounded-xl w-full text-left transition-all duration-150
               ${isActive ? 'bg-blue-50 text-primary font-semibold' : 'text-muted hover:bg-slate-50 hover:text-navy font-medium'}
               ${collapsed ? 'justify-center' : ''}`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={18} strokeWidth={isActive ? 2.2 : 1.8} aria-hidden="true" />
                {!collapsed && <span className="text-sm">{label}</span>}
                {label === 'Alerts' && activeAlertCount > 0 && (
                  <span
                    className={`ml-auto bg-accent text-white text-[10px] font-bold rounded-full leading-none flex items-center justify-center ${collapsed ? 'absolute -top-1 -right-1 w-4 h-4' : 'w-5 h-5'}`}
                    aria-label={`${activeAlertCount} active alerts`}
                  >
                    {activeAlertCount > 9 ? '9+' : activeAlertCount}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Connection pill */}
      <div className={`px-3 pb-2 ${collapsed ? 'flex justify-center' : ''}`}>
        <div
          title="Connection between this browser and the server"
          className={`flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-default ${connected ? 'bg-green-50' : 'bg-red-50'} ${collapsed ? 'justify-center' : ''}`}
        >
          <span
            className={`w-2.5 h-2.5 rounded-full shrink-0 ${connected ? 'bg-success live-dot' : 'bg-danger live-dot-red'}`}
            aria-hidden="true"
          />
          {!collapsed && (
            <span className={`text-xs font-semibold ${connected ? 'text-green-700' : 'text-red-600'}`}>
              {connected ? 'Portal connected' : 'Portal disconnected'}
            </span>
          )}
        </div>
      </div>

      {/* User row + logout + theme toggle */}
      {!collapsed && (
        <div className="px-3 pb-4 flex flex-col gap-1 border-t border-slate-50 pt-3">
          <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-slate-50">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-blue-400 flex items-center justify-center text-white text-xs font-bold shrink-0">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-navy truncate">{user?.name ?? 'User'}</p>
              <p className="text-[10px] text-muted capitalize">{(user?.role ?? '').toLowerCase().replace('_', ' ')}</p>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold text-muted hover:text-red-500 hover:bg-red-50 transition-colors"
            >
              <LogOut size={13} /> Sign out
            </button>
            <button
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              className="flex items-center justify-center w-8 h-8 rounded-xl text-muted hover:bg-slate-50 hover:text-navy transition-colors shrink-0"
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </div>
      )}

      {/* Collapsed: show theme toggle icon */}
      {collapsed && (
        <div className="px-3 pb-4 flex justify-center border-t border-slate-50 pt-3">
          <button
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            className="flex items-center justify-center w-8 h-8 rounded-xl text-muted hover:bg-slate-50 hover:text-navy transition-colors shrink-0"
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>
      )}
    </aside>
  );
}
