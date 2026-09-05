import { api } from '../api/client';
import { useApi } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';

export default function LiveMonitoringPage() {
  const cameras = useApi(() => api.getCameras(), [], 15000);
  const counts = useApi(() => api.getCounts({ camera_id: 'cam01' }), [], 10000);
  const cam01 = cameras.status === 'success' ? cameras.data?.find(c => c.camera_id === 'cam01') : null;

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <HeaderSection />
      <CameraFeed cam01={cam01} />
      <CountsSection counts={counts} cam01={cam01} />
      <SecurityNotice />
    </div>
  );
}

function HeaderSection() {
  return (
    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-surface-container-low p-4 rounded-lg shadow-sm">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">LIVE CCTV MONITORING</span>
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-error animate-pulse" />
          <span className="font-code-telemetry text-label-sm text-error font-semibold">REC</span>
        </div>
        <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">Live Camera Feed</h1>
        <p className="font-body-sm text-on-surface-variant">Real-time optical surveillance with AI-powered vehicle detection and tracking.</p>
      </div>
    </div>
  );
}

function CameraFeed({ cam01 }: { cam01: any }) {
  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-error animate-pulse" />
          <span className="font-code-telemetry text-label-sm text-on-surface font-bold">CAM-01: NORTH PERIMETER</span>
          <span className="status-badge bg-error/20 text-error">LIVE</span>
        </div>
        <span className="font-code-telemetry text-label-sm text-on-surface-variant">
          {cam01 ? `${cam01.width || '?'}x${cam01.height || '?'}` : 'Connecting...'}
        </span>
      </div>
      <div className="relative aspect-video bg-surface-container-lowest flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 p-8">
          <span className="material-symbols-outlined text-[64px] text-outline">live_tv</span>
          <div className="text-center">
            <h3 className="font-headline-sm text-on-surface font-bold mb-2">Live Stream</h3>
            <p className="font-body-sm text-on-surface-variant max-w-md">
              Camera feed is active. Direct RTSP streaming to browser is not available for security reasons.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function CountsSection({ counts, cam01 }: { counts: any; cam01: any }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div className="card p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="font-label-sm text-outline uppercase tracking-wider">Traffic Counts</span>
          <span className="material-symbols-outlined text-[20px] text-primary">analytics</span>
        </div>
        {counts.status === 'loading' && <LoadingState message="Loading counts..." />}
        {counts.status === 'error' && <ErrorState message={counts.error} onRetry={counts.refresh} />}
        {counts.status === 'success' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-body-sm text-on-surface">IN</span>
              <span className="font-code-telemetry text-label-md text-secondary font-bold">{counts.data?.total.IN ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-body-sm text-on-surface">OUT</span>
              <span className="font-code-telemetry text-label-md text-primary font-bold">{counts.data?.total.OUT ?? 0}</span>
            </div>
          </div>
        )}
      </div>
      <div className="card p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="font-label-sm text-outline uppercase tracking-wider">Vehicle Classes</span>
          <span className="material-symbols-outlined text-[20px] text-secondary">directions_car</span>
        </div>
        {counts.status === 'loading' && <LoadingState message="Loading..." />}
        {counts.status === 'success' && (
          <div className="space-y-1">
            {Object.entries(counts.data?.by_class ?? {}).slice(0, 5).map(([cls, dirs]: [string, any]) => (
              <div key={cls} className="flex items-center justify-between">
                <span className="font-code-telemetry text-label-sm text-on-surface truncate">{cls}</span>
                <span className="font-code-telemetry text-label-sm text-primary">{dirs.IN + dirs.OUT}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="card p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="font-label-sm text-outline uppercase tracking-wider">Connection</span>
          <span className="material-symbols-outlined text-[20px] text-secondary">settings_ethernet</span>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-body-sm text-on-surface">Status</span>
            <span className={`font-code-telemetry text-label-sm font-bold ${cam01?.live ? 'text-secondary' : 'text-error'}`}>{cam01?.live ? 'CONNECTED' : 'OFFLINE'}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-body-sm text-on-surface">Transport</span>
            <span className="font-code-telemetry text-label-sm text-on-surface-variant">RTSP/TCP</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function SecurityNotice() {
  return (
    <div className="card p-4 border-l-4 border-primary">
      <div className="flex items-start gap-3">
        <span className="material-symbols-outlined text-[24px] text-primary">security</span>
        <div>
          <h3 className="font-label-md text-on-surface font-semibold mb-1">Security Notice</h3>
          <p className="font-body-sm text-on-surface-variant">
            RTSP credentials are never exposed to the browser. The AI pipeline processes the camera stream server-side and publishes detection metadata via REST API.
          </p>
        </div>
      </div>
    </div>
  );
}
