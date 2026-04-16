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
  created_at?: string | null;
  updated_at?: string | null;
}

export interface UserCreateRequest {
  username: string;
  password: string;
  role: UserRole;
}

export interface UserUpdateRequest {
  password?: string | null;
  role?: UserRole | null;
}

export interface BatchAckResult {
  updated: number;
  items: BusinessAlertRecord[];
}

export interface DeviceStatusMessage {
  device_id: string;
  online: boolean;
  ts?: number | string | null;
  status?: string;
}

export interface TelemetryMessage {
  type: 'telemetry';
  data: {
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
