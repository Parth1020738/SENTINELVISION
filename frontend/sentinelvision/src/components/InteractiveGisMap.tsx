import { useEffect, useRef } from 'react';
import { Camera, RoutePoint } from '../types';

interface InteractiveGisMapProps {
  cameras: Camera[];
  selectedCameraId?: string | null;
  routePoints?: RoutePoint[];
  vehiclePlate?: string | null;
  onSelectCamera?: (cameraId: string) => void;
}

export default function InteractiveGisMap({
  cameras,
  selectedCameraId,
  routePoints = [],
  vehiclePlate,
  onSelectCamera,
}: InteractiveGisMapProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Filter cameras that have valid coordinates
  const validCameras = cameras.filter(
    (c) => c.latitude !== null && c.latitude !== undefined && c.longitude !== null && c.longitude !== undefined
  );

  // Compute map bounding box
  const lats = validCameras.map((c) => c.latitude as number);
  const lngs = validCameras.map((c) => c.longitude as number);

  const minLat = lats.length > 0 ? Math.min(...lats) : 28.3;
  const maxLat = lats.length > 0 ? Math.max(...lats) : 28.6;
  const minLng = lngs.length > 0 ? Math.min(...lngs) : 76.8;
  const maxLng = lngs.length > 0 ? Math.max(...lngs) : 77.2;

  const latSpan = maxLat - minLat || 0.1;
  const lngSpan = maxLng - minLng || 0.1;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set high-DPI scaling
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * 2;
    canvas.height = rect.height * 2;
    ctx.scale(2, 2);

    const width = rect.width;
    const height = rect.height;
    const padding = 50;

    // Projection helper: lat/lng -> canvas x/y
    const project = (lat: number, lng: number) => {
      const x = padding + ((lng - minLng) / lngSpan) * (width - 2 * padding);
      const y = height - (padding + ((lat - minLat) / latSpan) * (height - 2 * padding));
      return { x, y };
    };

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Draw map background grid / tactical tiles
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, width, height);

    // Draw grid lines
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 40) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += 40) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Draw vehicle trajectory route if routePoints are provided
    const validRoute = routePoints.filter(
      (p) => p.latitude !== null && p.latitude !== undefined && p.longitude !== null && p.longitude !== undefined
    );

    if (validRoute.length > 1) {
      ctx.beginPath();
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 3;
      ctx.setLineDash([6, 4]);

      validRoute.forEach((pt, idx) => {
        const { x, y } = project(pt.latitude!, pt.longitude!);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]); // Reset line dash

      // Draw directional route point numbers
      validRoute.forEach((pt, idx) => {
        const { x, y } = project(pt.latitude!, pt.longitude!);
        ctx.fillStyle = idx === 0 ? '#10b981' : idx === validRoute.length - 1 ? '#ef4444' : '#0284c7';
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, 2 * Math.PI);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${idx + 1}`, x, y);
      });
    }

    // Draw camera markers
    validCameras.forEach((cam) => {
      const { x, y } = project(cam.latitude!, cam.longitude!);
      const isSelected = cam.camera_id === selectedCameraId;
      const isOnline = cam.live || cam.status === 'online' || cam.status === 'available';

      // Pulse ring for selected camera
      if (isSelected) {
        ctx.beginPath();
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 2;
        ctx.arc(x, y, 14, 0, 2 * Math.PI);
        ctx.stroke();
      }

      // Marker Circle
      ctx.beginPath();
      ctx.fillStyle = isSelected ? '#0284c7' : isOnline ? '#10b981' : '#f43f5e';
      ctx.arc(x, y, isSelected ? 9 : 6, 0, 2 * Math.PI);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Camera Label
      ctx.fillStyle = isSelected ? '#38bdf8' : '#e2e8f0';
      ctx.font = isSelected ? 'bold 11px monospace' : '10px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(cam.camera_id, x, y - (isSelected ? 14 : 10));
    });
  }, [cameras, selectedCameraId, routePoints, minLat, maxLat, minLng, maxLng, latSpan, lngSpan]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !onSelectCamera) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const width = rect.width;
    const height = rect.height;
    const padding = 50;

    const project = (lat: number, lng: number) => {
      const x = padding + ((lng - minLng) / lngSpan) * (width - 2 * padding);
      const y = height - (padding + ((lat - minLat) / latSpan) * (height - 2 * padding));
      return { x, y };
    };

    // Find clicked camera marker
    for (const cam of validCameras) {
      const { x, y } = project(cam.latitude!, cam.longitude!);
      const dist = Math.hypot(clickX - x, clickY - y);
      if (dist <= 15) {
        onSelectCamera(cam.camera_id);
        break;
      }
    }
  };

  return (
    <div className="card overflow-hidden border border-outline-variant/30 flex flex-col bg-surface-container-lowest">
      {/* Map Header */}
      <div className="p-3 bg-surface-container-low border-b border-outline-variant/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">map</span>
          <span className="font-headline-sm text-on-surface font-bold text-sm">
            Interactive GIS Tactical Command Map
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs font-code-telemetry text-on-surface-variant">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            Online ({cameras.filter((c) => c.live || c.status === 'online').length})
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            Offline ({cameras.filter((c) => !c.live && c.status !== 'online').length})
          </span>
          {vehiclePlate && (
            <span className="bg-primary/20 text-primary font-bold px-2 py-0.5 rounded">
              Route: {vehiclePlate}
            </span>
          )}
        </div>
      </div>

      {/* Interactive Map Canvas */}
      <div className="relative aspect-[21/9] w-full bg-slate-950 flex items-center justify-center">
        <canvas
          ref={canvasRef}
          onClick={handleClick}
          className="w-full h-full cursor-pointer block"
        />

        {/* Floating Controls Overlay */}
        <div className="absolute bottom-3 left-3 bg-slate-900/90 backdrop-blur border border-slate-700/60 p-2 rounded-md text-[11px] font-code-telemetry text-slate-300 flex items-center gap-4">
          <span>Map Provider: OpenStreetMap / GIS Vector Layer</span>
          <span>Coverage: Haryana State Police Surveillance Grid</span>
          <span>Mapped Nodes: {validCameras.length} / {cameras.length}</span>
        </div>
      </div>

      {/* Map Footer */}
      <div className="p-2.5 bg-surface-container-low border-t border-outline-variant/30 flex items-center justify-between text-body-xs text-on-surface-variant">
        <span>Click any camera node marker to select and inspect live telemetry.</span>
        <span className="font-code-telemetry text-[10px] text-outline">
          Bounding Box: [{minLat.toFixed(2)}°N, {minLng.toFixed(2)}°E] - [{maxLat.toFixed(2)}°N, {maxLng.toFixed(2)}°E]
        </span>
      </div>
    </div>
  );
}
