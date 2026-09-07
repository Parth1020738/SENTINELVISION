import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { useApi, useEventStream, formatTimestamp, formatRelativeTime, getStatusColor, getPriorityColor } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';
import { Alert, ALERT_STATUSES } from '../types';

export default function AlertsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('');
  const alerts = useApi(() => api.getAlerts(statusFilter ? { status: statusFilter } : undefined), [statusFilter], 10000);
  const [error, setError] = useState<string | null>(null);
  const { subscribe } = useEventStream();

  useEffect(() => {
    const unsubscribe = subscribe((event) => {
      if (['alert_created', 'alert_status_changed'].includes(event.event_type)) {
        alerts.refresh();
      }
    });
    return unsubscribe;
  }, [subscribe, alerts]);

  const handleStatusUpdate = async (alertId: number, status: string) => {
    try {
      await api.updateAlertStatus(alertId, status);
      alerts.refresh();
    } catch (err: any) {
      setError(err.message || 'Failed to update alert status');
    }
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="font-label-sm text-error uppercase tracking-widest bg-error-container/20 px-2 py-0.5 rounded">SECURITY ALERTS</span>
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-error animate-pulse" />
          </div>
          <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">Alert Command Center</h1>
          <p className="font-body-sm text-on-surface-variant">Real-time threat interdiction and watchlist match alerts.</p>
        </div>
        <div className="flex gap-2">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="select-field w-40">
            <option value="">All Statuses</option>
            {ALERT_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {error && <div className="card p-4 border-l-4 border-error"><p className="text-error">{error}</p></div>}

      <div className="card">
        <div className="card-header flex items-center justify-between">
          <h2 className="font-headline-sm text-on-surface font-bold">Alert Feed</h2>
          {alerts.status === 'success' && <span className="font-code-telemetry text-label-sm text-on-surface-variant">{alerts.data?.count} alerts</span>}
        </div>
        <div className="p-4">
          {alerts.status === 'loading' && <LoadingState message="Loading alerts..." />}
          {alerts.status === 'error' && <ErrorState message={alerts.error} onRetry={alerts.refresh} />}
          {alerts.status === 'success' && alerts.data?.results.length === 0 && (
            <EmptyState icon="shield" title="No alerts" description="No security alerts match the current filter." />
          )}
          {alerts.status === 'success' && alerts.data && alerts.data.results.length > 0 && (
            <div className="space-y-3">
              {alerts.data.results.map((alert: Alert) => (
                <AlertCard key={alert.id} alert={alert} onStatusUpdate={handleStatusUpdate} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AlertCard({ alert, onStatusUpdate }: { alert: Alert; onStatusUpdate: (id: number, status: string) => void }) {
  const isHighPriority = alert.priority === 'HIGH' || alert.priority === 'CRITICAL';
  return (
    <div className={`p-4 rounded border ${isHighPriority ? 'border-error/40 bg-error-container/5' : 'border-outline-variant/20 bg-surface-container-lowest'}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className={`material-symbols-outlined text-[24px] ${isHighPriority ? 'text-error' : 'text-primary'}`}>
            {alert.priority === 'CRITICAL' ? 'dangerous' : 'warning'}
          </span>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-code-telemetry text-label-md text-primary font-bold">{alert.normalized_plate || `VEH-${alert.canonical_vehicle_id}`}</span>
              <span className={`status-badge ${getPriorityColor(alert.priority)}`}>{alert.priority}</span>
              <span className={`status-badge ${getStatusColor(alert.status)}`}>{alert.status}</span>
            </div>
            <p className="font-body-sm text-on-surface mb-1">{alert.reason}</p>
            <div className="flex items-center gap-4 font-code-telemetry text-label-sm text-on-surface-variant">
              <span>Camera: {alert.camera_id}</span>
              <span>Vehicle: {alert.canonical_vehicle_id}</span>
              {alert.vehicle_class && <span>Class: {alert.vehicle_class}</span>}
              <span>{formatRelativeTime(alert.timestamp || alert.created_at)}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          {alert.status === 'NEW' && (
            <button onClick={() => onStatusUpdate(alert.id, 'ACKNOWLEDGED')} className="btn-secondary text-xs">Acknowledge</button>
          )}
          {alert.status !== 'RESOLVED' && (
            <button onClick={() => onStatusUpdate(alert.id, 'RESOLVED')} className="btn-primary text-xs">Resolve</button>
          )}
        </div>
      </div>
    </div>
  );
}
