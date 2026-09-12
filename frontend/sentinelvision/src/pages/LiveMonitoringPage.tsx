import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { useApi, useEventStream } from '../hooks';
import { Camera } from '../types';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import LiveCameraPlayer from '../components/LiveCameraPlayer';

export default function LiveMonitoringPage() {
  const [selectedCameraId, setSelectedCameraId] = useState<string>('cam01');
  const camerasApi = useApi(() => api.getCameras(selectedCameraId), [selectedCameraId], 15000);
  const { connectionStatus, subscribe } = useEventStream();

  const cameras: Camera[] = camerasApi.data || [];
  
  // Resolve selected camera, fallback to first if selected camera not found
  const selectedCamera =
    cameras.find((c) => c.camera_id === selectedCameraId) ||
    cameras[0] ||
    null;

  const currentCamId = selectedCamera?.camera_id || 'cam01';
  const countsApi = useApi(() => api.getCounts({ camera_id: currentCamId }), [currentCamId], 10000);

  useEffect(() => {
    const unsubscribe = subscribe((event) => {
      if (['attention_changed', 'alert_created', 'alert_status_changed', 'zone_count_changed', 'camera_status_changed'].includes(event.event_type)) {
        camerasApi.refresh();
        countsApi.refresh();
      }
    });
    return unsubscribe;
  }, [subscribe, camerasApi, countsApi]);

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <HeaderSection
        totalCameras={cameras.length}
        aiActiveCount={cameras.filter((c) => c.ai_active || c.camera_id === currentCamId).length}
        isLoading={camerasApi.status === 'loading'}
        connectionStatus={connectionStatus}
      />

      {camerasApi.status === 'loading' && cameras.length === 0 && (
        <LoadingState message="Discovering dynamic camera catalogue..." />
      )}

      {camerasApi.status === 'error' && cameras.length === 0 && (
        <ErrorState
          message={camerasApi.error || 'Failed to fetch camera catalogue'}
          onRetry={camerasApi.refresh}
        />
      )}

      {cameras.length > 0 && (
        <>
          {/* Camera Grid Section */}
          <CameraGridSection
            cameras={cameras}
            selectedCameraId={currentCamId}
            onSelectCamera={(id) => setSelectedCameraId(id)}
          />

          {/* Selected Camera Inspector & Stream Details */}
          <SelectedCameraInspector
            camera={selectedCamera}
            countsApi={countsApi}
          />
        </>
      )}

      <SecurityNotice />
    </div>
  );
}

function HeaderSection({
  totalCameras,
  aiActiveCount,
  isLoading,
  connectionStatus,
}: {
  totalCameras: number;
  aiActiveCount: number;
  isLoading: boolean;
  connectionStatus: string;
}) {
  return (
    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-surface-container-low p-4 rounded-lg shadow-sm border border-outline-variant/30">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">
            DYNAMIC CAMERA CATALOGUE
          </span>
          <span className="inline-block w-2 h-2 rounded-full bg-secondary animate-pulse" />
          <span className="font-code-telemetry text-label-sm text-secondary font-semibold">
            {isLoading ? 'DISCOVERING...' : `${totalCameras} DISCOVERED`}
          </span>
        </div>
        <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">
          Live CCTV Camera Grid
        </h1>
        <p className="font-body-sm text-on-surface-variant">
          Multi-camera surveillance catalogue with AI-powered detection monitoring.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 bg-surface-container px-3 py-1.5 rounded-md border border-outline-variant/40">
          <span className="material-symbols-outlined text-[18px] text-primary">sensors</span>
          <span className="font-label-sm text-on-surface">Realtime Events:</span>
          <span
            className={`font-code-telemetry text-label-sm font-bold ${
              connectionStatus === 'CONNECTED'
                ? 'text-secondary'
                : connectionStatus === 'RECONNECTING'
                ? 'text-warning'
                : 'text-on-surface-variant'
            }`}
          >
            {connectionStatus}
          </span>
        </div>
        <div className="flex items-center gap-2 bg-surface-container px-3 py-1.5 rounded-md border border-outline-variant/40">
          <span className="material-symbols-outlined text-[18px] text-primary">analytics</span>
          <span className="font-label-sm text-on-surface">AI Active:</span>
          <span className="font-code-telemetry text-label-sm text-primary font-bold">
            {aiActiveCount}
          </span>
        </div>
        <div className="flex items-center gap-2 bg-surface-container px-3 py-1.5 rounded-md border border-outline-variant/40">
          <span className="material-symbols-outlined text-[18px] text-secondary">videocam</span>
          <span className="font-label-sm text-on-surface">Total:</span>
          <span className="font-code-telemetry text-label-sm text-secondary font-bold">
            {totalCameras}
          </span>
        </div>
      </div>
    </div>
  );
}

function CameraGridSection({
  cameras,
  selectedCameraId,
  onSelectCamera,
}: {
  cameras: Camera[];
  selectedCameraId: string;
  onSelectCamera: (id: string) => void;
}) {
  const [filterQuery, setFilterQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<'all' | 'real' | 'virtual'>('all');

  const realCount = cameras.filter((c) => !c.is_virtual && !c.camera_id.startsWith('v_cam')).length;
  const virtualCount = cameras.filter((c) => c.is_virtual || c.camera_id.startsWith('v_cam')).length;

  const categoryFiltered = cameras.filter((c) => {
    const isVirt = c.is_virtual || c.camera_id.startsWith('v_cam');
    if (activeCategory === 'real') return !isVirt;
    if (activeCategory === 'virtual') return isVirt;
    return true;
  });

  const filtered = categoryFiltered.filter(
    (c) =>
      c.camera_id.toLowerCase().includes(filterQuery.toLowerCase()) ||
      (c.name && c.name.toLowerCase().includes(filterQuery.toLowerCase())) ||
      (c.location && c.location.toLowerCase().includes(filterQuery.toLowerCase()))
  );

  const priorityWeight = (state?: string) => {
    if (state === 'CRITICAL') return 0;
    if (state === 'WATCH') return 1;
    return 2;
  };

  const sortedFiltered = [...filtered].sort((a, b) => {
    const pA = priorityWeight(a.attention_state);
    const pB = priorityWeight(b.attention_state);
    if (pA !== pB) return pA - pB;
    return a.camera_id.localeCompare(b.camera_id);
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-surface-container-low p-3.5 rounded-lg border border-outline-variant/30">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveCategory('all')}
            className={`px-3 py-1.5 rounded-md font-label-sm font-bold transition-colors cursor-pointer ${
              activeCategory === 'all'
                ? 'bg-primary text-on-primary shadow-sm'
                : 'bg-surface-container-high text-on-surface hover:bg-surface-container-highest'
            }`}
          >
            ALL CAMERAS ({cameras.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveCategory('real')}
            className={`px-3 py-1.5 rounded-md font-label-sm font-bold transition-colors cursor-pointer flex items-center gap-1.5 ${
              activeCategory === 'real'
                ? 'bg-secondary text-on-secondary shadow-sm'
                : 'bg-surface-container-high text-on-surface hover:bg-surface-container-highest'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">videocam</span>
            REAL GOVERNMENT ({realCount})
          </button>
          <button
            type="button"
            onClick={() => setActiveCategory('virtual')}
            className={`px-3 py-1.5 rounded-md font-label-sm font-bold transition-colors cursor-pointer flex items-center gap-1.5 ${
              activeCategory === 'virtual'
                ? 'bg-amber-600 text-white shadow-sm'
                : 'bg-surface-container-high text-amber-400 hover:bg-surface-container-highest'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">smart_display</span>
            DEMO / VIRTUAL ({virtualCount})
          </button>
        </div>

        <div className="relative max-w-xs w-full">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-[18px]">
            search
          </span>
          <input
            type="text"
            placeholder="Search cameras by ID or name..."
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            className="w-full bg-surface-container border border-outline-variant/50 rounded-md pl-9 pr-3 py-1.5 font-body-sm text-on-surface focus:outline-none focus:border-primary"
          />
        </div>
      </div>

      {sortedFiltered.length === 0 ? (
        <div className="card p-8 text-center text-on-surface-variant">
          No cameras match filter &quot;{filterQuery}&quot;.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 max-h-[520px] overflow-y-auto pr-1">
          {sortedFiltered.map((cam) => {
            const isSelected = cam.camera_id === selectedCameraId;
            return (
              <CameraCard
                key={cam.camera_id}
                camera={cam}
                isSelected={isSelected}
                onClick={() => onSelectCamera(cam.camera_id)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function CameraCard({
  camera,
  isSelected,
  onClick,
}: {
  camera: Camera;
  isSelected: boolean;
  onClick: () => void;
}) {
  const isOnline = camera.live || camera.status === 'online' || camera.status === 'available';
  const attention = camera.attention_state || 'NORMAL';
  const isAiActive = isSelected || camera.ai_active;
  const isVirtual = camera.is_virtual || camera.camera_id.startsWith('v_cam');

  let attentionBadgeClass = 'bg-surface-container-high text-on-surface-variant';
  if (attention === 'CRITICAL') {
    attentionBadgeClass = 'bg-error/20 text-error font-bold border border-error/40';
  } else if (attention === 'WATCH') {
    attentionBadgeClass = 'bg-warning/20 text-warning font-semibold border border-warning/40';
  }

  return (
    <div
      className={`card text-left p-3.5 flex flex-col justify-between gap-3 transition-all ${
        isSelected
          ? isVirtual
            ? 'ring-2 ring-amber-500 border-amber-500 bg-amber-500/10'
            : 'ring-2 ring-primary border-primary bg-primary-container/10'
          : isVirtual
          ? 'border-amber-500/30 bg-surface-container-low hover:border-amber-500/60'
          : 'border-outline-variant/40 bg-surface-container-low hover:border-primary/50'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 truncate">
          <span className={`material-symbols-outlined text-[18px] ${isVirtual ? 'text-amber-400' : 'text-primary'}`}>
            {isVirtual ? 'smart_display' : 'videocam'}
          </span>
          <span className="font-code-telemetry text-label-md text-on-surface font-bold truncate">
            {camera.camera_id}
          </span>
        </div>

        {isVirtual ? (
          <span className="bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] px-1.5 py-0.5 rounded font-bold tracking-wider">
            DEMO
          </span>
        ) : (
          <span
            className={`status-badge text-[10px] px-1.5 py-0.5 rounded font-semibold ${
              isOnline ? 'bg-secondary/20 text-secondary' : 'bg-error/20 text-error'
            }`}
          >
            {isOnline ? 'LIVE' : 'OFFLINE'}
          </span>
        )}
      </div>

      <div className="space-y-1">
        <h4 className="font-label-md text-on-surface font-semibold truncate">
          {camera.name || `Camera ${camera.camera_id}`}
        </h4>
        <p className="font-body-xs text-on-surface-variant truncate">
          {camera.location || 'Location Not Specified'}
        </p>
        {camera.attention_reason && (
          <p className="font-body-xs text-warning/90 font-medium truncate pt-0.5" title={camera.attention_reason}>
            {camera.attention_reason}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between gap-1 text-[11px] pt-1 border-t border-outline-variant/30">
        <div className="flex items-center gap-1 font-code-telemetry text-on-surface-variant text-[10px]">
          <span>{camera.resolution || (camera.width ? `${camera.width}x${camera.height}` : '720p')}</span>
          <span>•</span>
          <span>{camera.codec || 'H264'}</span>
        </div>

        <div className="flex items-center gap-1">
          {isAiActive ? (
            <span className="bg-primary/20 text-primary font-code-telemetry text-[10px] px-1.5 py-0.5 rounded font-bold">
              AI ACTIVE
            </span>
          ) : (
            <span className="bg-surface-container-high text-on-surface-variant font-code-telemetry text-[10px] px-1.5 py-0.5 rounded">
              AI INACTIVE
            </span>
          )}

          <span className={`text-[10px] px-1.5 py-0.5 rounded ${attentionBadgeClass}`}>
            {attention}
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={onClick}
        className={`w-full py-1.5 px-3 rounded text-label-xs font-bold uppercase tracking-wider flex items-center justify-center gap-1.5 transition-colors cursor-pointer ${
          isSelected
            ? 'bg-primary text-on-primary shadow-sm'
            : 'bg-surface-container-high text-on-surface hover:bg-primary/20 hover:text-primary'
        }`}
      >
        <span className="material-symbols-outlined text-[16px]">
          {isSelected ? 'visibility' : 'play_circle'}
        </span>
        <span>{isSelected ? 'WATCHING' : 'WATCH'}</span>
      </button>
    </div>
  );
}

function SelectedCameraInspector({
  camera,
  countsApi,
}: {
  camera: Camera | null;
  countsApi: any;
}) {
  if (!camera) return null;

  const isOnline = camera.live || camera.status === 'online' || camera.status === 'available';

  const isVirtual = camera.is_virtual || camera.camera_id.startsWith('v_cam');

  return (
    <div className="flex flex-col gap-4">
      {isVirtual && (
        <div className="bg-amber-500/15 border border-amber-500/40 rounded-lg p-3.5 flex items-center gap-3">
          <span className="material-symbols-outlined text-[24px] text-amber-400">smart_display</span>
          <div>
            <div className="font-label-sm text-amber-300 font-bold uppercase tracking-wider flex items-center gap-2">
              DEMO / VIRTUAL CAMERA SOURCE
              <span className="bg-amber-500 text-black text-[10px] px-1.5 py-0.2 rounded font-extrabold">DEMO MODE</span>
            </div>
            <p className="font-body-xs text-amber-200/80">
              Running through production AI pipeline (YOLO11m + ByteTrack + ANPREngine + EventHub) using recorded evaluation video.
            </p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h2 className="font-headline-sm text-on-surface font-bold">
          Selected Camera Inspector
        </h2>
        <span className={`font-code-telemetry text-label-sm font-semibold ${isVirtual ? 'text-amber-400' : 'text-primary'}`}>
          ID: {camera.camera_id} {isVirtual ? '(VIRTUAL)' : '(LIVE GOVERNMENT)'}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Real HLS Live Camera Player */}
        <LiveCameraPlayer
          cameraId={camera.camera_id}
          cameraName={camera.name}
          resolution={camera.resolution}
          aiActive={camera.ai_active}
        />

        {/* Camera Operational Details & Counts */}
        <div className="flex flex-col gap-4">
          <div className="card p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-2">
              <span className="font-label-sm text-outline uppercase tracking-wider">
                Operational Telemetry
              </span>
              <span className="material-symbols-outlined text-[20px] text-primary">
                tune
              </span>
            </div>

            <div className="space-y-2 font-body-sm">
              <div className="flex justify-between items-center">
                <span className="text-on-surface-variant">Camera ID</span>
                <span className="font-code-telemetry text-on-surface font-bold">
                  {camera.camera_id}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-on-surface-variant">Location</span>
                <span className="font-body-sm text-on-surface">
                  {camera.location || 'N/A'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-on-surface-variant">Resolution</span>
                <span className="font-code-telemetry text-on-surface">
                  {camera.resolution || '720p'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-on-surface-variant">Codec</span>
                <span className="font-code-telemetry text-on-surface">
                  {camera.codec || 'H264'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-on-surface-variant">AI Pipeline Status</span>
                <span
                  className={`font-code-telemetry text-label-sm font-bold ${
                    camera.ai_active ? 'text-primary' : 'text-on-surface-variant'
                  }`}
                >
                  {camera.ai_active ? `ACTIVE (${camera.camera_id})` : 'INACTIVE'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-on-surface-variant">Attention State</span>
                <span
                  className={`font-code-telemetry text-label-sm font-bold ${
                    camera.attention_state === 'CRITICAL'
                      ? 'text-error'
                      : camera.attention_state === 'WATCH'
                      ? 'text-warning'
                      : 'text-secondary'
                  }`}
                >
                  {camera.attention_state || 'NORMAL'}
                </span>
              </div>
              {camera.attention_reason && (
                <div className="flex justify-between items-center pt-1 border-t border-outline-variant/20">
                  <span className="text-on-surface-variant">Attention Reason</span>
                  <span className="font-body-xs text-on-surface italic text-right max-w-[200px] truncate" title={camera.attention_reason}>
                    {camera.attention_reason}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Counts Section */}
          <div className="card p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-2">
              <span className="font-label-sm text-outline uppercase tracking-wider">
                Traffic Counts ({camera.camera_id})
              </span>
              <span className="material-symbols-outlined text-[20px] text-secondary">
                analytics
              </span>
            </div>

            {countsApi.status === 'loading' && (
              <LoadingState message="Loading camera counts..." />
            )}

            {countsApi.status === 'error' && (
              <ErrorState
                message={countsApi.error || 'Counts unavailable'}
                onRetry={countsApi.refresh}
              />
            )}

            {countsApi.status === 'success' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-body-sm text-on-surface">Vehicle IN</span>
                  <span className="font-code-telemetry text-label-md text-secondary font-bold">
                    {countsApi.data?.total.IN ?? 0}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-body-sm text-on-surface">Vehicle OUT</span>
                  <span className="font-code-telemetry text-label-md text-primary font-bold">
                    {countsApi.data?.total.OUT ?? 0}
                  </span>
                </div>
              </div>
            )}
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
            RTSP credentials are isolated inside backend/camera/rtsp_credentials.py and never returned to the client. The dynamic camera catalogue provides safe operational metadata for monitoring.
          </p>
        </div>
      </div>
    </div>
  );
}
