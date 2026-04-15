import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

import { get_runtime_config } from '../config/runtime_config';
import type {
  AuthTokenPair,
  BatchAckResult,
  BindingEventRecord,
  BusinessAlertRecord,
  BusinessWsMessage,
  DeviceConfigPublishRequest,
  DeviceConfigPublishResult,
  DeviceSummary,
  EnvTelemetryAggregateRecord,
  LoginRequest,
  TelemetryRecord
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
  const url = new URL(runtime_config.backend_ws_url);
  if (session?.access_token) {
    url.searchParams.set('token', session.access_token);
  }
  return new WebSocket(url.toString());
}

export function parse_business_message(raw: string): BusinessWsMessage {
  return JSON.parse(raw) as BusinessWsMessage;
}
