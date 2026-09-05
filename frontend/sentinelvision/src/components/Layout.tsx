import { NavLink, Outlet } from 'react-router-dom';
import { useNow } from '../hooks';

const navItems = [
  { to: '/', label: 'Overview', icon: 'dashboard' },
  { to: '/live', label: 'Live Monitoring', icon: 'videocam' },
  { to: '/vehicles', label: 'Vehicles', icon: 'directions_car' },
  { to: '/anpr', label: 'ANPR', icon: 'document_scanner' },
  { to: '/watchlist', label: 'Watchlist', icon: 'shield_with_heart' },
  { to: '/alerts', label: 'Alerts', icon: 'warning' },
  { to: '/history', label: 'History', icon: 'manage_search' },
  { to: '/health', label: 'System Health', icon: 'monitoring' },
];

export default function Layout() {
  const now = useNow();

  return (
    <div className="min-h-screen bg-surface flex">
      {/* Sidebar */}
      <aside className="w-64 bg-surface-container-low border-r border-outline-variant/20 flex flex-col">
        {/* Logo */}
        <div className="px-4 py-4 border-b border-outline-variant/20">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-[28px]">visibility</span>
            <div>
              <h1 className="font-headline-sm text-on-surface font-bold tracking-tight">SentinelVision</h1>
              <p className="font-code-telemetry text-label-sm text-primary">TACTICAL AI COMMAND</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                  isActive
                    ? 'bg-primary-container/20 text-primary font-semibold'
                    : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'
                }`
              }
            >
              <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Status Footer */}
        <div className="px-4 py-3 border-t border-outline-variant/20">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
            <span className="font-code-telemetry text-label-sm text-secondary font-semibold">SYSTEM ONLINE</span>
          </div>
          <p className="font-code-telemetry text-label-sm text-outline mt-1" id="utc-clock">{now}</p>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
