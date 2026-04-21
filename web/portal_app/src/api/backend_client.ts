import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

import { get_runtime_config } from '../config/runtime_config';
import type {
  AiAnalyzeRequest,
  AiReportDetail,
  AiReportSummary,
  AuthTokenPair,
  BatchAckResult,
  BindingEventRecord,
  BusinessAlertRecord,
  BusinessWsMessage,
  DeviceConfigPublishRequest,
  DeviceConfigPublishResult,
  DeviceRegistrationRequest,
  DeviceRegistrationUpdateRequest,
  DeviceSummary,
  EnvTelemetryAggregateRecord,
  LoginRequest,
  TelemetryRecord,
  UserCreateRequest,
  UserWristbandBindingOverviewResponse,
  UserWristbandBindingCreateRequest,
  UserWristbandBindingSummary,
  UserWristbandBindingUnbindRequest,
  UserTrainingProfileResponse,
  UserSummary,
  UserUpdateRequest,
  WorkoutSessionSummary,
  WorkoutSessionAggregateRequest,
  WorkoutSessionAggregateResult
} from '../types/backend';
import { clear_auth_session, get_auth_session, save_auth_session } from '../utils/auth_session';

const runtime_config = get_runtime_config();

const backend_client = axios.create({
  baseURL: runtime_config.backend_base_url,
  timeout: 8000
});

const auth_client = axios.create({
  baseURL: runtime_config.backend_base_url,
  timeout: 8000
});

let refresh_promise: Promise<AuthTokenPair | null> | null = null;

backend_client.interceptors.request.use((config) => attach_authorization(config));
backend_client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    if (!config || error.response?.status !== 401 || config._retry) {
      throw error;
    }

    const session = get_auth_session();
    if (!session?.refresh_token) {
      clear_auth_session();
      throw error;
    }

    config._retry = true;
    const refreshed = await refresh_session(session.refresh_token);
    if (!refreshed) {
      clear_auth_session();
      throw error;
    }

    config.headers.set('Authorization', `Bearer ${refreshed.access_token}`);
    return backend_client.request(config);
  }
);

function attach_authorization(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  const session = get_auth_session();
  if (session?.access_token) {
    config.headers.set('Authorization', `Bearer ${session.access_token}`);
  }
  return config;
}

async function refresh_session(refresh_token: string): Promise<AuthTokenPair | null> {
  if (!refresh_promise) {
    refresh_promise = auth_client
      .post<AuthTokenPair>('/api/v1/auth/refresh', { refresh_token })
      .then((response) => save_auth_session(response.data))
      .catch(() => {
        clear_auth_session();
        return null;
      })
      .finally(() => {
        refresh_promise = null;
      });
  }

  return refresh_promise;
}

export async function login_backend(payload: LoginRequest): Promise<AuthTokenPair> {
  const response = await auth_client.post<AuthTokenPair>('/api/v1/auth/login', payload);
  save_auth_session(response.data);
  return response.data;
}

export async function logout_backend(): Promise<void> {
  const session = get_auth_session();
  try {
    if (session?.refresh_token) {
      await auth_client.post('/api/v1/auth/logout', { refresh_token: session.refresh_token });
    }
  } finally {
    clear_auth_session();
  }
}

export async function fetch_users(): Promise<UserSummary[]> {
  const response = await backend_client.get<UserSummary[]>('/api/v1/users');
  return response.data;
}

export async function create_user(payload: UserCreateRequest): Promise<UserSummary> {
  const response = await backend_client.post<UserSummary>('/api/v1/users', payload);
  return response.data;
}

export async function update_user(username: string, payload: UserUpdateRequest): Promise<UserSummary> {
  const response = await backend_client.patch<UserSummary>(`/api/v1/users/${username}`, payload);
  return response.data;
}

export async function delete_user(username: string): Promise<void> {
  await backend_client.delete(`/api/v1/users/${username}`);
}

export async function fetch_user_training_profile(
  username: string,
  params?: {
    start?: string;
    end?: string;
    binding_limit?: number;
    session_limit?: number;
  }
): Promise<UserTrainingProfileResponse> {
  const response = await backend_client.get<UserTrainingProfileResponse>(`/api/v1/users/${username}/training-profile`, {
    params
  });
  return response.data;
}

export async function aggregate_workout_sessions(
  payload: WorkoutSessionAggregateRequest
): Promise<WorkoutSessionAggregateResult> {
  const response = await backend_client.post<WorkoutSessionAggregateResult>('/api/v1/workout-sessions/aggregate', payload);
  return response.data;
}

export async function analyze_ai_report(payload: AiAnalyzeRequest): Promise<AiReportDetail> {
  const response = await backend_client.post<AiReportDetail>('/api/v1/ai/analyze', payload);
  return response.data;
}

export async function fetch_ai_reports(params?: {
  user_id?: string;
  status?: string;
  start?: string;
  end?: string;
}): Promise<AiReportSummary[]> {
  const response = await backend_client.get<AiReportSummary[]>('/api/v1/ai/reports', {
    params
  });
  return response.data;
}

export async function fetch_ai_report_detail(report_id: string): Promise<AiReportDetail> {
  const response = await backend_client.get<AiReportDetail>(`/api/v1/ai/reports/${report_id}`);
  return response.data;
}

export async function fetch_workout_sessions(params?: {
  username?: string;
  wristband_id?: string;
  gym_id?: string;
  status?: 'open' | 'completed' | 'cancelled';
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
}): Promise<WorkoutSessionSummary[]> {
  const response = await backend_client.get<WorkoutSessionSummary[]>('/api/v1/workout-sessions', {
    params
  });
  return response.data;
}

export async function create_user_wristband_binding(
  payload: UserWristbandBindingCreateRequest
): Promise<UserWristbandBindingSummary> {
  const response = await backend_client.post<UserWristbandBindingSummary>('/api/v1/user-wristband-bindings', payload);
  return response.data;
}

export async function fetch_user_wristband_bindings(params?: {
  username?: string;
  wristband_id?: string;
  gym_id?: string;
  active_only?: boolean;
  limit?: number;
  offset?: number;
}): Promise<UserWristbandBindingSummary[]> {
  const response = await backend_client.get<UserWristbandBindingSummary[]>('/api/v1/user-wristband-bindings', {
    params
  });
  return response.data;
}

export async function fetch_user_wristband_binding_overview(params?: {
  username?: string;
  wristband_id?: string;
  gym_id?: string;
  active_limit?: number;
  history_limit?: number;
}): Promise<UserWristbandBindingOverviewResponse> {
  const response = await backend_client.get<UserWristbandBindingOverviewResponse>('/api/v1/user-wristband-bindings/overview', {
    params
  });
  return response.data;
}

export async function end_user_wristband_binding(
  binding_id: number,
  payload: UserWristbandBindingUnbindRequest
): Promise<UserWristbandBindingSummary> {
  const response = await backend_client.post<UserWristbandBindingSummary>(
    `/api/v1/user-wristband-bindings/${binding_id}/unbind`,
    payload
  );
  return response.data;
}

export async function fetch_devices(params?: {
  type?: string;
  status?: string;
}): Promise<DeviceSummary[]> {
  const response = await backend_client.get<DeviceSummary[]>('/api/v1/devices', { params });
  return response.data;
}

export async function fetch_device(device_id: string): Promise<DeviceSummary> {
  const response = await backend_client.get<DeviceSummary>(`/api/v1/devices/${device_id}`);
  return response.data;
}

export async function create_device_registration(payload: DeviceRegistrationRequest): Promise<DeviceSummary> {
  const response = await backend_client.post<DeviceSummary>('/api/v1/devices', payload);
  return response.data;
}

export async function update_device_registration(
  device_id: string,
  payload: DeviceRegistrationUpdateRequest
): Promise<DeviceSummary> {
  const response = await backend_client.patch<DeviceSummary>(`/api/v1/devices/${device_id}`, payload);
  return response.data;
}

export async function delete_device_registration(device_id: string): Promise<void> {
  await backend_client.delete(`/api/v1/devices/${device_id}`);
}

export async function fetch_business_alerts(params?: {
  level?: string;
  is_ack?: boolean;
  device_id?: string;
}): Promise<BusinessAlertRecord[]> {
  const response = await backend_client.get<BusinessAlertRecord[]>('/api/v1/alerts', { params });
  return response.data;
}

export async function ack_business_alert(alert_id: number): Promise<BusinessAlertRecord> {
  const response = await backend_client.patch<BusinessAlertRecord>(`/api/v1/alerts/${alert_id}/ack`);
  return response.data;
}

export async function batch_ack_business_alerts(ids: number[]): Promise<BatchAckResult> {
  const response = await backend_client.post<BatchAckResult>('/api/v1/alerts/batch-ack', { ids });
  return response.data;
}

export async function fetch_equipment_telemetry(device_id: string, params?: Record<string, unknown>): Promise<TelemetryRecord[]> {
  const response = await backend_client.get<TelemetryRecord[]>(`/api/v1/telemetry/equipment/${device_id}`, {
    params
  });
  return response.data;
}

export async function fetch_env_telemetry(device_id: string, params?: Record<string, unknown>): Promise<TelemetryRecord[]> {
  const response = await backend_client.get<TelemetryRecord[]>(`/api/v1/telemetry/env/${device_id}`, {
    params
  });
  return response.data;
}

export async function fetch_wristband_telemetry(device_id: string, params?: Record<string, unknown>): Promise<TelemetryRecord[]> {
  const response = await backend_client.get<TelemetryRecord[]>(`/api/v1/telemetry/wristband/${device_id}`, {
    params
  });
  return response.data;
}

export async function fetch_env_aggregate(device_id: string, params?: Record<string, unknown>): Promise<EnvTelemetryAggregateRecord[]> {
  const response = await backend_client.get<EnvTelemetryAggregateRecord[]>(
    `/api/v1/telemetry/env/${device_id}/aggregate`,
    { params }
  );
  return response.data;
}

export async function fetch_wristband_bindings(device_id: string, params?: Record<string, unknown>): Promise<BindingEventRecord[]> {
  const response = await backend_client.get<BindingEventRecord[]>(`/api/v1/wristband/${device_id}/bindings`, {
    params
  });
  return response.data;
}

export async function publish_device_config(
  device_id: string,
  payload: DeviceConfigPublishRequest
): Promise<DeviceConfigPublishResult> {
  const response = await backend_client.post<DeviceConfigPublishResult>(`/api/v1/devices/${device_id}/config`, payload);
  return response.data;
}

export function create_business_websocket(): WebSocket {
  const session = get_auth_session();
  const url = new URL(runtime_config.backend_ws_url, window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (session?.access_token) {
    url.searchParams.set('token', session.access_token);
  }
  return new WebSocket(url.toString());
}

export function parse_business_message(raw: string): BusinessWsMessage {
  return JSON.parse(raw) as BusinessWsMessage;
}
