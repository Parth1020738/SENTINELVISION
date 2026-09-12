// SentinelVision API Client
// Centralized API service layer - all backend communication goes through here

import {
  Camera,
  CameraPlaybackResponse,
  PlateSearchResponse,
  CountsResponse,
  WatchlistListResponse,
  WatchlistEntry,
  WatchlistEntryCreate,
  WatchlistEntryUpdate,
  AlertListResponse,
  Alert,
  VehicleEvent,
  HealthResponse,
  CameraHealth,
  SystemHealthResponse,
  GlobalVehicle,
  GlobalVehicleListResponse,
  GlobalVehicleTimelineResponse,
  GlobalVehicleRouteResponse,
} from '../types';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const token = localStorage.getItem('sentinel_token');
  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeader,
      ...options.headers,
    },
  });

  if (!response.ok) {
    let detail = 'Request failed';
    try {
      const errorBody = await response.json();
      detail = errorBody.detail || detail;
    } catch {
      // Response wasn't JSON
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const api = {
  // Access Gate
  verifyAccessCode: (accessCode: string) =>
    request<{ access_token: string; token_type: string; role: string; username: string }>('/api/auth/verify-access-code', {
      method: 'POST',
      body: JSON.stringify({ access_code: accessCode }),
    }),
  // Health
  getHealth: () => request<HealthResponse>('/health'),
  getSystemHealth: () => request<SystemHealthResponse>('/api/system/health'),
  getCamerasHealth: () => request<CameraHealth[]>('/api/cameras/health'),

  // Cameras
  getCameras: (selectedCameraId?: string) =>
    request<Camera[]>(selectedCameraId ? `/api/cameras?selected_camera_id=${encodeURIComponent(selectedCameraId)}` : '/api/cameras'),
  getCamera: (cameraId: string) => request<Camera>(`/api/cameras/${cameraId}`),
  getCameraPlayback: (cameraId: string) => request<CameraPlaybackResponse>(`/api/cameras/${cameraId}/playback`),
  getCameraLiveUrl: (cameraId: string) => {
    const token = localStorage.getItem('sentinel_token');
    return `${API_BASE_URL}/api/cameras/${encodeURIComponent(cameraId)}/live${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  },

  // Vehicles & Global Tracking
  getVehicleHistory: (canonicalVehicleId: number) => request<VehicleEvent[]>(`/api/vehicles/${canonicalVehicleId}/history`),
  getGlobalVehicles: (limit = 100, offset = 0) => request<GlobalVehicleListResponse>(`/api/vehicles?limit=${limit}&offset=${offset}`),
  getGlobalVehicle: (globalVehicleId: string) => request<GlobalVehicle>(`/api/vehicles/${encodeURIComponent(globalVehicleId)}`),
  getGlobalVehicleTimeline: (globalVehicleId: string) => request<GlobalVehicleTimelineResponse>(`/api/vehicles/${encodeURIComponent(globalVehicleId)}/timeline`),
  getGlobalVehicleRoute: (globalVehicleId: string) => request<GlobalVehicleRouteResponse>(`/api/vehicles/${encodeURIComponent(globalVehicleId)}/route`),
  searchGlobalVehicleByPlate: (plate: string) => request<GlobalVehicle>(`/api/vehicles/search?plate=${encodeURIComponent(plate)}`),

  // Plates
  searchPlates: (plate: string, match: 'exact' | 'partial' = 'partial') =>
    request<PlateSearchResponse>(`/api/plates/search?plate=${encodeURIComponent(plate)}&match=${match}`),

  // Counts
  getCounts: (params?: { camera_id?: string; vehicle_class?: string; direction?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.camera_id) searchParams.set('camera_id', params.camera_id);
    if (params?.vehicle_class) searchParams.set('vehicle_class', params.vehicle_class);
    if (params?.direction) searchParams.set('direction', params.direction);
    const query = searchParams.toString();
    return request<CountsResponse>(`/api/counts${query ? `?${query}` : ''}`);
  },

  // Watchlist
  getWatchlist: () => request<WatchlistListResponse>('/api/watchlist'),
  getWatchlistEntry: (plate: string) => request<WatchlistEntry>(`/api/watchlist/${plate}`),
  createWatchlistEntry: (data: WatchlistEntryCreate) =>
    request<WatchlistEntry>('/api/watchlist', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateWatchlistEntry: (plate: string, data: WatchlistEntryUpdate) =>
    request<WatchlistEntry>(`/api/watchlist/${plate}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteWatchlistEntry: (plate: string) =>
    request<{ detail: string; plate: string }>(`/api/watchlist/${plate}`, {
      method: 'DELETE',
    }),

  // Alerts
  getAlerts: (params?: { status?: string; priority?: string; camera_id?: string; plate?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.priority) searchParams.set('priority', params.priority);
    if (params?.camera_id) searchParams.set('camera_id', params.camera_id);
    if (params?.plate) searchParams.set('plate', params.plate);
    const query = searchParams.toString();
    return request<AlertListResponse>(`/api/alerts${query ? `?${query}` : ''}`);
  },
  getAlert: (alertId: number) => request<Alert>(`/api/alerts/${alertId}`),
  updateAlertStatus: (alertId: number, status: string) =>
    request<Alert>(`/api/alerts/${alertId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  // Export
  exportVehiclesCsv: async () => {
    const token = localStorage.getItem('sentinel_token');
    const response = await fetch(`${API_BASE_URL}/api/vehicles/export.csv`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new Error('Failed to export CSV evidence');
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sentinelvision_vehicle_evidence.csv';
    a.click();
    window.URL.revokeObjectURL(url);
  },
  exportVehiclePdf: async (globalVehicleId: string) => {
    const token = localStorage.getItem('sentinel_token');
    const response = await fetch(`${API_BASE_URL}/api/vehicles/${encodeURIComponent(globalVehicleId)}/export.pdf`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new Error('Failed to export PDF investigation report');
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sentinelvision_report_${globalVehicleId}.pdf`;
    a.click();
    window.URL.revokeObjectURL(url);
  },
};

export { ApiError };
