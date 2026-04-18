import axios from 'axios';

import { get_runtime_config } from '../config/runtime_config';
import { get_auth_session } from '../utils/auth_session';
import type {
  OpsAlertListResponse,
  OpsHealthDetailResponse,
  OpsHealthListResponse,
  OpsStatsResponse
} from '../types/ops';

const runtime_config = get_runtime_config();

const ops_client = axios.create({
  baseURL: runtime_config.ops_base_url,
  timeout: 5000
});

ops_client.interceptors.request.use((config) => {
  const session = get_auth_session();
  if (session?.access_token) {
    config.headers.set('Authorization', `Bearer ${session.access_token}`);
  }
  return config;
});

export async function fetch_ops_health(): Promise<OpsHealthListResponse> {
  const response = await ops_client.get<OpsHealthListResponse>('/api/v1/ops/health');
  return response.data;
}

export async function fetch_ops_health_detail(module_id: string): Promise<OpsHealthDetailResponse> {
  const response = await ops_client.get<OpsHealthDetailResponse>(`/api/v1/ops/health/${module_id}`);
  return response.data;
}

export async function fetch_ops_alerts(status?: 'open' | 'closed'): Promise<OpsAlertListResponse> {
  const response = await ops_client.get<OpsAlertListResponse>('/api/v1/ops/alerts', {
    params: status ? { status } : undefined
  });
  return response.data;
}

export async function close_ops_alert(alert_id: number) {
  const response = await ops_client.patch(`/api/v1/ops/alerts/${alert_id}/close`);
  return response.data;
}

export async function fetch_ops_stats(): Promise<OpsStatsResponse> {
  const response = await ops_client.get<OpsStatsResponse>('/api/v1/ops/stats');
  return response.data;
}

export function create_ops_websocket(): WebSocket {
  const session = get_auth_session();
  const url = new URL(runtime_config.ops_ws_url, window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (session?.access_token) {
    url.searchParams.set('token', session.access_token);
  }
  return new WebSocket(url.toString());
}
