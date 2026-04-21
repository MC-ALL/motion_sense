export type DeviceType = 'wristband' | 'equipment' | 'env' | 'gateway' | string;
export type DeviceRegistryType = 'wristband' | 'equipment' | 'env' | 'gateway';
export type UserRole = 'admin' | 'teacher' | 'student';

export interface DeviceSummary {
  gym_id: string;
  device_type: DeviceType;
  device_id: string;
  gateway_id?: string | null;
  display_name?: string | null;
  location?: string | null;
  metadata?: Record<string, unknown> | null;
  status: string;
  online: boolean;
  last_seen_ts: number | null;
  last_payload: Record<string, unknown>;
  registered_at?: string | null;
  updated_at?: string | null;
}

export interface DeviceRegistrationRequest {
  gym_id: string;
  device_type: DeviceRegistryType;
  device_id: string;
  gateway_id?: string | null;
  display_name?: string | null;
  location?: string | null;
  metadata?: Record<string, unknown>;
}

export interface DeviceRegistrationUpdateRequest {
  gateway_id?: string | null;
  display_name?: string | null;
  location?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface BusinessAlertRecord {
  id: number;
  gym_id: string;
  device_type: DeviceType;
  device_id: string;
  level: string;
  code: string;
  message: string;
  priority?: string | null;
  is_ack: boolean;
  triggered_at: string;
  payload: Record<string, unknown>;
}

export interface TelemetryRecord {
  ts: string;
  gym_id: string;
  device_type: DeviceType;
  device_id: string;
  payload: Record<string, unknown>;
}

export interface MetricAggregate {
  min: number;
  max: number;
  avg: number;
}

export interface EnvTelemetryAggregateRecord {
  bucket_start: string;
  bucket_end: string;
  count: number;
  metrics: Record<string, MetricAggregate>;
}

export interface BindingEventRecord {
  id: number;
  wristband_id: string;
  equipment_id: string;
  gym_id: string;
  action: string;
  reason?: string | null;
  ts: string;
  duration_s?: number | null;
}

export interface DeviceConfigPublishRequest {
  config: Record<string, unknown>;
  gym_id?: string | null;
  gateway_id?: string | null;
  device_type?: DeviceType | null;
  qos?: number | null;
  retain?: boolean | null;
}

export interface DeviceConfigPublishResult {
  command_id: string;
  gateway_id: string;
  device_id: string;
  gym_id: string;
  device_type: DeviceType;
  topic: string;
  qos: number;
  retain: boolean;
  payload: Record<string, unknown>;
  status: 'pending' | 'succeeded' | 'failed' | 'timed_out';
  attempt_count: number;
  max_attempts: number;
  retry_backoff_s: number;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  leased_until?: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
  result_detail?: string | null;
  result_payload: Record<string, unknown>;
}

export interface AuthUser {
  username: string;
  role: UserRole | 'anonymous';
  gym_ids: string[];
  device_ids: string[];
}

export interface AuthTokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
  refresh_expires_in: number;
  user: AuthUser;
}

export interface AuthSession extends AuthTokenPair {
  issued_at_ms: number;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface LogoutRequest {
  refresh_token: string;
}

export interface UserSummary {
  username: string;
  role: UserRole;
  gym_ids: string[];
  device_ids: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface UserCreateRequest {
  username: string;
  password: string;
  role: UserRole;
  gym_ids: string[];
  device_ids: string[];
}

export interface UserUpdateRequest {
  password?: string | null;
  role?: UserRole | null;
  gym_ids?: string[] | null;
  device_ids?: string[] | null;
}

export interface UserWristbandBindingSummary {
  id: number;
  username: string;
  wristband_id: string;
  gym_id: string;
  is_active: boolean;
  bound_at: string;
  unbound_at?: string | null;
  source: 'manual' | 'imported' | 'aggregated';
  note?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface UserWristbandBindingOverviewResponse {
  active_bindings: UserWristbandBindingSummary[];
  binding_history: UserWristbandBindingSummary[];
}

export interface UserWristbandBindingCreateRequest {
  username: string;
  wristband_id: string;
  gym_id: string;
  bound_at?: string | null;
  source?: 'manual' | 'imported' | 'aggregated';
  note?: string | null;
}

export interface UserWristbandBindingUnbindRequest {
  unbound_at?: string | null;
  note?: string | null;
}

export interface WorkoutSessionMetrics {
  avg_heart_rate?: number | null;
  max_heart_rate?: number | null;
  total_steps?: number | null;
  total_rep_count?: number | null;
  total_energy_wh?: number | null;
  alert_count?: number | null;
}

export interface WorkoutSessionSegment {
  equipment_id: string;
  started_at: string;
  ended_at?: string | null;
  duration_s?: number | null;
  rep_count?: number | null;
  energy_wh?: number | null;
}

export interface WorkoutSessionSummary {
  session_id: string;
  username: string;
  wristband_id: string;
  gym_id: string;
  status: 'open' | 'completed' | 'cancelled';
  source: 'manual' | 'imported' | 'aggregated';
  started_at: string;
  ended_at?: string | null;
  duration_s?: number | null;
  equipment_ids: string[];
  segments: WorkoutSessionSegment[];
  metrics: WorkoutSessionMetrics;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkoutSessionAggregateRequest {
  username?: string | null;
  wristband_id?: string | null;
  gym_id?: string | null;
  start?: string | null;
  end?: string | null;
}

export interface WorkoutSessionAggregateResult {
  processed_bindings: number;
  created_sessions: number;
  updated_sessions: number;
  skipped_segments: number;
  sessions: WorkoutSessionSummary[];
}

export interface AiAnalyzeRequest {
  user_id: string;
  start: string;
  end: string;
}

export interface ReservedApiResponse {
  status: string;
  detail: string;
  reserved_for: string;
  docs_ref: string;
}

export interface AiReportSummary {
  report_id: string;
  user_id: string;
  status: string;
  start: string;
  end: string;
  created_at: string;
  finished_at?: string | null;
  summary_title?: string | null;
}

export interface AiReportDetail extends AiReportSummary {
  summary?: string | null;
  insights?: string[] | null;
  recommendations?: string[] | null;
  evidence_session_ids?: string[] | null;
  raw_markdown?: string | null;
}

export interface UserTrainingProfileSummary {
  total_sessions: number;
  completed_sessions: number;
  open_sessions: number;
  cancelled_sessions: number;
  total_duration_s: number;
  total_rep_count: number;
  total_energy_wh: number;
  avg_heart_rate?: number | null;
  max_heart_rate?: number | null;
  equipment_ids: string[];
  last_session_at?: string | null;
}

export interface UserTrainingProfileResponse {
  user: UserSummary;
  query_start?: string | null;
  query_end?: string | null;
  active_binding?: UserWristbandBindingSummary | null;
  recent_bindings: UserWristbandBindingSummary[];
  recent_sessions: WorkoutSessionSummary[];
  summary: UserTrainingProfileSummary;
}

export interface BatchAckResult {
  updated: number;
  items: BusinessAlertRecord[];
}

export interface DeviceStatusMessage {
  gym_id?: string;
  device_type?: DeviceType;
  device_id: string;
  online: boolean;
  ts?: number | string | null;
  status?: string;
}

export interface TelemetryMessage {
  type: 'telemetry';
  data: {
    gym_id: string;
    device_type: DeviceType;
    device_id: string;
    ts?: number | string;
  } & Record<string, unknown>;
}

export interface AlertMessage {
  type: 'alert';
  data: BusinessAlertRecord;
}

export interface DeviceStatusWsMessage {
  type: 'device_status';
  data: DeviceStatusMessage;
}

export interface PongMessage {
  type: 'pong';
  data?: Record<string, unknown>;
}

export type BusinessWsMessage = TelemetryMessage | AlertMessage | DeviceStatusWsMessage | PongMessage;
