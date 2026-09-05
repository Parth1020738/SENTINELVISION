import { api } from '../api/client';
import { useApi, formatRelativeTime, getStatusColor } from '../hooks';
import StatCard from '../components/StatCard';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

export default function OverviewPage() {
  const health = useApi(() => api.getHealth(), [], 30000);
  const cameras = useApi(() => api.getCameras(), [], 15000);
  const counts = useApi(() => api.getCounts(), [], 10000);
  const alerts = useApi(() => api.getAlerts(), [], 10000);
  const isHealthy = health.status === 'success' && health.data?.status === 'ok';
  const cameraCount = cameras.status === 'success' ? cameras.data?.length ?? 0 : 0;
  const liveCameras = cameras.status === 'success' ? cameras.data?.filter(c => c.live).length ?? 0 : 0;
  const totalIn = counts.status === 'success' ? counts.data?.total.IN ?? 0 : 0;
  const totalOut = counts.status === 'success' ? counts.data?.total.OUT ?? 0 : 0;
  const totalVehicles = totalIn + totalOut;
  const activeAlerts = alerts.status === 'success' ? alerts.data?.results.filter((a) => a.status === 'NEW').length ?? 0 : 0;
  const vehicleClasses = counts.status === 'success' ? counts.data?.by_class ?? {} : {};
  const classDistribution = Object.entries(vehicleClasses).map(([cls, dirs]) => ({ class: cls, in: dirs.IN, out: dirs.OUT, total: dirs.IN + dirs.OUT })).sort((a, b) => b.total - a.total);

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
        <StatCard icon="directions_car" label="Vehicles Detected" value={counts.status === 'loading' ? '—' : totalVehicles} sublabel="Total zone crossings" color="text-primary" />
        <StatCard icon="login" label="IN Count" value={counts.status === 'loading' ? '—' : totalIn} sublabel="Inbound traffic" color="text-secondary" />
        <StatCard icon="logout" label="OUT Count" value={counts.status === 'loading' ? '—' : totalOut} sublabel="Outbound traffic" color="text-primary" />
        <StatCard icon="warning" label="Active Alerts" value={alerts.status === 'loading' ? '—' : activeAlerts} sublabel="New alerts pending" color="text-error" />
        <StatCard icon="videocam" label="Active Cameras" value={cameras.status === 'loading' ? '—' : `${liveCameras} / ${cameraCount}`} sublabel="Live feeds" color="text-secondary" />
        <StatCard icon="document_scanner" label="Plate Reads" value="—" sublabel="ANPR data (see ANPR page)" color="text-primary" />
        <StatCard icon="monitoring" label="System Status" value={health.status === 'loading' ? 'CONNECTING' : isHealthy ? 'HEALTHY' : 'DEGRADED'} sublabel={health.status === 'loading' ? 'Connecting to backend...' : health.status === 'success' ? `DB: ${health.data?.database}` : 'Backend unreachable'} color={health.status === 'loading' ? 'text-primary' : isHealthy ? 'text-secondary' : 'text-error'} />
        <StatCard icon="speed" label="AI Pipeline" value="READY" sublabel="YOLO + ByteTrack + ANPR" color="text-primary" />
      </div>
    </div>
  );
}
