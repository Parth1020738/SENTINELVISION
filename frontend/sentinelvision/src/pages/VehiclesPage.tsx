import { useState } from 'react';
import { api } from '../api/client';
import { useApi, formatTimestamp, getStatusColor } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

export default function VehiclesPage() {
  const [searchId, setSearchId] = useState('');
  const [searchTriggered, setSearchTriggered] = useState(false);
  const [vehicleId, setVehicleId] = useState<number | null>(null);

  const history = useApi(
    () => (vehicleId !== null ? api.getVehicleHistory(vehicleId) : Promise.resolve([])),
    [vehicleId],
    undefined
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(searchId, 10);
    if (!isNaN(id)) {
      setVehicleId(id);
      setSearchTriggered(true);
    }
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">VEHICLE INVESTIGATION</span>
        </div>
        <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">Vehicle History</h1>
        <p className="font-body-sm text-on-surface-variant">Query vehicle events by canonical ID across all camera nodes.</p>
      </div>

      <div className="card p-4">
        <form onSubmit={handleSearch} className="flex gap-3">
          <input
            type="text"
            value={searchId}
            onChange={(e) => setSearchId(e.target.value)}
            placeholder="Enter canonical vehicle ID (e.g. 1, 2, 3...)"
            className="input-field flex-1"
          />
          <button type="submit" className="btn-primary">Search</button>
        </form>
      </div>

      {searchTriggered && vehicleId && (
        <div className="card">
          <div className="card-header">
            <h2 className="font-headline-sm text-on-surface font-bold">Vehicle #{vehicleId} Event History</h2>
          </div>
          <div className="p-4">
            {history.status === 'loading' && <LoadingState message="Loading vehicle history..." />}
            {history.status === 'error' && <ErrorState message={history.error} onRetry={history.refresh} />}
            {history.status === 'success' && history.data && (
              <>
                {history.data.length === 0 ? (
                  <EmptyState icon="directions_car" title="No events found" description={`No events recorded for vehicle ${vehicleId}.`} />
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
                        {history.data.map((event, idx) => (
                          <tr key={idx} className="border-b border-outline-variant/10 hover:bg-surface-container-low">
                            <td className="py-2 px-3 font-code-telemetry text-label-sm text-on-surface-variant">{formatTimestamp(event.timestamp)}</td>
                            <td className="py-2 px-3">
                              <span className={`status-badge ${event.event_type === 'ZONE_IN' ? 'bg-secondary/20 text-secondary' : event.event_type === 'ZONE_OUT' ? 'bg-primary/20 text-primary' : 'bg-surface-container-high text-on-surface-variant'}`}>
                                {event.event_type}
                              </span>
                            </td>
                            <td className="py-2 px-3 font-code-telemetry text-label-sm text-on-surface">{event.camera_id}</td>
                            <td className="py-2 px-3 text-on-surface">{event.vehicle_class}</td>
                            <td className="py-2 px-3">
                              {event.direction && (
                                <span className={`font-code-telemetry text-label-sm font-bold ${event.direction === 'IN' ? 'text-secondary' : 'text-primary'}`}>
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

      {!searchTriggered && (
        <div className="card p-8">
          <EmptyState icon="search" title="Search for a vehicle" description="Enter a canonical vehicle ID to view its complete event history across all cameras." />
        </div>
      )}
    </div>
  );
}
