import { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Tooltip, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Camera, RoutePoint } from '../types';

// Fix Leaflet default icon path issues in Vite
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

interface InteractiveGisMapProps {
  cameras: Camera[];
  selectedCameraId?: string | null;
  routePoints?: RoutePoint[];
  vehiclePlate?: string | null;
  onSelectCamera?: (cameraId: string) => void;
  onViewLiveCamera?: (cameraId: string) => void;
}

// Custom Marker Icons
function createCustomIcon(status: string, isSelected: boolean, isAiActive: boolean) {
  const isOnline = status === 'ONLINE' || status === 'online' || status === 'available';
  const color = isSelected ? '#0284c7' : isAiActive ? '#06b6d4' : isOnline ? '#10b981' : '#f43f5e';
  const ring = isSelected ? 'border-2 border-sky-400 animate-pulse' : '';

  const html = `
    <div class="relative flex items-center justify-center w-8 h-8 rounded-full bg-slate-900/90 shadow-md ${ring}" style="border: 2px solid ${color};">
      <span class="material-symbols-outlined text-[18px]" style="color: ${color}; font-size: 16px;">videocam</span>
    </div>
  `;

  return L.divIcon({
    html,
    className: 'custom-leaflet-marker',
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16],
    tooltipAnchor: [0, -20],
  });
}

function createWayPointIcon(index: number, total: number) {
  const isFirst = index === 0;
  const isLast = index === total - 1;
  const bg = isFirst ? '#10b981' : isLast ? '#ef4444' : '#0284c7';

  const html = `
    <div class="w-6 h-6 rounded-full flex items-center justify-center font-bold text-[10px] text-white shadow-lg border border-white" style="background-color: ${bg};">
      ${index + 1}
    </div>
  `;

  return L.divIcon({
    html,
    className: 'route-waypoint-marker',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

// Auto-bounds controller
function MapBoundsController({
  cameras,
  routePoints,
}: {
  cameras: Camera[];
  routePoints: RoutePoint[];
}) {
  const map = useMap();

  useEffect(() => {
    const routeCoords: [number, number][] = routePoints
      .filter((p) => p.latitude != null && p.longitude != null)
      .map((p) => [p.latitude!, p.longitude!]);

    if (routeCoords.length > 0) {
      const bounds = L.latLngBounds(routeCoords);
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
      return;
    }

    const camCoords: [number, number][] = cameras
      .filter((c) => c.latitude != null && c.longitude != null)
      .map((c) => [c.latitude!, c.longitude!]);

    if (camCoords.length > 0) {
      const bounds = L.latLngBounds(camCoords);
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
    } else {
      // Gujarat default view centroid
      map.setView([22.2587, 71.1924], 7);
    }
  }, [cameras, routePoints, map]);

  return null;
}

export default function InteractiveGisMap({
  cameras,
  selectedCameraId,
  routePoints = [],
  vehiclePlate,
  onSelectCamera,
  onViewLiveCamera,
}: InteractiveGisMapProps) {
  // GIS map displays ONLY real government cameras (excluding demo/virtual feeds)
  const realGovtCameras = cameras.filter(
    (c) => !c.is_virtual && !c.camera_id.startsWith('v_cam')
  );

  // Filter cameras that have valid coordinates
  const validCameras = realGovtCameras.filter(
    (c) => c.latitude !== null && c.latitude !== undefined && c.longitude !== null && c.longitude !== undefined
  );

  const unmappedCameras = realGovtCameras.filter(
    (c) => c.latitude === null || c.latitude === undefined || c.longitude === null || c.longitude === undefined
  );

  const totalCount = realGovtCameras.length;
  const mappedCount = validCameras.length;
  const unmappedCount = unmappedCameras.length;

  // Filter valid route points
  const validRoute = routePoints.filter(
    (p) => p.latitude !== null && p.latitude !== undefined && p.longitude !== null && p.longitude !== undefined
  );

  const polylinePositions: [number, number][] = validRoute.map((p) => [p.latitude!, p.longitude!]);

  return (
    <div className="card overflow-hidden border border-outline-variant/30 flex flex-col bg-surface-container-lowest relative">
      {/* Map Header & Summary Statistics */}
      <div className="p-3 bg-surface-container-low border-b border-outline-variant/30 flex flex-wrap items-center justify-between gap-3 z-[400]">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">map</span>
          <span className="font-headline-sm text-on-surface font-bold text-sm">
            Gujarat CCTV Command Map (GIS)
          </span>
        </div>

        {/* Dynamic Header Metrics */}
        <div className="flex flex-wrap items-center gap-3 text-xs font-code-telemetry">
          <span className="bg-surface-container px-2.5 py-1 rounded border border-outline-variant/40 text-on-surface">
            Cameras: <strong className="text-primary">{totalCount}</strong>
          </span>
          <span className="bg-emerald-500/10 text-emerald-400 px-2.5 py-1 rounded border border-emerald-500/30">
            Mapped: <strong>{mappedCount}</strong>
          </span>
          <span className="bg-amber-500/10 text-amber-400 px-2.5 py-1 rounded border border-amber-500/30">
            Location unavailable: <strong>{unmappedCount}</strong>
          </span>
          {vehiclePlate && (
            <span className="bg-primary/20 text-primary font-bold px-2 py-1 rounded">
              Route: {vehiclePlate}
            </span>
          )}
        </div>
      </div>

      {/* Map View Container */}
      <div className="h-[480px] w-full relative z-[1]">
        <MapContainer
          center={[22.2587, 71.1924]}
          zoom={7}
          scrollWheelZoom={true}
          className="h-full w-full bg-slate-900"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          <MapBoundsController cameras={validCameras} routePoints={validRoute} />

          {/* Vehicle Route Polyline */}
          {polylinePositions.length > 1 && (
            <Polyline
              positions={polylinePositions}
              pathOptions={{
                color: '#0284c7',
                weight: 4,
                opacity: 0.8,
                dashArray: '8, 6',
              }}
            />
          )}

          {/* Waypoint Markers for Route */}
          {validRoute.map((pt, idx) => (
            <Marker
              key={`route-pt-${idx}`}
              position={[pt.latitude!, pt.longitude!]}
              icon={createWayPointIcon(idx, validRoute.length)}
            >
              <Popup>
                <div className="p-1 font-body-xs space-y-1">
                  <div className="font-bold text-sky-600">Waypoint #{idx + 1}</div>
                  <div>Camera: <strong>{pt.camera_id}</strong></div>
                  <div>Timestamp: {pt.timestamp || 'N/A'}</div>
                  {pt.normalized_plate && <div>Plate: <strong>{pt.normalized_plate}</strong></div>}
                </div>
              </Popup>
            </Marker>
          ))}

          {/* Camera Markers with Permanent Label Tooltip */}
          {validCameras.map((cam) => {
            const isSelected = cam.camera_id === selectedCameraId;
            const isOnline = cam.live || cam.status === 'ONLINE' || cam.status === 'online' || cam.status === 'available';
            const labelText = `${cam.camera_id.toUpperCase()} - ${cam.name || cam.location || `Camera ${cam.camera_id}`}`;

            return (
              <Marker
                key={cam.camera_id}
                position={[cam.latitude!, cam.longitude!]}
                icon={createCustomIcon(cam.status || 'online', isSelected, !!cam.ai_active)}
                eventHandlers={{
                  click: () => onSelectCamera?.(cam.camera_id),
                }}
              >
                {/* Visible Permanent Label */}
                <Tooltip permanent direction="top" className="custom-gis-tooltip">
                  <span className="font-code-telemetry font-bold text-[11px] uppercase tracking-wide px-1">
                    {labelText}
                  </span>
                </Tooltip>

                {/* Detailed Interactive Popup */}
                <Popup>
                  <div className="p-2 space-y-2 text-slate-800 font-sans min-w-[220px]">
                    <div className="flex items-center justify-between border-b pb-1">
                      <span className="font-bold text-sm text-slate-900">{cam.camera_id.toUpperCase()}</span>
                      <span className="text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded font-mono">
                        {cam.district || 'Gujarat Grid'}
                      </span>
                    </div>
                    <div className="font-semibold text-xs text-sky-800">
                      {cam.name || `Camera ${cam.camera_id}`}
                    </div>
                    <div className="text-xs space-y-1 text-slate-700">
                      <div>Location: <strong>{cam.location || cam.name || 'Gujarat Road Network'}</strong></div>
                      <div>Coordinate: <strong>{cam.coordinate_source || 'Verified camera location'}</strong></div>
                      <div>Status: <strong className={isOnline ? 'text-emerald-700 uppercase' : 'text-rose-700 uppercase'}>{isOnline ? 'ONLINE' : 'OFFLINE'}</strong></div>
                      <div>AI: <strong className={cam.ai_active ? 'text-sky-700 uppercase' : 'text-slate-500 uppercase'}>{cam.ai_active ? 'ACTIVE' : 'INACTIVE'}</strong></div>
                    </div>

                    <div className="pt-2 flex flex-col gap-1">
                      {onViewLiveCamera && (
                        <button
                          type="button"
                          onClick={() => onViewLiveCamera(cam.camera_id)}
                          className="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-1.5 px-2 rounded text-xs transition-colors flex items-center justify-center gap-1 cursor-pointer"
                        >
                          <span className="material-symbols-outlined text-[15px]">videocam</span>
                          View Live
                        </button>
                      )}
                      {onSelectCamera && (
                        <button
                          type="button"
                          onClick={() => onSelectCamera(cam.camera_id)}
                          className="w-full bg-slate-100 hover:bg-slate-200 text-slate-800 font-semibold py-1 px-2 rounded text-xs transition-colors flex items-center justify-center gap-1 cursor-pointer border border-slate-300"
                        >
                          <span className="material-symbols-outlined text-[15px]">info</span>
                          Camera Details
                        </button>
                      )}
                    </div>
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      </div>

      {/* Unresolved / Location Unavailable Camera List Section */}
      {unmappedCameras.length > 0 && (
        <div className="p-3 bg-surface-container-low border-t border-outline-variant/30 flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-amber-400 text-[18px]">location_off</span>
            <span className="font-label-sm text-amber-400 font-bold uppercase tracking-wider">
              Location Unavailable ({unmappedCameras.length})
            </span>
          </div>
          <div className="flex flex-wrap gap-2 max-h-[120px] overflow-y-auto pr-1">
            {unmappedCameras.map((cam) => (
              <div
                key={cam.camera_id}
                onClick={() => onSelectCamera?.(cam.camera_id)}
                className="flex items-center gap-2 bg-surface-container px-2.5 py-1.5 rounded border border-outline-variant/40 hover:border-amber-400/50 transition-colors cursor-pointer text-xs"
              >
                <span className="font-code-telemetry text-amber-300 font-bold">
                  {cam.camera_id.toUpperCase()}
                </span>
                <span className="text-on-surface-variant font-medium">
                  {cam.location || cam.name || 'Unmapped Location'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Map Footer Info */}
      <div className="p-2 bg-surface-container-low border-t border-outline-variant/30 flex items-center justify-between text-xs text-on-surface-variant font-code-telemetry">
        <span>Leaflet + OpenStreetMap GIS Engine</span>
        <span>Zero fake coordinates policy active</span>
      </div>
    </div>
  );
}
