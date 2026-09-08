import { useState } from 'react';
import { api } from '../api/client';
import { useApi, formatTimestamp } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';
import {
  GlobalVehicle,
  GlobalVehicleTimelineResponse,
  GlobalVehicleRouteResponse,
  RoutePoint,
} from '../types';

export default function VehiclesPage() {
  const [activeTab, setActiveTab] = useState<'global' | 'local'>('global');
  
  // Global Vehicle Search State
  const [globalSearch, setGlobalSearch] = useState('');
  const [selectedGlobalId, setSelectedGlobalId] = useState<string | null>(null);

  // Sub-view mode for Global Vehicles: 'timeline' vs 'route'
  const [globalViewMode, setGlobalViewMode] = useState<'timeline' | 'route'>('timeline');

  // Local Canonical Vehicle Search State
  const [localSearchId, setLocalSearchId] = useState('');
  const [localSearchTriggered, setLocalSearchTriggered] = useState(false);
  const [canonicalVehicleId, setCanonicalVehicleId] = useState<number | null>(null);

  // Global vehicles directory list
  const globalVehiclesList = useApi(
    () => api.getGlobalVehicles(50, 0),
    [],
    undefined
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
      setLocalSearchTriggered(true);
    }
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      {/* Header */}
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">
            VEHICLE INTELLIGENCE HUB
          </span>
        </div>
        <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">
          Cross-Camera Vehicle Intelligence & GIS Route
        </h1>
        <p className="font-body-sm text-on-surface-variant">
          Track global vehicle identities, cross-camera timelines, and geographical camera movement routes.
        </p>

        {/* Tab Selection */}
        <div className="flex gap-4 mt-4 border-b border-outline-variant/20">
          <button
            onClick={() => setActiveTab('global')}
            className={`pb-2 px-1 font-label-md font-bold transition-colors ${
              activeTab === 'global'
                ? 'text-primary border-b-2 border-primary'
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            Global Cross-Camera & GIS Route
          </button>
          <button
            onClick={() => setActiveTab('local')}
            className={`pb-2 px-1 font-label-md font-bold transition-colors ${
              activeTab === 'local'
                ? 'text-primary border-b-2 border-primary'
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            Camera-Local Track Query
          </button>
        </div>
      </div>

      {/* TAB 1: Global Cross-Camera & GIS Route */}
      {activeTab === 'global' && (
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Left Panel: Global Vehicle Directory & Search */}
          <div className="lg:w-1/3 flex flex-col gap-4">
            <div className="card p-4">
              <form onSubmit={handleGlobalSearch} className="flex gap-2">
                <input
                  type="text"
                  value={globalSearch}
                  onChange={(e) => setGlobalSearch(e.target.value)}
                  placeholder="Search by plate or GV ID (e.g. GJ01AB1234, GV-000001)..."
                  className="input-field flex-1 text-sm"
                />
                <button type="submit" className="btn-primary py-2 px-4 text-sm">
                  Search
                </button>
              </form>
            </div>

            <div className="card p-4 flex-1">
              <h2 className="font-headline-sm text-on-surface font-bold mb-3">
                Global Vehicles Directory
              </h2>

              {globalVehiclesList.status === 'loading' && (
                <LoadingState message="Loading global vehicles..." />
              )}
              {globalVehiclesList.status === 'error' && (
                <ErrorState message={globalVehiclesList.error} onRetry={globalVehiclesList.refresh} />
              )}
              {globalVehiclesList.status === 'success' && globalVehiclesList.data && (
                <>
                  {globalVehiclesList.data.results.length === 0 ? (
                    <EmptyState
                      icon="directions_car"
                      title="No global vehicles recorded"
                      description="Global identities will populate automatically when ANPR plate reads are finalized."
                    />
                  ) : (
                    <div className="flex flex-col gap-2 max-h-[600px] overflow-y-auto pr-1">
                      {globalVehiclesList.data.results.map((gv: GlobalVehicle) => (
                        <div
                          key={gv.global_vehicle_id}
                          onClick={() => setSelectedGlobalId(gv.global_vehicle_id)}
                          className={`p-3 rounded-lg border cursor-pointer transition-all ${
                            selectedGlobalId === gv.global_vehicle_id
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
                            <span>Last Seen: {formatTimestamp(gv.last_seen_at)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Right Panel: Timeline & GIS Route View */}
          <div className="lg:w-2/3">
            <div className="card h-full p-4 flex flex-col gap-4">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-outline-variant/20 pb-3">
                <h2 className="font-headline-sm text-on-surface font-bold">
                  Vehicle Intelligence View
                </h2>

                {/* Sub-view switcher */}
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
                      Timeline List
                    </button>
                    <button
                      onClick={() => setGlobalViewMode('route')}
                      className={`px-3 py-1 text-xs font-bold rounded transition-colors ${
                        globalViewMode === 'route'
                          ? 'bg-primary text-on-primary'
                          : 'text-on-surface-variant hover:text-on-surface'
                      }`}
                    >
                      GIS Route Map
                    </button>
                  </div>
                )}
              </div>

              {!selectedGlobalId ? (
                <EmptyState
                  icon="map"
                  title="Select a vehicle"
                  description="Select a global vehicle from the directory or search by plate to view its multi-camera movement timeline and GIS route."
                />
              ) : (
                <>
                  {/* SUB-VIEW 1: Timeline List */}
                  {globalViewMode === 'timeline' && (
                    <>
                      {globalTimeline.status === 'loading' && (
                        <LoadingState message="Fetching movement timeline..." />
                      )}
                      {globalTimeline.status === 'error' && (
                        <ErrorState message={globalTimeline.error} onRetry={globalTimeline.refresh} />
                      )}
                      {globalTimeline.status === 'success' && globalTimeline.data && (
                        <div className="flex flex-col gap-4">
                          {/* Vehicle Header Info */}
                          <div className="bg-surface-container-low p-4 rounded-lg border border-outline-variant/20 flex flex-wrap gap-4 justify-between items-center">
                            <div>
                              <div className="font-code-telemetry text-lg font-bold text-primary">
                                {globalTimeline.data.global_vehicle_id}
                              </div>
                              <div className="text-sm font-bold text-on-surface">
                                Plate: <span className="font-code-telemetry">{globalTimeline.data.normalized_plate}</span>
                              </div>
                            </div>
                            <div className="text-xs text-on-surface-variant">
                              <div>Class: <span className="font-bold text-on-surface">{globalTimeline.data.vehicle_class || 'car'}</span></div>
                              <div>Observations: <span className="font-bold text-primary">{globalTimeline.data.observation_count}</span></div>
                            </div>
                          </div>

                          {/* Observations Table */}
                          {globalTimeline.data.timeline.length === 0 ? (
                            <EmptyState
                              icon="history"
                              title="No observations"
                              description="No cross-camera observations recorded for this identity yet."
                            />
                          ) : (
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b border-outline-variant/20">
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Source Timestamp</th>
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Camera Node</th>
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Canonical Track ID</th>
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Vehicle Class</th>
                                    <th className="text-left py-2 px-3 font-label-sm text-outline">Plate Signal</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {globalTimeline.data.timeline.map((obs, idx) => (
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
                                      <td className="py-2.5 px-3 text-xs text-on-surface">
                                        {obs.vehicle_class || 'car'}
                                      </td>
                                      <td className="py-2.5 px-3">
                                        <span className="font-code-telemetry text-xs font-bold text-secondary">
                                          {obs.normalized_plate}
                                        </span>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}

                  {/* SUB-VIEW 2: GIS Route Map */}
                  {globalViewMode === 'route' && (
                    <>
                      {globalRoute.status === 'loading' && (
                        <LoadingState message="Fetching GIS route points..." />
                      )}
                      {globalRoute.status === 'error' && (
                        <ErrorState message={globalRoute.error} onRetry={globalRoute.refresh} />
                      )}
                      {globalRoute.status === 'success' && globalRoute.data && (
                        <div className="flex flex-col gap-4">
                          {/* Route Summary Bar */}
                          <div className="bg-surface-container-low p-4 rounded-lg border border-outline-variant/20 flex flex-wrap justify-between items-center gap-4">
                            <div>
                              <span className="text-xs font-bold uppercase text-primary tracking-wider bg-primary/10 px-2 py-0.5 rounded">
                                GIS MOVEMENT ROUTE
                              </span>
                              <div className="font-code-telemetry text-base font-bold text-on-surface mt-1">
                                {globalRoute.data.global_vehicle_id} — {globalRoute.data.normalized_plate}
                              </div>
                            </div>
                            <div className="flex gap-4 text-xs">
                              <div className="bg-surface-container-high px-3 py-1.5 rounded text-on-surface">
                                Total Observations: <span className="font-bold font-code-telemetry text-primary">{globalRoute.data.total_observations}</span>
                              </div>
                              <div className="bg-surface-container-high px-3 py-1.5 rounded text-on-surface">
                                Mapped Points: <span className="font-bold font-code-telemetry text-secondary">{globalRoute.data.mapped_points_count}</span>
                              </div>
                            </div>
                          </div>

                          {/* Mandatory GIS Disclaimer */}
                          <div className="bg-primary/5 border border-primary/20 p-2.5 rounded-lg text-xs text-primary flex items-center gap-2">
                            <span className="material-symbols-outlined text-sm">info</span>
                            <span>
                              <strong>Observed Camera Sequence</strong> — Route represents confirmed camera observations connected in source timestamp order. Not a continuous road GPS trace.
                            </span>
                          </div>

                          {/* Tactical Map Visualizer Canvas / Grid */}
                          <div className="card p-4 bg-surface-container-lowest min-h-[320px] flex flex-col justify-between relative overflow-hidden border border-outline-variant/30">
                            {globalRoute.data.mapped_points_count === 0 ? (
                              <div className="py-12 text-center">
                                <EmptyState
                                  icon="location_off"
                                  title="GPS Location Data Unavailable"
                                  description="GPS location data unavailable for this vehicle. Camera nodes in the current catalogue operate without registered GIS coordinates."
                                />
                              </div>
                            ) : (
                              <div className="flex flex-col gap-6">
                                {/* SVG/Visual Node Sequence Map */}
                                <div className="p-6 bg-surface-container-low rounded-lg border border-outline-variant/20">
                                  <div className="text-xs font-bold text-outline uppercase tracking-wider mb-4">
                                    Chronological Camera Node Sequence Map
                                  </div>

                                  <div className="flex flex-wrap items-center gap-3">
                                    {globalRoute.data.points.map((pt: RoutePoint, idx: number) => {
                                      const hasCoords = pt.latitude !== null && pt.longitude !== null;
                                      return (
                                        <div key={idx} className="flex items-center gap-3">
                                          {/* Node Card */}
                                          <div
                                            className={`p-3 rounded-lg border flex flex-col gap-1 min-w-[150px] ${
                                              hasCoords
                                                ? 'bg-primary-container/20 border-primary shadow-sm'
                                                : 'bg-surface-container-high border-outline-variant/30 opacity-70'
                                            }`}
                                          >
                                            <div className="flex justify-between items-center">
                                              <span className="font-code-telemetry text-xs font-bold text-primary">
                                                {pt.camera_id}
                                              </span>
                                              <span className="text-[10px] text-outline">#{idx + 1}</span>
                                            </div>
                                            <div className="text-xs text-on-surface font-semibold">
                                              {pt.vehicle_class || 'car'} • Track #{pt.canonical_vehicle_id}
                                            </div>
                                            <div className="text-[10px] font-code-telemetry text-on-surface-variant">
                                              {formatTimestamp(pt.timestamp)}
                                            </div>
                                            <div className="text-[10px] font-code-telemetry mt-1">
                                              {hasCoords ? (
                                                <span className="text-secondary font-bold">
                                                  {pt.latitude?.toFixed(4)}, {pt.longitude?.toFixed(4)}
                                                </span>
                                              ) : (
                                                <span className="text-outline italic">Location unavailable</span>
                                              )}
                                            </div>
                                          </div>

                                          {/* Arrow Connector */}
                                          {idx < (globalRoute.data?.points.length ?? 0) - 1 && (
                                            <span className="text-primary font-bold text-lg">→</span>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Full Observations Sequence Table with Location Status */}
                          <div className="overflow-x-auto">
                            <h3 className="text-xs font-bold text-outline uppercase tracking-wider mb-2">
                              Detailed Camera Observations & GIS Status
                            </h3>
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b border-outline-variant/20">
                                  <th className="text-left py-2 px-3 font-label-sm text-outline">#</th>
                                  <th className="text-left py-2 px-3 font-label-sm text-outline">Timestamp</th>
                                  <th className="text-left py-2 px-3 font-label-sm text-outline">Camera Node</th>
                                  <th className="text-left py-2 px-3 font-label-sm text-outline">Class</th>
                                  <th className="text-left py-2 px-3 font-label-sm text-outline">Coordinates</th>
                                  <th className="text-left py-2 px-3 font-label-sm text-outline">Location Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {globalRoute.data.points.map((pt: RoutePoint, idx: number) => {
                                  const hasCoords = pt.latitude !== null && pt.longitude !== null;
                                  return (
                                    <tr key={idx} className="border-b border-outline-variant/10 hover:bg-surface-container-low">
                                      <td className="py-2 px-3 font-code-telemetry text-xs text-outline">{idx + 1}</td>
                                      <td className="py-2 px-3 font-code-telemetry text-xs text-on-surface-variant">
                                        {formatTimestamp(pt.timestamp)}
                                      </td>
                                      <td className="py-2 px-3">
                                        <span className="bg-primary/10 text-primary font-code-telemetry font-bold px-2 py-0.5 rounded text-xs">
                                          {pt.camera_id}
                                        </span>
                                      </td>
                                      <td className="py-2 px-3 text-xs text-on-surface">{pt.vehicle_class || 'car'}</td>
                                      <td className="py-2 px-3 font-code-telemetry text-xs text-on-surface">
                                        {hasCoords ? `${pt.latitude?.toFixed(4)}, ${pt.longitude?.toFixed(4)}` : '—'}
                                      </td>
                                      <td className="py-2 px-3 text-xs">
                                        {hasCoords ? (
                                          <span className="bg-secondary/20 text-secondary font-bold px-2 py-0.5 rounded text-[11px]">
                                            MAPPED
                                          </span>
                                        ) : (
                                          <span className="bg-surface-container-highest text-outline font-medium px-2 py-0.5 rounded text-[11px]">
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
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Camera-Local Track Query */}
      {activeTab === 'local' && (
        <div className="flex flex-col gap-4">
          <div className="card p-4">
            <form onSubmit={handleLocalSearch} className="flex gap-3">
              <input
                type="text"
                value={localSearchId}
                onChange={(e) => setLocalSearchId(e.target.value)}
                placeholder="Enter canonical vehicle ID (e.g. 1, 2, 3...)"
                className="input-field flex-1"
              />
              <button type="submit" className="btn-primary">
                Search Local Track
              </button>
            </form>
          </div>

          {localSearchTriggered && canonicalVehicleId && (
            <div className="card">
              <div className="card-header">
                <h2 className="font-headline-sm text-on-surface font-bold">
                  Vehicle #{canonicalVehicleId} Event History
                </h2>
              </div>
              <div className="p-4">
                {localHistory.status === 'loading' && <LoadingState message="Loading vehicle history..." />}
                {localHistory.status === 'error' && <ErrorState message={localHistory.error} onRetry={localHistory.refresh} />}
                {localHistory.status === 'success' && localHistory.data && (
                  <>
                    {localHistory.data.length === 0 ? (
                      <EmptyState
                        icon="directions_car"
                        title="No events found"
                        description={`No events recorded for canonical vehicle ID ${canonicalVehicleId}.`}
                      />
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-outline-variant/20">
                              <th className="text-left py-2 px-3 font-label-sm text-outline">Timestamp</th>
                              <th className="text-left py-2 px-3 font-label-sm text-outline">Event</th>
                              <th className="text-left py-2 px-3 font-label-sm text-outline">Camera</th>
                              <th className="text-left py-2 px-3 font-label-sm text-outline">Class</th>
                              <th className="text-left py-2 px-3 font-label-sm text-outline">Direction</th>
                              <th className="text-left py-2 px-3 font-label-sm text-outline">Confidence</th>
                            </tr>
                          </thead>
                          <tbody>
                            {localHistory.data.map((event, idx) => (
                              <tr key={idx} className="border-b border-outline-variant/10 hover:bg-surface-container-low">
                                <td className="py-2 px-3 font-code-telemetry text-label-sm text-on-surface-variant">
                                  {formatTimestamp(event.timestamp)}
                                </td>
                                <td className="py-2 px-3">
                                  <span
                                    className={`status-badge ${
                                      event.event_type === 'ZONE_IN'
                                        ? 'bg-secondary/20 text-secondary'
                                        : event.event_type === 'ZONE_OUT'
                                        ? 'bg-primary/20 text-primary'
                                        : 'bg-surface-container-high text-on-surface-variant'
                                    }`}
                                  >
                                    {event.event_type}
                                  </span>
                                </td>
                                <td className="py-2 px-3 font-code-telemetry text-label-sm text-on-surface">
                                  {event.camera_id}
                                </td>
                                <td className="py-2 px-3 text-on-surface">{event.vehicle_class}</td>
                                <td className="py-2 px-3">
                                  {event.direction && (
                                    <span
                                      className={`font-code-telemetry text-label-sm font-bold ${
                                        event.direction === 'IN' ? 'text-secondary' : 'text-primary'
                                      }`}
                                    >
                                      {event.direction === 'IN' ? '↓ IN' : '↑ OUT'}
                                    </span>
                                  )}
                                </td>
                                <td className="py-2 px-3 font-code-telemetry text-label-sm text-on-surface-variant">
                                  {event.confidence ? `${(event.confidence * 100).toFixed(1)}%` : '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {!localSearchTriggered && (
            <div className="card p-8">
              <EmptyState
                icon="search"
                title="Search for a camera-local track"
                description="Enter a canonical vehicle ID to view its local detection and zone event history."
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
