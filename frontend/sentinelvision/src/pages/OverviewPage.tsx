import { api } from '../api/client';
import { useApi, formatRelativeTime, getStatusColor } from '../hooks';
import StatCard from '../components/StatCard';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

export default function OverviewPage() {
  const health = useApi(() => api.getHealth(), [], 30000);
  const sysHealth = useApi(() => api.getSystemHealth(), [], 15000);
  const counts = useApi(() => api.getCounts(), [], 10000);
  const alerts = useApi(() => api.getAlerts(), [], 10000);
  const globalVehicles = useApi(() => api.getGlobalVehicles(1, 0), [], 15000);

  const isHealthy = health.status === 'success' && health.data?.status === 'ok';
  const summary = sysHealth.data?.summary;
  const configuredCameras = summary?.total_configured ?? 30;
  const onlineCameras = summary?.online_count ?? 0;
  const checkedCameras = configuredCameras - (summary?.not_checked_count ?? configuredCameras);
  const aiActiveCount = summary?.ai_active_count ?? 1;

  const totalIn = counts.status === 'success' ? counts.data?.total.IN ?? 0 : 0;
  const totalOut = counts.status === 'success' ? counts.data?.total.OUT ?? 0 : 0;
  const totalVehicles = totalIn + totalOut;
  const activeAlerts = alerts.status === 'success' ? alerts.data?.results.filter((a) => a.status === 'NEW').length ?? 0 : 0;
  const totalGlobalVehicles = globalVehicles.data?.count ?? 0;

  let healthLabel = 'CHECKING...';
  let healthClass = 'text-outline';
  if (health.status === 'loading') {
    healthLabel = 'CONNECTING...';
    healthClass = 'text-primary animate-pulse';
  } else if (isHealthy) {
    healthLabel = 'BACKEND ONLINE';
    healthClass = 'text-secondary';
  } else if (health.status === 'error') {
    healthLabel = 'BACKEND OFFLINE';
    healthClass = 'text-error';
  }

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-surface-container-low p-4 rounded-lg shadow-sm">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">TACTICAL FEED MATRIX // ALPHA-01</span>
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-secondary animate-ping" />
            <span className="font-code-telemetry text-label-sm text-secondary font-semibold">STREAM ENGAGED</span>
          </div>
          <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">Traffic Intelligence Overview</h1>
          <p className="font-body-sm text-on-surface-variant">Continuous optical parsing, dynamic trajectory estimation, and automated watchlist triangulation.</p>
        </div>
        <div className="flex items-center gap-4 font-code-telemetry text-label-sm">
          <div className="flex items-center gap-2 bg-surface-container px-3 py-1 rounded shadow-inner">
            <span className="material-symbols-outlined text-[14px] text-secondary">health_and_safety</span>
            <span className={healthClass}>{healthLabel}</span>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard icon="settings_input_component" label="Configured Cameras" value={sysHealth.status === 'loading' ? '—' : configuredCameras} sublabel={`Checked: ${checkedCameras} | Online: ${onlineCameras}`} color="text-primary" />
        <StatCard icon="psychology" label="AI Active Engine" value={sysHealth.status === 'loading' ? '—' : `${aiActiveCount} Active`} sublabel="YOLO + ByteTrack + ANPR" color="text-cyan-400" />
        <StatCard icon="directions_car" label="Global Vehicles" value={globalVehicles.status === 'loading' ? '—' : totalGlobalVehicles} sublabel="Identified across cameras" color="text-secondary" />
        <StatCard icon="warning" label="Active Alerts" value={alerts.status === 'loading' ? '—' : activeAlerts} sublabel="New alerts pending" color="text-error" />
        <StatCard icon="swap_calls" label="Zone Crossings" value={counts.status === 'loading' ? '—' : totalVehicles} sublabel={`IN: ${totalIn} | OUT: ${totalOut}`} color="text-secondary" />
        <StatCard icon="videocam" label="Online Streams" value={sysHealth.status === 'loading' ? '—' : `${onlineCameras} / ${configuredCameras}`} sublabel="Live stream health" color="text-emerald-400" />
        <StatCard icon="monitoring" label="System Status" value={health.status === 'loading' ? 'CONNECTING' : isHealthy ? 'HEALTHY' : 'DEGRADED'} sublabel={health.status === 'loading' ? 'Connecting...' : `DB: ${health.data?.database}`} color={isHealthy ? 'text-secondary' : 'text-error'} />
        <StatCard icon="speed" label="Pipeline Status" value="OPERATIONAL" sublabel="Live Multi-Camera Ingestion" color="text-primary" />
      </div>
    </div>
  );
}
