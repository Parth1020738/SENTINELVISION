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
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    return Boolean(localStorage.getItem('sentinel_token'));
  });

  if (!isAuthenticated) {
    return <AccessGate onAuthenticated={() => setIsAuthenticated(true)} />;
  }

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
