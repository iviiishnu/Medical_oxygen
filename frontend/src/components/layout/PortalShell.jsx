/**
 * PortalShell.jsx
 * ===============
 * Main app layout for the Oxygen Flow Check portal.
 * Renders PortalSidebar + PortalTopBar + main content area.
 * Receives data from usePortalData via the PortalApp.
 */
import { useState, useEffect } from 'react';
import { PortalSidebar } from './PortalSidebar';
import { PortalTopBar }  from './PortalTopBar';

export function PortalShell({ summary, alerts = [], connected = false, children }) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1024px)');
    const handler = (e) => setCollapsed(e.matches);
    setCollapsed(mq.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const activeAlertCount = (alerts || []).length;

  return (
    <div className="min-h-screen bg-[#F4F7FC] relative overflow-hidden flex items-start justify-center p-4 sm:p-6">
      <div className="pointer-events-none absolute top-0 left-0 w-72 h-72 bg-dots opacity-60" aria-hidden="true" />
      <div
        className="pointer-events-none absolute -top-24 -right-24 w-96 h-96 rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(47,128,237,0.10) 0%, transparent 70%)' }}
        aria-hidden="true"
      />

      <div
        className="relative z-10 w-full max-w-[1440px] min-h-[calc(100vh-3rem)] rounded-3xl bg-white overflow-hidden flex"
        style={{ boxShadow: '0 8px 48px rgba(47,128,237,0.10)', border: '1px solid rgba(47,128,237,0.10)' }}
      >
        <PortalSidebar
          activeAlertCount={activeAlertCount}
          connected={connected}
          collapsed={collapsed}
        />

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <PortalTopBar summary={summary} alerts={alerts} />
          <main className="flex-1 overflow-y-auto bg-[#F4F7FC]">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
