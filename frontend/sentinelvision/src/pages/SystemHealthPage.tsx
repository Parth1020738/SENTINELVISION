import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useApi, formatTimestamp } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import { CameraHealth } from '../types';

export default function SystemHealthPage() {
  const navigate = useNavigate();
  const systemHealth = useApi(() => api.getSystemHealth(), [], 10000);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  const isHealthy = systemHealth.status === 'success' && systemHealth.data?.status === 'ok';
  const summary = systemHealth.data?.summary;
  const cameras = systemHealth.data?.cameras ?? [];

  const filteredCameras = cameras.filter((c) => {
    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'ONLINE') return c.status === 'ONLINE';
    if (statusFilter === 'DEGRADED') return c.status === 'DEGRADED';
    if (statusFilter === 'OFFLINE') return c.status === 'OFFLINE';
    if (statusFilter === 'NOT_CHECKED') return c.status === 'NOT_CHECKED' || c.status === 'UNKNOWN';
    return true;
  });

  const headerBorder = systemHealth.status === 'loading' ? 'border-primary' : isHealthy ? 'border-secondary' : 'border-amber-500';
  const headerIcon = systemHealth.status === 'loading' ? 'sync' : isHealthy ? 'check_circle' : 'warning';
  const headerIconColor = systemHealth.status === 'loading' ? 'text-primary animate-spin' : isHealthy ? 'text-secondary' : 'text-amber-500';
  const headerTitle = systemHealth.status === 'loading' ? 'Connecting to Telemetry Services...' : isHealthy ? 'All Systems & Streams Operational' : 'Telemetry Status: Monitored';
  const headerMessage = systemHealth.status === 'loading'
    ? 'Polling camera health and infrastructure telemetry...'
    : systemHealth.status === 'success'
      ? `Backend reachable. ${summary?.online_count ?? 0} online, ${summary?.degraded_count ?? 0} degraded, ${summary?.offline_count ?? 0} offline, ${summary?.not_checked_count ?? 0} not checked.`
      : 'Unable to reach backend telemetry endpoint';

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      {/* Header banner */}
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">
              GOVERNMENT CCTV MONITORING
            </span>
          </div>
          <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">System Health & Camera Monitoring</h1>
          <p className="font-body-sm text-on-surface-variant">Real-time camera runtime telemetry and component infrastructure status.</p>
        </div>
        <button
          onClick={() => systemHealth.refresh()}
          className="px-4 py-2 bg-surface-container-high hover:bg-surface-container-highest text-on-surface rounded-lg font-label-md flex items-center gap-2 transition-colors"
        >
          <span className="material-symbols-outlined text-[18px]">refresh</span>
          Refresh Telemetry
        </button>
      </div>

      {/* Infrastructure Alert Banner */}
      <div className={'card p-6 border-l-4 ' + headerBorder}>
        <div className="flex items-center gap-4">
          <span className={'material-symbols-outlined text-[48px] ' + headerIconColor}>{headerIcon}</span>
          <div>
            <h2 className="font-headline-md text-on-surface font-bold">{headerTitle}</h2>
            <p className="font-body-sm text-on-surface-variant">{headerMessage}</p>
          </div>
        </div>
      </div>

      {/* Telemetry Summary KPI Grid */}
      <SummaryKpiGrid summary={summary} loading={systemHealth.status === 'loading'} />

      {/* Camera Grid & Monitoring Section */}
      <div className="card p-6 flex flex-col gap-4">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-outline-variant/20 pb-4">
          <div>
            <h2 className="font-headline-sm text-on-surface font-bold flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-[24px]">videocam</span>
              30-Camera Grid Monitoring
            </h2>
            <p className="font-body-xs text-on-surface-variant">
              Runtime health observation matrix across all configured CCTV feeds.
            </p>
          </div>

          {/* Filter Tabs */}
          <div className="flex flex-wrap items-center gap-1.5 bg-surface-container-low p-1 rounded-lg border border-outline-variant/20">
            {[
              { id: 'ALL', label: `All (${summary?.total_configured ?? 30})` },
              { id: 'ONLINE', label: `Online (${summary?.online_count ?? 0})` },
              { id: 'DEGRADED', label: `Degraded (${summary?.degraded_count ?? 0})` },
              { id: 'OFFLINE', label: `Offline (${summary?.offline_count ?? 0})` },
              { id: 'NOT_CHECKED', label: `Not Checked (${summary?.not_checked_count ?? 0})` },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={
                  'px-3 py-1.5 rounded font-label-xs font-semibold transition-all ' +
                  (statusFilter === tab.id
                    ? 'bg-primary text-on-primary shadow-sm'
                    : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high')
                }
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {systemHealth.status === 'loading' && <LoadingState message="Loading camera telemetry grid..." />}
        {systemHealth.status === 'error' && <ErrorState message={systemHealth.error} onRetry={systemHealth.refresh} />}
        
        {systemHealth.status === 'success' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredCameras.map((cam) => (
              <CameraHealthCard key={cam.camera_id} camera={cam} onNavigate={(id) => navigate(`/live?camera=${id}`)} />
            ))}
            {filteredCameras.length === 0 && (
              <div className="col-span-full py-12 text-center text-on-surface-variant font-body-md">
                No cameras match the selected status filter "{statusFilter}".
              </div>
            )}
          </div>
        )}
      </div>

      {/* Backend & Component Status */}
      <ComponentGrid health={systemHealth} />
      <PipelineArchitecture />
    </div>
  );
}

function SummaryKpiGrid({ summary, loading }: { summary: any; loading: boolean }) {
  const items = [
    { label: 'Configured Cameras', value: summary?.total_configured ?? 30, icon: 'settings_input_component', color: 'text-primary', bg: 'bg-primary/10' },
    { label: 'Online Streams', value: summary?.online_count ?? 0, icon: 'check_circle', color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
    { label: 'Degraded Feeds', value: summary?.degraded_count ?? 0, icon: 'warning', color: 'text-amber-400', bg: 'bg-amber-500/10' },
    { label: 'Offline / Failed', value: summary?.offline_count ?? 0, icon: 'error', color: 'text-rose-400', bg: 'bg-rose-500/10' },
    { label: 'Not Checked', value: summary?.not_checked_count ?? 30, icon: 'help_outline', color: 'text-slate-400', bg: 'bg-slate-500/10' },
    { label: 'AI Active Engine', value: summary?.ai_active_count ?? 1, icon: 'psychology', color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
      {items.map((item) => (
        <div key={item.label} className="card p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="font-label-xs text-on-surface-variant font-medium">{item.label}</span>
            <div className={`p-1.5 rounded-md ${item.bg}`}>
              <span className={`material-symbols-outlined text-[20px] ${item.color}`}>{item.icon}</span>
            </div>
          </div>
          <div className="font-headline-md text-on-surface font-bold">
            {loading ? '...' : item.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function CameraHealthCard({ camera, onNavigate }: { camera: CameraHealth; onNavigate: (id: string) => void }) {
  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case 'ONLINE':
        return { bg: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', icon: 'sensors', label: 'ONLINE' };
      case 'DEGRADED':
        return { bg: 'bg-amber-500/20 text-amber-400 border-amber-500/30', icon: 'warning', label: 'DEGRADED' };
      case 'OFFLINE':
        return { bg: 'bg-rose-500/20 text-rose-400 border-rose-500/30', icon: 'videocam_off', label: 'OFFLINE' };
      default:
        return { bg: 'bg-slate-500/20 text-slate-400 border-slate-500/30', icon: 'help', label: 'NOT CHECKED' };
    }
  };

  const getAttentionBadge = (state?: string) => {
    switch (state) {
      case 'CRITICAL':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      case 'WATCH':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  const badge = getStatusBadge(camera.status);

  return (
    <div className="card p-4 flex flex-col justify-between gap-3 hover:border-outline transition-colors">
      <div>
        {/* Header row */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div>
            <div className="font-code-telemetry text-label-md font-bold text-on-surface flex items-center gap-1.5">
              <span>{camera.camera_id}</span>
              {camera.ai_active && (
                <span className="bg-primary/20 text-primary text-[10px] px-1.5 py-0.5 rounded font-bold border border-primary/30">
                  AI ACTIVE
                </span>
              )}
            </div>
            <div className="font-body-xs text-on-surface-variant truncate max-w-[180px]">
              {camera.name || `Camera ${camera.camera_id}`}
            </div>
          </div>
          <span className={`px-2 py-0.5 rounded text-[11px] font-bold border flex items-center gap-1 ${badge.bg}`}>
            <span className="material-symbols-outlined text-[14px]">{badge.icon}</span>
            {badge.label}
          </span>
        </div>

        {/* Telemetry metadata */}
        <div className="space-y-1.5 pt-2 border-t border-outline-variant/10 font-body-xs text-on-surface-variant">
          <div className="flex justify-between">
            <span>Last Observed:</span>
            <span className="text-on-surface font-mono font-medium">
              {camera.last_successful_frame_at ? formatTimestamp(camera.last_successful_frame_at) : 'No frame'}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Attention:</span>
            <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold border ${getAttentionBadge(camera.attention_state)}`}>
              {camera.attention_state || 'NORMAL'}
            </span>
          </div>
          {camera.reconnect_count > 0 && (
            <div className="flex justify-between text-amber-400">
              <span>Reconnects:</span>
              <span className="font-bold">{camera.reconnect_count}</span>
            </div>
          )}
          {camera.consecutive_failures > 0 && (
            <div className="flex justify-between text-rose-400">
              <span>Read Failures:</span>
              <span className="font-bold">{camera.consecutive_failures}</span>
            </div>
          )}
          {camera.last_error && (
            <div className="text-[11px] text-rose-400 bg-rose-500/10 p-1.5 rounded mt-1 truncate">
              {camera.last_error}
            </div>
          )}
        </div>
      </div>

      <button
        onClick={() => onNavigate(camera.camera_id)}
        className="w-full py-1.5 bg-surface-container-high hover:bg-primary hover:text-on-primary text-on-surface rounded text-label-xs font-semibold flex items-center justify-center gap-1 transition-colors"
      >
        <span className="material-symbols-outlined text-[16px]">visibility</span>
        Monitor Stream
      </button>
    </div>
  );
}

function ComponentGrid({ health }: any) {
  const isHealthy = health.status === 'success' && health.data?.status === 'ok';
  const summary = health.data?.summary;

  const items = [
    { name: 'API Server', status: isHealthy ? 'OPERATIONAL' : 'DEGRADED', ok: isHealthy, icon: 'dns' },
    { name: 'Database', status: health.status === 'success' ? health.data?.database?.toUpperCase() : 'UNKNOWN', ok: isHealthy, icon: 'database' },
    { name: 'Camera Telemetry', status: `${summary?.online_count ?? 0}/${summary?.total_configured ?? 30} ONLINE`, ok: true, icon: 'videocam' },
    { name: 'AI Pipeline', status: 'READY (cam01)', ok: true, icon: 'speed' },
    { name: 'ANPR Engine', status: 'ACTIVE', ok: true, icon: 'document_scanner' },
    { name: 'Alert Engine', status: 'ACTIVE', ok: true, icon: 'notifications_active' },
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

function PipelineArchitecture() {
  const steps = ['RTSP Camera', 'CameraStream', 'VehicleDetector', 'ByteTrack', 'ZoneCounter', 'ANPR Engine', 'SQLite', 'AlertEngine', 'FastAPI', 'Frontend'];
  return (
    <div className="card">
      <div className="card-header">
        <h2 className="font-headline-sm text-on-surface font-bold">AI & Health Architecture</h2>
      </div>
      <div className="p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {steps.map((step, idx) => (
            <div key={step} className="flex items-center gap-2">
              <span className="px-3 py-1.5 bg-surface-container-lowest rounded border border-outline-variant/20 font-code-telemetry text-label-sm text-on-surface">
                {step}
              </span>
              {idx < steps.length - 1 && (
                <span className="material-symbols-outlined text-[16px] text-primary">arrow_forward</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
