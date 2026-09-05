// SentinelVision API Types
// Mirrors the backend Pydantic schemas

export interface Camera {
  camera_id: string;
  name?: string | null;
  location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  codec?: string | null;
  width?: number | null;
  height?: number | null;
  live: boolean;
  created_at?: string | null;
  updated_at?: string | null;
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
