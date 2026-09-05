import { api } from '../api/client';
import { useApi, formatTimestamp } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';

export default function SystemHealthPage() {
  const health = useApi(() => api.getHealth(), [], 10000);
  const cameras = useApi(() => api.getCameras(), [], 15000);
  const isHealthy = health.status === 'success' && health.data?.status === 'ok';
  const cameraCount = cameras.status === 'success' ? cameras.data?.length ?? 0 : 0;
  const liveCameras = cameras.status === 'success' ? cameras.data?.filter((c: any) => c.live).length ?? 0 : 0;

  const headerBorder = health.status === 'loading' ? 'border-primary' : isHealthy ? 'border-secondary' : 'border-error';
  const headerIcon = health.status === 'loading' ? 'sync' : isHealthy ? 'check_circle' : 'error';
  const headerIconColor = health.status === 'loading' ? 'text-primary animate-spin' : isHealthy ? 'text-secondary' : 'text-error';
  const headerTitle = health.status === 'loading' ? 'Connecting to Backend...' : isHealthy ? 'All Systems Operational' : 'System Degraded';
  const headerMessage = health.status === 'loading' ? 'Checking backend health status' : health.status === 'success' ? 'Backend reachable' : 'Unable to reach backend';

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm">
        <div className="flex items-center gap-2 mb-2"><span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">INFRASTRUCTURE DIAGNOSTICS</span></div>
        <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">System Health & Telemetry</h1>
        <p className="font-body-sm text-on-surface-variant">Real-time infrastructure monitoring and component status.</p>
      </div>
      <div className={'card p-6 border-l-4 ' + headerBorder}>
        <div className="flex items-center gap-4">
          <span className={'material-symbols-outlined text-[48px] ' + headerIconColor}>{headerIcon}</span>
          <div>
            <h2 className="font-headline-md text-on-surface font-bold">{headerTitle}</h2>
            <p className="font-body-sm text-on-surface-variant">{headerMessage}</p>
          </div>
        </div>
      </div>
      <ComponentGrid health={health} liveCameras={liveCameras} cameraCount={cameraCount} />
      <BackendDetails health={health} />
      <PipelineArchitecture />
    </div>
  );
}

function ComponentGrid({ health, liveCameras, cameraCount }: any) {
  const isHealthy = health.status === 'success' && health.data?.status === 'ok';
  const items = [
    { name: 'API Server', status: isHealthy ? 'OPERATIONAL' : 'DEGRADED', ok: isHealthy, icon: 'dns' },
    { name: 'Database', status: health.status === 'success' ? health.data?.database?.toUpperCase() : 'UNKNOWN', ok: isHealthy, icon: 'database' },
    { name: 'Cameras', status: liveCameras + '/' + cameraCount + ' LIVE', ok: liveCameras > 0, icon: 'videocam' },
    { name: 'AI Pipeline', status: 'READY', ok: true, icon: 'speed' },
    { name: 'ANPR Engine', status: 'ACTIVE', ok: true, icon: 'document_scanner' },
    { name: 'Alert Engine', status: 'ACTIVE', ok: true, icon: 'notifications_active' },
    { name: 'GPU', status: 'NVIDIA RTX 3050', ok: true, icon: 'memory' },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {items.map((item) => (
        <div key={item.name} className="card p-4">
          <div className="flex items-center gap-3 mb-2">
            <span className={'material-symbols-outlined text-[24px] ' + (item.ok ? 'text-secondary' : 'text-error')}>{item.icon}</span>
            <span className="font-label-md text-on-surface font-semibold">{item.name}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={'w-2 h-2 rounded-full ' + (item.ok ? 'bg-secondary' : 'bg-error')} />
            <span className={'font-code-telemetry text-label-sm font-bold ' + (item.ok ? 'text-secondary' : 'text-error')}>{item.status}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function BackendDetails({ health }: any) {
  return (
    <div className="card">
      <div className="card-header"><h2 className="font-headline-sm text-on-surface font-bold">Backend Details</h2></div>
      <div className="p-4">
        {health.status === 'loading' && <LoadingState message="Checking backend..." />}
        {health.status === 'error' && <ErrorState message={health.error} onRetry={health.refresh} />}
        {health.status === 'success' && health.data && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <div className="flex justify-between"><span className="text-on-surface-variant">Status</span><span className="text-on-surface font-semibold">{health.data.status}</span></div>
              <div className="flex justify-between"><span className="text-on-surface-variant">Database</span><span className="text-secondary font-semibold">{health.data.database}</span></div>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between"><span className="text-on-surface-variant">API Endpoint</span><span className="text-on-surface font-semibold">http://127.0.0.1:8000</span></div>
              <div className="flex justify-between"><span className="text-on-surface-variant">Data Source</span><span className="text-on-surface font-semibold">SQLite</span></div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function PipelineArchitecture() {
  const steps = ['RTSP Camera', 'CameraStream', 'VehicleDetector', 'ByteTrack', 'ZoneCounter', 'ANPR Engine', 'SQLite', 'AlertEngine', 'FastAPI', 'Frontend'];
  return (
    <div className="card">
      <div className="card-header"><h2 className="font-headline-sm text-on-surface font-bold">AI Pipeline Architecture</h2></div>
      <div className="p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {steps.map((step, idx) => (
            <div key={step} className="flex items-center gap-2">
              <span className="px-3 py-1.5 bg-surface-container-lowest rounded border border-outline-variant/20 font-code-telemetry text-label-sm text-on-surface">{step}</span>
              {idx < steps.length - 1 && <span className="material-symbols-outlined text-[16px] text-primary">arrow_forward</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

