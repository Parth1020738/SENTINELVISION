import { useState } from 'react';
import { api } from '../api/client';
import { useApi, formatTimestamp } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

export default function HistoryPage() {
  const [searchId, setSearchId] = useState('');
  const [vehicleId, setVehicleId] = useState<number | null>(null);

  const history = useApi(
    () => (vehicleId !== null ? api.getVehicleHistory(vehicleId) : Promise.resolve([])),
    [vehicleId],
    undefined
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(searchId, 10);
    if (!isNaN(id)) setVehicleId(id);
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">FORENSIC TELEMETRY ENGINE</span>
        </div>
        <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">Vehicle Investigation & Trajectory History</h1>
        <p className="font-body-sm text-on-surface-variant">Deep forensic query by canonical vehicle ID across all camera nodes.</p>
      </div>

      <div className="card p-4">
        <form onSubmit={handleSearch} className="flex gap-3">
          <input type="text" value={searchId} onChange={(e) => setSearchId(e.target.value)} placeholder="Enter canonical vehicle ID" className="input-field flex-1" />
          <button type="submit" className="btn-primary">Investigate</button>
        </form>
      </div>

      {vehicleId && (
        <div className="card">
          <div className="card-header">
            <h2 className="font-headline-sm text-on-surface font-bold">Vehicle #{vehicleId} Timeline</h2>
          </div>
          <div className="p-4">
            {history.status === 'loading' && <LoadingState message="Loading history..." />}
            {history.status === 'error' && <ErrorState message={history.error} onRetry={history.refresh} />}
            {history.status === 'success' && history.data && (
              history.data.length === 0 ? (
                <EmptyState icon="search_off" title="No events found" description="No events recorded for this vehicle." />
              ) : (
                <div className="relative">
                  {/* Timeline line */}
                  <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-outline-variant/40" />
                  <div className="space-y-4">
                    {history.data.map((event, idx) => (
                      <div key={idx} className="relative pl-10">
                        {/* Timeline dot */}
                        <div className={`absolute left-2.5 top-1.5 w-3 h-3 rounded-full ${event.event_type === 'ZONE_IN' ? 'bg-secondary' : event.event_type === 'ZONE_OUT' ? 'bg-primary' : 'bg-outline-variant'}`} />
                        <div className="p-3 bg-surface-container-lowest rounded border border-outline-variant/20">
                          <div className="flex items-center justify-between mb-1">
                            <span className={`status-badge ${event.event_type === 'ZONE_IN' ? 'bg-secondary/20 text-secondary' : event.event_type === 'ZONE_OUT' ? 'bg-primary/20 text-primary' : 'bg-surface-container-high text-on-surface-variant'}`}>
                              {event.event_type}
                            </span>
                            <span className="font-code-telemetry text-label-sm text-on-surface-variant">{formatTimestamp(event.timestamp)}</span>
                          </div>
                          <div className="flex items-center gap-4 font-code-telemetry text-label-sm text-on-surface-variant">
                            <span>Camera: {event.camera_id}</span>
                            <span>Class: {event.vehicle_class}</span>
                            {event.direction && <span>Dir: {event.direction}</span>}
                            {event.confidence && <span>Conf: {(event.confidence * 100).toFixed(1)}%</span>}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      )}

      {!vehicleId && (
        <div className="card p-8">
          <EmptyState icon="manage_search" title="Investigate a vehicle" description="Enter a canonical vehicle ID to view its complete timeline and trajectory history." />
        </div>
      )}
    </div>
  );
}
