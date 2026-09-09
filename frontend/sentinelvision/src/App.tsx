import { useState } from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import AccessGate from './components/AccessGate';
import OverviewPage from './pages/OverviewPage';
import LiveMonitoringPage from './pages/LiveMonitoringPage';
import VehiclesPage from './pages/VehiclesPage';
import ANPRPage from './pages/ANPRPage';
import WatchlistPage from './pages/WatchlistPage';
import AlertsPage from './pages/AlertsPage';
import HistoryPage from './pages/HistoryPage';
import SystemHealthPage from './pages/SystemHealthPage';

export default function App() {
  const [isAuthenticated] = useState<boolean>(() => {
    // TEMPORARY DEMO MODE: Ensure a session token exists for dev/demo UI testing.
    // If no token exists in localStorage, initialize a guest demo session token.
    if (!localStorage.getItem('sentinel_token')) {
      localStorage.setItem('sentinel_token', 'demo_guest_token');
    }
    return true;
  });

  // AccessGate visually bypassed for temporary live camera demo testing.
  // Component preserved for production access code gating.

  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="live" element={<LiveMonitoringPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
          <Route path="anpr" element={<ANPRPage />} />
          <Route path="watchlist" element={<WatchlistPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="health" element={<SystemHealthPage />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
