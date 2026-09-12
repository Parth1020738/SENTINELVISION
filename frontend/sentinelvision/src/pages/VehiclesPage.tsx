import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useApi, formatTimestamp } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';
import InteractiveGisMap from '../components/InteractiveGisMap';
import {
  Camera,
  GlobalVehicle,
  GlobalVehicleTimelineResponse,
  GlobalVehicleRouteResponse,
  RoutePoint,
} from '../types';

export default function VehiclesPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'global' | 'local'>('global');

  // Camera Search & Filter State
  const [cameraSearch, setCameraSearch] = useState('');
  const [districtFilter, setDistrictFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [anprOnlyFilter, setAnprOnlyFilter] = useState(false);
  const [selectedCameraIdOnMap, setSelectedCameraIdOnMap] = useState<string | null>(null);

  // Global Vehicle Search State
  const [globalSearch, setGlobalSearch] = useState('');
  const [selectedGlobalId, setSelectedGlobalId] = useState<string | null>(null);

  // Sub-view mode for Global Vehicles: 'timeline' vs 'route'
  const [globalViewMode, setGlobalViewMode] = useState<'timeline' | 'route'>('timeline');

  // Local Canonical Vehicle Search State
  const [localSearchId, setLocalSearchId] = useState('');
  const [canonicalVehicleId, setCanonicalVehicleId] = useState<number | null>(null);

  // Export State
  const [exportingCsv, setExportingCsv] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);

  // Cameras metadata for GIS map
  const camerasApi = useApi(
    () => api.getCameras(),
    [],
    30000
  );

  // Global vehicles directory list
  const globalVehiclesList = useApi(
    () => api.getGlobalVehicles(100, 0),
    [],
    15000
  );

  // Selected global vehicle timeline
  const globalTimeline = useApi<GlobalVehicleTimelineResponse | null>(
    () => (selectedGlobalId ? api.getGlobalVehicleTimeline(selectedGlobalId) : Promise.resolve(null)),
    [selectedGlobalId],
    undefined
  );

  // Selected global vehicle GIS route
  const globalRoute = useApi<GlobalVehicleRouteResponse | null>(
    () => (selectedGlobalId ? api.getGlobalVehicleRoute(selectedGlobalId) : Promise.resolve(null)),
    [selectedGlobalId],
    undefined
  );

  // Local canonical vehicle event history
  const localHistory = useApi(
    () => (canonicalVehicleId !== null ? api.getVehicleHistory(canonicalVehicleId) : Promise.resolve([])),
    [canonicalVehicleId],
    undefined
  );

  const cameras = camerasApi.data || [];

  // Districts for filter dropdown
  const availableDistricts = Array.from(
    new Set(cameras.map((c) => c.district).filter((d): d is string => Boolean(d)))
  );

  // Filtered cameras
  const filteredCameras = cameras.filter((cam) => {
    const query = cameraSearch.toLowerCase().trim();
    if (query) {
      const nameMatch = (cam.name || '').toLowerCase().includes(query);
      const idMatch = cam.camera_id.toLowerCase().includes(query);
      if (!nameMatch && !idMatch) return false;
    }
    if (districtFilter !== 'ALL' && cam.district !== districtFilter) return false;
    if (statusFilter !== 'ALL') {
      const isOnline = cam.status === 'ONLINE' || cam.status === 'online' || cam.live;
      if (statusFilter === 'ONLINE' && !isOnline) return false;
      if (statusFilter === 'OFFLINE' && isOnline) return false;
    }
    if (anprOnlyFilter && cam.anpr_capable === false) return false;
    return true;
  });

  const handleGlobalSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!globalSearch.trim()) return;
    const query = globalSearch.trim();
    if (query.toUpperCase().startsWith('GV-')) {
      setSelectedGlobalId(query.toUpperCase());
    } else {
      try {
        const found = await api.searchGlobalVehicleByPlate(query);
        setSelectedGlobalId(found.global_vehicle_id);
      } catch {
        setSelectedGlobalId(query);
      }
    }
  };

  const handleLocalSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(localSearchId, 10);
    if (!isNaN(id)) {
      setCanonicalVehicleId(id);
    }
  };

  const handleExportCsv = async () => {
    try {
      setExportingCsv(true);
      await api.exportVehiclesCsv();
    } catch (err: any) {
      alert(`CSV Export Failed: ${err.message}`);
    } finally {
      setExportingCsv(false);
    }
  };

  const handleExportPdf = async () => {
    if (!selectedGlobalId) return;
    try {
      setExportingPdf(true);
      await api.exportVehiclePdf(selectedGlobalId);
    } catch (err: any) {
      alert(`PDF Export Failed: ${err.message}`);
    } finally {
      setExportingPdf(false);
    }
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      {/* Header Banner */}
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">
              GUJARAT CCTV COMMAND CENTER
            </span>
          </div>
          <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">
            GIS Camera Network & Vehicle Route Intelligence
          </h1>
          <p className="font-body-sm text-on-surface-variant">
            Command map visualization, multi-camera vehicle route tracking, and authenticated evidence exports.
          </p>
        </div>

        {/* Global CSV Evidence Export Button */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportCsv}
            disabled={exportingCsv}
            className="btn-primary py-2 px-4 text-xs flex items-center gap-2 font-bold"
          >
            <span className="material-symbols-outlined text-[18px]">download</span>
            {exportingCsv ? 'Exporting CSV...' : 'Export Vehicles CSV'}
          </button>
        </div>
      </div>

      {/* Main Tab Navigation */}
      <div className="flex gap-4 border-b border-outline-variant/20 bg-surface-container-low px-4 pt-3 rounded-t-lg">
        <button
          onClick={() => setActiveTab('global')}
          className={`pb-3 px-2 font-label-md font-bold transition-colors flex items-center gap-2 ${
            activeTab === 'global'
              ? 'text-primary border-b-2 border-primary'
              : 'text-on-surface-variant hover:text-on-surface'
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">map</span>
          GIS Map & Cross-Camera Intelligence
        </button>
        <button
          onClick={() => setActiveTab('local')}
          className={`pb-3 px-2 font-label-md font-bold transition-colors flex items-center gap-2 ${
            activeTab === 'local'
              ? 'text-primary border-b-2 border-primary'
              : 'text-on-surface-variant hover:text-on-surface'
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">query_stats</span>
          Camera-Local Track Query
        </button>
      </div>

      {/* TAB 1: GIS MAP & GLOBAL VEHICLE ROUTE */}
      {activeTab === 'global' && (
        <div className="flex flex-col gap-6">
          {/* Top GIS Map Command Section */}
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Map Component */}
            <div className="lg:w-2/3 flex flex-col gap-3">
              <InteractiveGisMap
                cameras={filteredCameras}
                selectedCameraId={selectedCameraIdOnMap}
                routePoints={globalRoute.data?.points || []}
                vehiclePlate={globalRoute.data?.normalized_plate}
                onSelectCamera={(id) => setSelectedCameraIdOnMap(id)}
                onViewLiveCamera={(id) => navigate(`/live?camera=${id}`)}
              />
            </div>

            {/* Camera Network Search & Filters Panel */}
            <div className="lg:w-1/3 card p-4 flex flex-col gap-4 bg-surface-container-low border border-outline-variant/20">
              <div className="flex items-center justify-between border-b border-outline-variant/20 pb-2">
                <h2 className="font-headline-sm text-on-surface font-bold text-sm flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary text-[18px]">filter_list</span>
                  Camera Network Filter ({filteredCameras.length}/{cameras.length})
                </h2>
                <button
                  onClick={() => {
                    setCameraSearch('');
                    setDistrictFilter('ALL');
                    setStatusFilter('ALL');
                    setAnprOnlyFilter(false);
                  }}
                  className="text-xs text-primary hover:underline font-bold"
                >
                  Reset
                </button>
              </div>

              {/* Controls */}
              <div className="flex flex-col gap-3 text-xs">
                <input
                  type="text"
                  value={cameraSearch}
                  onChange={(e) => setCameraSearch(e.target.value)}
                  placeholder="Search camera by name or ID (e.g. cam01)..."
                  className="input-field text-xs py-2 px-3"
                />

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-on-surface-variant font-medium block mb-1">District</label>
                    <select
                      value={districtFilter}
                      onChange={(e) => setDistrictFilter(e.target.value)}
                      className="input-field text-xs py-1.5 px-2 w-full"
                    >
                      <option value="ALL">All Districts</option>
                      {availableDistricts.map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-on-surface-variant font-medium block mb-1">Status</label>
                    <select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      className="input-field text-xs py-1.5 px-2 w-full"
                    >
                      <option value="ALL">All Statuses</option>
                      <option value="ONLINE">Online</option>
                      <option value="OFFLINE">Offline</option>
                    </select>
                  </div>
                </div>

                <label className="flex items-center gap-2 cursor-pointer pt-1 text-on-surface">
                  <input
                    type="checkbox"
                    checked={anprOnlyFilter}
                    onChange={(e) => setAnprOnlyFilter(e.target.checked)}
                    className="rounded text-primary focus:ring-primary"
                  />
                  <span>ANPR Capable Feeds Only</span>
                </label>
              </div>

              {/* Camera List */}
              <div className="flex-1 max-h-[300px] overflow-y-auto pr-1 flex flex-col gap-1.5 border-t border-outline-variant/10 pt-2">
                {filteredCameras.map((cam) => {
                  const hasCoords = cam.latitude !== null && cam.latitude !== undefined && cam.longitude !== null && cam.longitude !== undefined;
                  const isSelected = cam.camera_id === selectedCameraIdOnMap;
                  return (
                    <div
                      key={cam.camera_id}
                      onClick={() => setSelectedCameraIdOnMap(cam.camera_id)}
                      className={`p-2 rounded text-xs border flex items-center justify-between cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-primary/20 border-primary text-on-surface font-bold'
                          : 'bg-surface-container border-outline-variant/10 hover:bg-surface-container-high text-on-surface-variant'
                      }`}
                    >
                      <div className="flex items-center gap-2 truncate">
                        <span
                          className={`w-2 h-2 rounded-full flex-shrink-0 ${
                            cam.live || cam.status === 'online' ? 'bg-emerald-500' : 'bg-rose-500'
                          }`}
                        />
                        <span className="font-code-telemetry font-bold text-on-surface">{cam.camera_id}</span>
                        <span className="truncate">{cam.name || `Camera ${cam.camera_id}`}</span>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        {hasCoords ? (
                          <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded font-mono">
                            GIS OK
                          </span>
                        ) : (
                          <span className="text-[10px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded font-mono">
                            Location Unavailable
                          </span>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/live?camera=${cam.camera_id}`);
                          }}
                          className="p-1 hover:text-primary transition-colors"
                          title="View Live Stream"
                        >
                          <span className="material-symbols-outlined text-[16px]">visibility</span>
                        </button>
                      </div>
                    </div>
                  );
                })}

                {filteredCameras.length === 0 && (
                  <div className="py-6 text-center text-xs text-on-surface-variant">
                    No cameras match the selected filters.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Bottom Section: Vehicle Directory & Route Intelligence */}
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Left Column: Vehicle Search & Directory */}
            <div className="lg:w-1/3 flex flex-col gap-4">
              <div className="card p-4">
                <form onSubmit={handleGlobalSearch} className="flex gap-2">
                  <input
                    type="text"
                    value={globalSearch}
                    onChange={(e) => setGlobalSearch(e.target.value)}
                    placeholder="Search plate or GV ID (e.g. HR19R6697, GV-000002)..."
                    className="input-field flex-1 text-sm py-2 px-3"
                  />
                  <button type="submit" className="btn-primary py-2 px-4 text-sm font-bold">
                    Search
                  </button>
                </form>
              </div>

              <div className="card p-4 flex-1 flex flex-col">
                <h2 className="font-headline-sm text-on-surface font-bold mb-3 flex items-center justify-between">
                  <span>Global Vehicle Directory</span>
                  <span className="text-xs font-normal text-on-surface-variant font-code-telemetry">
                    {globalVehiclesList.data?.count ?? 0} total
                  </span>
                </h2>

                {globalVehiclesList.status === 'loading' && <LoadingState message="Loading vehicle identities..." />}
                {globalVehiclesList.status === 'error' && (
                  <ErrorState message={globalVehiclesList.error} onRetry={globalVehiclesList.refresh} />
                )}
                {globalVehiclesList.status === 'success' && globalVehiclesList.data && (
                  <>
                    {globalVehiclesList.data.results.length === 0 ? (
                      <EmptyState
                        icon="directions_car"
                        title="No vehicle movement recorded"
                        description="No vehicle movement recorded for the selected period. Vehicle identities will populate automatically upon ANPR plate read."
                      />
                    ) : (
                      <div className="flex flex-col gap-2 max-h-[500px] overflow-y-auto pr-1">
                        {globalVehiclesList.data.results.map((gv: GlobalVehicle) => {
                          const isSelected = selectedGlobalId === gv.global_vehicle_id;
                          return (
                            <div
                              key={gv.global_vehicle_id}
                              onClick={() => setSelectedGlobalId(gv.global_vehicle_id)}
                              className={`p-3 rounded-lg border cursor-pointer transition-all ${
                                isSelected
                                  ? 'bg-primary-container/20 border-primary shadow-sm'
                                  : 'bg-surface-container-low border-outline-variant/20 hover:bg-surface-container-high'
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-code-telemetry text-sm font-bold text-primary">
                                  {gv.global_vehicle_id}
                                </span>
                                <span className="bg-surface-container-highest px-2 py-0.5 rounded font-code-telemetry text-xs font-bold text-on-surface">
                                  {gv.normalized_plate || 'UNRESOLVED'}
                                </span>
                              </div>
                              <div className="flex justify-between items-center mt-2 text-xs text-on-surface-variant">
                                <span>Class: {gv.vehicle_class || 'car'}</span>
                                <span>Last: {formatTimestamp(gv.last_seen_at)}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* Right Column: Selected Vehicle Route Details */}
            <div className="lg:w-2/3">
              <div className="card h-full p-4 flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-outline-variant/20 pb-3">
                  <div className="flex items-center gap-3">
                    <h2 className="font-headline-sm text-on-surface font-bold">
                      Vehicle Intelligence & Route Details
                    </h2>
                    {selectedGlobalId && (
                      <button
                        onClick={handleExportPdf}
                        disabled={exportingPdf}
                        className="px-3 py-1 bg-surface-container-high hover:bg-surface-container-highest text-on-surface rounded border border-outline-variant/30 text-xs font-bold flex items-center gap-1.5 transition-colors"
                      >
                        <span className="material-symbols-outlined text-[16px] text-rose-400">picture_as_pdf</span>
                        {exportingPdf ? 'Exporting...' : 'PDF Report'}
                      </button>
                    )}
                  </div>

                  {selectedGlobalId && (
                    <div className="flex bg-surface-container-low p-1 rounded-lg border border-outline-variant/20">
                      <button
                        onClick={() => setGlobalViewMode('timeline')}
                        className={`px-3 py-1 text-xs font-bold rounded transition-colors ${
                          globalViewMode === 'timeline'
                            ? 'bg-primary text-on-primary'
                            : 'text-on-surface-variant hover:text-on-surface'
                        }`}
                      >
                        Timeline View
                      </button>
                      <button
                        onClick={() => setGlobalViewMode('route')}
                        className={`px-3 py-1 text-xs font-bold rounded transition-colors ${
                          globalViewMode === 'route'
                            ? 'bg-primary text-on-primary'
                            : 'text-on-surface-variant hover:text-on-surface'
                        }`}
                      >
                        Node Route Vector
                      </button>
                    </div>
                  )}
                </div>

                {!selectedGlobalId ? (
                  <EmptyState
                    icon="route"
                    title="Select a vehicle"
                    description="Select a global vehicle identity from the directory or search by plate to inspect its chronological camera route."
                  />
                ) : (
                  <>
                    {/* View 1: Timeline */}
                    {globalViewMode === 'timeline' && (
                      <>
                        {globalTimeline.status === 'loading' && <LoadingState message="Fetching movement timeline..." />}
                        {globalTimeline.status === 'error' && (
                          <ErrorState message={globalTimeline.error} onRetry={globalTimeline.refresh} />
                        )}
                        {globalTimeline.status === 'success' && globalTimeline.data && (
                          <div className="flex flex-col gap-4">
                            {/* Summary Card */}
                            <div className="bg-surface-container-low p-4 rounded-lg border border-outline-variant/20 flex flex-wrap gap-4 justify-between items-center">
                              <div>
                                <div className="font-code-telemetry text-lg font-bold text-primary">
                                  {globalTimeline.data.global_vehicle_id}
                                </div>
                                <div className="text-sm font-bold text-on-surface">
                                  Plate: <span className="font-code-telemetry">{globalTimeline.data.normalized_plate}</span>
                                </div>
                              </div>
                              <div className="text-xs text-on-surface-variant space-y-1 text-right">
                                <div>Class: <span className="font-bold text-on-surface">{globalTimeline.data.vehicle_class || 'car'}</span></div>
                                <div>Total Sightings: <span className="font-bold text-primary">{globalTimeline.data.observation_count}</span></div>
                              </div>
                            </div>

                            {/* Single Camera Case Warning */}
                            {globalTimeline.data.observation_count === 1 && (
                              <div className="bg-amber-500/10 border border-amber-500/30 text-amber-400 p-3 rounded-lg text-xs flex items-center gap-2 font-medium">
                                <span className="material-symbols-outlined text-[18px]">info</span>
                                Single camera observation. Multi-camera route polyline unavailable.
                              </div>
                            )}

                            {/* Sightings Table */}
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b border-outline-variant/20">
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Source Timestamp</th>
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Camera Feed</th>
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Track ID</th>
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Plate Read</th>
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">GIS Coordinates</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {globalTimeline.data.timeline.map((obs, idx) => {
                                    const pt = globalRoute.data?.points.find((p) => p.camera_id === obs.camera_id && p.timestamp === obs.timestamp);
                                    const hasCoords = pt?.latitude != null && pt?.longitude != null;
                                    return (
                                      <tr key={idx} className="border-b border-outline-variant/10 hover:bg-surface-container-low">
                                        <td className="py-2.5 px-3 font-code-telemetry text-xs text-on-surface-variant">
                                          {formatTimestamp(obs.timestamp)}
                                        </td>
                                        <td className="py-2.5 px-3">
                                          <span className="bg-primary/10 text-primary font-code-telemetry font-bold px-2 py-0.5 rounded text-xs">
                                            {obs.camera_id}
                                          </span>
                                        </td>
                                        <td className="py-2.5 px-3 font-code-telemetry text-xs text-on-surface">
                                          Track #{obs.canonical_vehicle_id}
                                        </td>
                                        <td className="py-2.5 px-3 font-code-telemetry text-xs font-bold text-secondary">
                                          {obs.normalized_plate || globalTimeline.data?.normalized_plate}
                                        </td>
                                        <td className="py-2.5 px-3 text-xs">
                                          {hasCoords ? (
                                            <span className="font-mono text-emerald-400">
                                              {pt!.latitude!.toFixed(4)}, {pt!.longitude!.toFixed(4)}
                                            </span>
                                          ) : (
                                            <span className="text-amber-400 font-mono text-[11px] bg-amber-500/10 px-1.5 py-0.5 rounded">
                                              Location unavailable
                                            </span>
                                          )}
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </>
                    )}

                    {/* View 2: Node Route Vector */}
                    {globalViewMode === 'route' && (
                      <>
                        {globalRoute.status === 'loading' && <LoadingState message="Fetching route vector..." />}
                        {globalRoute.status === 'error' && (
                          <ErrorState message={globalRoute.error} onRetry={globalRoute.refresh} />
                        )}
                        {globalRoute.status === 'success' && globalRoute.data && (
                          <div className="flex flex-col gap-4">
                            <div className="p-4 bg-surface-container-low rounded-lg border border-outline-variant/20">
                              <div className="text-xs font-bold text-outline uppercase tracking-wider mb-4 flex items-center justify-between">
                                <span>Chronological Camera Vector Chain</span>
                                <span>{globalRoute.data.mapped_points_count} of {globalRoute.data.total_observations} waypoints mapped</span>
                              </div>

                              <div className="flex flex-wrap items-center gap-3">
                                {globalRoute.data.points.map((pt: RoutePoint, idx: number) => {
                                  const hasCoords = pt.latitude !== null && pt.longitude !== null;
                                  return (
                                    <div key={idx} className="flex items-center gap-3">
                                      <div
                                        className={`p-3 rounded-lg border flex flex-col gap-1 min-w-[160px] ${
                                          hasCoords
                                            ? 'bg-primary-container/20 border-primary shadow-sm'
                                            : 'bg-surface-container-high border-outline-variant/30 opacity-70'
                                        }`}
                                      >
                                        <div className="flex justify-between items-center">
                                          <span className="font-code-telemetry font-bold text-xs text-primary">
                                            {pt.camera_id}
                                          </span>
                                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-surface-container-highest text-on-surface">
                                            #{idx + 1}
                                          </span>
                                        </div>
                                        <div className="text-[11px] font-code-telemetry text-on-surface-variant truncate">
                                          {formatTimestamp(pt.timestamp)}
                                        </div>
                                        <div className="text-[10px] font-mono mt-1">
                                          {hasCoords ? (
                                            <span className="text-emerald-400">
                                              {pt.latitude!.toFixed(4)}, {pt.longitude!.toFixed(4)}
                                            </span>
                                          ) : (
                                            <span className="text-amber-400 font-bold">Location unavailable</span>
                                          )}
                                        </div>
                                      </div>

                                      {idx < globalRoute.data!.points.length - 1 && (
                                        <span className="material-symbols-outlined text-primary text-[20px]">
                                          east
                                        </span>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Camera-Local Track Query */}
      {activeTab === 'local' && (
        <div className="card p-6 flex flex-col gap-6">
          <form onSubmit={handleLocalSearch} className="flex gap-2 max-w-md">
            <input
              type="number"
              value={localSearchId}
              onChange={(e) => setLocalSearchId(e.target.value)}
              placeholder="Enter canonical track ID (e.g. 100)..."
              className="input-field flex-1 text-sm py-2 px-3"
            />
            <button type="submit" className="btn-primary py-2 px-4 text-sm font-bold">
              Query Track
            </button>
          </form>

          {canonicalVehicleId !== null && (
            <div>
              <h2 className="font-headline-sm text-on-surface font-bold mb-4">
                Local Event History for Canonical Track #{canonicalVehicleId}
              </h2>
              {localHistory.status === 'loading' && <LoadingState message="Fetching track events..." />}
              {localHistory.status === 'error' && <ErrorState message={localHistory.error} onRetry={localHistory.refresh} />}
              {localHistory.status === 'success' && localHistory.data && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-outline-variant/20">
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Timestamp</th>
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Camera</th>
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Class</th>
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Event Type</th>
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {localHistory.data.map((evt) => (
                        <tr key={evt.id} className="border-b border-outline-variant/10 hover:bg-surface-container-low">
                          <td className="py-2.5 px-3 font-code-telemetry text-xs text-on-surface-variant">
                            {formatTimestamp(evt.timestamp)}
                          </td>
                          <td className="py-2.5 px-3 font-code-telemetry font-bold text-primary text-xs">
                            {evt.camera_id}
                          </td>
                          <td className="py-2.5 px-3 text-xs">{evt.vehicle_class}</td>
                          <td className="py-2.5 px-3 text-xs">{evt.event_type}</td>
                          <td className="py-2.5 px-3 font-mono text-xs">{evt.confidence ? (evt.confidence * 100).toFixed(1) + '%' : 'N/A'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
