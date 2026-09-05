// SentinelVision React Hooks
import { useState, useEffect, useCallback } from 'react';
import { ApiError } from '../api/client';

export type AsyncState<T> = 
  | { status: 'loading'; data: null; error: null }
  | { status: 'success'; data: T; error: null }
  | { status: 'error'; data: null; error: string }
  | { status: 'empty'; data: null; error: null };

export type { AsyncState as AsyncStateType };

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  pollInterval?: number
): AsyncState<T> & { refresh: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading', data: null, error: null });

  const fetchData = useCallback(() => {
    setState({ status: 'loading', data: null, error: null });
    fetcher()
      .then((data) => {
        setState({ status: 'success', data, error: null });
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : 'Failed to fetch data';
        setState({ status: 'error', data: null, error: message });
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!pollInterval) return;
    const interval = setInterval(fetchData, pollInterval);
    return () => clearInterval(interval);
  }, [fetchData, pollInterval]);

  return { ...state, refresh: fetchData };
}

export function useNow(intervalMs: number = 1000): string {
  const [now, setNow] = useState<string>(() => formatUtcNow());

  useEffect(() => {
    const interval = setInterval(() => setNow(formatUtcNow()), intervalMs);
    return () => clearInterval(interval);
  }, [intervalMs]);

  return now;
}

function formatUtcNow(): string {
  return new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
}

export function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    return d.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
  } catch {
    return ts;
  }
}

export function formatRelativeTime(ts: string | null | undefined): string {
  if (!ts) return '—';
  try {
    const then = new Date(ts).getTime();
    const now = Date.now();
    const diff = Math.floor((now - then) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch {
    return ts;
  }
}

export function getPriorityColor(priority: string): string {
  switch (priority) {
    case 'CRITICAL': return 'text-error bg-error-container/20';
    case 'HIGH': return 'text-tertiary-container bg-tertiary-container/20';
    case 'MEDIUM': return 'text-primary bg-primary/20';
    case 'LOW': return 'text-outline bg-surface-container-high';
    default: return 'text-on-surface-variant bg-surface-container';
  }
}

export function getCategoryColor(category: string): string {
  switch (category) {
    case 'STOLEN': return 'text-error bg-error-container/20';
    case 'WANTED': return 'text-tertiary-container bg-tertiary-container/20';
    case 'SUSPICIOUS': return 'text-primary bg-primary/20';
    case 'INVESTIGATION': return 'text-secondary bg-secondary/20';
    default: return 'text-on-surface-variant bg-surface-container';
  }
}

export function getStatusColor(status: string): string {
  switch (status) {
    case 'NEW': return 'text-error bg-error-container/20';
    case 'ACKNOWLEDGED': return 'text-primary bg-primary/20';
    case 'RESOLVED': return 'text-secondary bg-secondary/20';
    case 'ACTIVE': return 'text-secondary bg-secondary/20';
    case 'INACTIVE': return 'text-outline bg-surface-container-high';
    default: return 'text-on-surface-variant bg-surface-container';
  }
}
