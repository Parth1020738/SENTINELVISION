// SentinelVision API Types
// Mirrors the backend Pydantic schemas

export interface Camera {
  camera_id: string;
  name?: string | null;
  location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  coordinate_source?: string | null;
  coordinate_approximate?: boolean | null;
  codec?: string | null;
  width?: number | null;
  height?: number | null;
  resolution?: string | null;
  live: boolean;
  status?: string;
  ai_active?: boolean;
  attention_state?: 'NORMAL' | 'WATCH' | 'CRITICAL' | string;
  attention_reason?: string | null;
  anpr_capable?: boolean;
  department?: string | null;
  district?: string | null;
  tags?: string[] | null;
  is_virtual?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CameraPlaybackResponse {
  camera_id: string;
  playback_type: string;
  playback_url: string;
  available: boolean;
}

export interface VehicleEvent {
  id?: number | null;
  canonical_vehicle_id: number;
  camera_id: string;
  vehicle_class: string;
  event_type: string;
  timestamp?: string | null;
  confidence?: number | null;
  bbox_x1?: number | null;
  bbox_y1?: number | null;
  bbox_x2?: number | null;
  bbox_y2?: number | null;
  direction?: string | null;
  created_at?: string | null;
}

export interface PlateRead {
  id?: number | null;
  canonical_vehicle_id: number;
  camera_id: string;
  normalized_plate?: string | null;
  raw_ocr?: string | null;
  ocr_confidence?: number | null;
  detector_confidence?: number | null;
  combined_confidence?: number | null;
  timestamp?: string | null;
  created_at?: string | null;
}

export interface PlateSearchResponse {
  query: string;
  normalized_query: string;
  match: string;
  count: number;
  results: PlateRead[];
}

export interface DirectionTotals {
  IN: number;
  OUT: number;
}

export interface CountsResponse {
  filters: Record<string, unknown>;
  total: DirectionTotals;
  by_class: Record<string, DirectionTotals>;
}

export interface WatchlistEntry {
  id: number;
  normalized_plate: string;
  reason: string;
  category: string;
  priority: string;
  notes?: string | null;
  active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WatchlistListResponse {
  count: number;
  results: WatchlistEntry[];
}

export interface WatchlistEntryCreate {
  plate: string;
  reason: string;
  category: string;
  priority: string;
  notes?: string | null;
}

export interface WatchlistEntryUpdate {
  reason?: string | null;
  category?: string | null;
  priority?: string | null;
  notes?: string | null;
  active?: boolean | null;
}

export interface Alert {
  id: number;
  watchlist_entry_id: number;
  normalized_plate: string;
  canonical_vehicle_id: number;
  camera_id: string;
  plate_read_id?: number | null;
  vehicle_class?: string | null;
  confidence?: number | null;
  reason: string;
  category: string;
  priority: string;
  timestamp?: string | null;
  status: string;
  created_at?: string | null;
  acknowledged_at?: string | null;
}

export interface AlertListResponse {
  count: number;
  results: Alert[];
}

export interface AlertStatusUpdate {
  status: string;
}

export interface HealthResponse {
  status: string;
  database: string;
  service?: string;
  version?: string;
  timestamp?: string;
}

export interface CameraHealth {
  camera_id: string;
  name?: string | null;
  location?: string | null;
  status: 'ONLINE' | 'DEGRADED' | 'OFFLINE' | 'NOT_CHECKED' | string;
  last_successful_frame_at?: string | null;
  last_attempt_at?: string | null;
  last_failure_at?: string | null;
  consecutive_failures: number;
  reconnect_count: number;
  last_error?: string | null;
  ai_active: boolean;
  attention_state?: 'NORMAL' | 'WATCH' | 'CRITICAL' | string;
  attention_reason?: string | null;
}

export interface HealthSummaryCounts {
  total_configured: number;
  online_count: number;
  degraded_count: number;
  offline_count: number;
  not_checked_count: number;
  ai_active_count: number;
}

export interface SystemHealthResponse {
  status: string;
  database: string;
  summary: HealthSummaryCounts;
  cameras: CameraHealth[];
}

export interface VehicleHistoryResponse {
  canonical_vehicle_id: number;
  event_count: number;
  events: VehicleEvent[];
}

// Constants
export const WATCHLIST_CATEGORIES = ['STOLEN', 'WANTED', 'SUSPICIOUS', 'INVESTIGATION', 'OTHER'] as const;
export const WATCHLIST_PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const;
export const ALERT_STATUSES = ['NEW', 'ACKNOWLEDGED', 'RESOLVED'] as const;

export type WatchlistCategory = typeof WATCHLIST_CATEGORIES[number];
export type WatchlistPriority = typeof WATCHLIST_PRIORITIES[number];
export type AlertStatus = typeof ALERT_STATUSES[number];

export interface RealtimeEvent {
  event_type: 'alert_created' | 'alert_status_changed' | 'attention_changed' | 'zone_count_changed' | 'plate_read' | 'vehicle_event' | string;
  timestamp: string;
  camera_id?: string | null;
  data: Record<string, any>;
}

export type ConnectionStatus = 'CONNECTED' | 'RECONNECTING' | 'DISCONNECTED';

export interface GlobalVehicle {
  id: number;
  global_vehicle_id: string;
  normalized_plate?: string | null;
  vehicle_class?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GlobalVehicleListResponse {
  count: number;
  results: GlobalVehicle[];
}

export interface CrossCameraObservation {
  id: number;
  global_vehicle_id: string;
  camera_id: string;
  canonical_vehicle_id: number;
  normalized_plate?: string | null;
  vehicle_class?: string | null;
  timestamp?: string | null;
  plate_read_id?: number | null;
  created_at?: string | null;
}

export interface GlobalVehicleTimelineResponse {
  global_vehicle_id: string;
  normalized_plate?: string | null;
  vehicle_class?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  observation_count: number;
  timeline: CrossCameraObservation[];
}

export interface RoutePoint {
  camera_id: string;
  timestamp?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  vehicle_class?: string | null;
  canonical_vehicle_id: number;
  normalized_plate?: string | null;
}

export interface GlobalVehicleRouteResponse {
  global_vehicle_id: string;
  normalized_plate?: string | null;
  vehicle_class?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  total_observations: number;
  mapped_points_count: number;
  points: RoutePoint[];
}
