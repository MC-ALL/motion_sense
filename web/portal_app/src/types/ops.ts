export type HealthStatus = 'healthy' | 'degraded' | 'offline' | 'unknown';
export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertStatus = 'open' | 'closed';

export interface ModuleHealthSummary {
  module_id: string;
  module_type: 'gateway' | 'backend';
  display_name?: string | null;
  online: boolean;
  health_status: HealthStatus;
  checked_at: string;
  component_total: number;
  healthy_components: number;
  degraded_components: number;
  offline_components: number;
  last_error?: string | null;
}

export interface ModuleComponent {
  module_id: string;
  component_id: string;
  component_type: string;
  display_name: string;
  online: boolean;
  health_status: HealthStatus;
  checked_at: string;
  endpoint?: string | null;
  latency_ms?: number | null;
  detail?: string | null;
}

export interface ModuleStats {
  module_id: string;
  module_type: 'gateway' | 'backend';
  updated_at: string;
  data: Record<string, unknown>;
}

export interface OpsAlertRecord {
  id: number;
  module_id: string;
  module_type: 'gateway' | 'backend';
  alert_type: string;
  severity: AlertSeverity;
  status: AlertStatus;
  title: string;
  detail: string;
  created_at: string;
  updated_at: string;
  closed_at?: string | null;
  payload: Record<string, unknown>;
}

export interface OpsHealthListResponse {
  items: ModuleHealthSummary[];
  updated_at?: string | null;
}

export interface OpsHealthDetailResponse {
  summary: ModuleHealthSummary;
  components: ModuleComponent[];
  stats?: ModuleStats | null;
}

export interface OpsAlertListResponse {
  items: OpsAlertRecord[];
}

export interface OpsStatsResponse {
  items: ModuleStats[];
  updated_at?: string | null;
}

export interface OpsMessage<T = unknown> {
  type: string;
  data: T;
}
