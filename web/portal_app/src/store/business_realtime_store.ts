import { create } from 'zustand';

import { create_business_websocket, parse_business_message } from '../api/backend_client';
import type {
  AiReportDetail,
  BusinessAlertRecord,
  BusinessWsMessage,
  DeviceStatusMessage,
  DeviceSummary,
  TelemetryMessage
} from '../types/backend';
import { get_auth_session } from '../utils/auth_session';

const max_points = 200;
const max_alerts = 50;
const max_alert_index = 1000;
const telemetry_flush_interval_ms = 250;

interface BusinessRealtimeState {
  ws_state: 'idle' | 'connecting' | 'open' | 'closed';
  telemetry_by_device: Record<string, TelemetryMessage['data'][]>;
  recent_alerts: BusinessAlertRecord[];
  device_status: Record<string, DeviceStatusMessage>;
  devices_by_id: Record<string, DeviceSummary>;
  alerts_by_id: Record<number, BusinessAlertRecord>;
  ai_reports_by_id: Record<string, AiReportDetail>;
  connect: () => void;
  disconnect: () => void;
  hydrate_snapshot: (payload: { devices: DeviceSummary[]; alerts: BusinessAlertRecord[] }) => void;
  clear_snapshot: () => void;
  replace_ai_reports: (reports: AiReportDetail[]) => void;
  upsert_ai_report: (report: AiReportDetail) => void;
  clear_recent_alert: (alert_id: number) => void;
}

let websocket: WebSocket | null = null;
let reconnect_timer: number | null = null;
let ping_timer: number | null = null;
let telemetry_flush_timer: number | null = null;
let reconnect_delay_ms = 1000;
let should_reconnect = true;
let pending_telemetry_by_device: Record<string, TelemetryMessage['data']> = {};

function clear_timers(): void {
  if (reconnect_timer !== null) {
    window.clearTimeout(reconnect_timer);
    reconnect_timer = null;
  }
  if (ping_timer !== null) {
    window.clearInterval(ping_timer);
    ping_timer = null;
  }
  if (telemetry_flush_timer !== null) {
    window.clearTimeout(telemetry_flush_timer);
    telemetry_flush_timer = null;
  }
}

function clear_pending_telemetry(): void {
  pending_telemetry_by_device = {};
}

function to_unix_seconds(value: unknown): number | null {
  if (typeof value === 'number') {
    return value > 1_000_000_000_000 ? Math.floor(value / 1000) : Math.floor(value);
  }
  if (typeof value === 'string') {
    const numeric = Number(value);
    if (!Number.isNaN(numeric) && value.trim() !== '') {
      return numeric > 1_000_000_000_000 ? Math.floor(numeric / 1000) : Math.floor(numeric);
    }
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : Math.floor(parsed / 1000);
  }
  return null;
}

function extract_live_payload(data: TelemetryMessage['data']): Record<string, unknown> {
  const { gym_id: _gym_id, device_type: _device_type, device_id: _device_id, ...payload } = data;
  return payload;
}

function apply_telemetry_messages(
  state: BusinessRealtimeState,
  messages: TelemetryMessage['data'][]
): Pick<BusinessRealtimeState, 'telemetry_by_device' | 'devices_by_id'> {
  if (messages.length === 0) {
    return {
      telemetry_by_device: state.telemetry_by_device,
      devices_by_id: state.devices_by_id
    };
  }

  const telemetry_by_device = { ...state.telemetry_by_device };
  let devices_by_id = state.devices_by_id;

  for (const data of messages) {
    telemetry_by_device[data.device_id] = [...(telemetry_by_device[data.device_id] ?? []), data].slice(-max_points);

    const current_device = devices_by_id[data.device_id];
    if (!current_device) {
      continue;
    }

    if (devices_by_id === state.devices_by_id) {
      devices_by_id = { ...state.devices_by_id };
    }
    devices_by_id[data.device_id] = {
      ...current_device,
      online: true,
      status: state.device_status[data.device_id]?.status ?? current_device.status,
      last_seen_ts: to_unix_seconds(data.ts) ?? current_device.last_seen_ts,
      last_payload: {
        ...current_device.last_payload,
        ...extract_live_payload(data)
      }
    };
  }

  return { telemetry_by_device, devices_by_id };
}

function apply_alert_message(
  state: BusinessRealtimeState,
  alert: BusinessAlertRecord
): Pick<BusinessRealtimeState, 'recent_alerts' | 'alerts_by_id'> {
  const recent_alerts = alert.is_ack
    ? state.recent_alerts.filter((item) => item.id !== alert.id)
    : [alert, ...state.recent_alerts.filter((item) => item.id !== alert.id)].slice(0, max_alerts);

  return {
    recent_alerts,
    alerts_by_id: trim_alert_index({
      ...state.alerts_by_id,
      [alert.id]: alert
    })
  };
}

function trim_alert_index(alerts_by_id: Record<number, BusinessAlertRecord>): Record<number, BusinessAlertRecord> {
  const alerts = Object.values(alerts_by_id);
  if (alerts.length <= max_alert_index) {
    return alerts_by_id;
  }
  return Object.fromEntries(
    alerts
      .sort((left, right) => {
        const left_ts = Date.parse(left.triggered_at);
        const right_ts = Date.parse(right.triggered_at);
        if (!Number.isNaN(left_ts) && !Number.isNaN(right_ts) && left_ts !== right_ts) {
          return right_ts - left_ts;
        }
        return right.id - left.id;
      })
      .slice(0, max_alert_index)
      .map((item) => [item.id, item])
  );
}

function apply_status_message(
  state: BusinessRealtimeState,
  status_message: DeviceStatusMessage
): Pick<BusinessRealtimeState, 'device_status' | 'devices_by_id'> {
  const device_status = {
    ...state.device_status,
    [status_message.device_id]: status_message
  };

  const current_device = state.devices_by_id[status_message.device_id];
  if (!current_device) {
    return {
      device_status,
      devices_by_id: state.devices_by_id
    };
  }

  return {
    device_status,
    devices_by_id: {
      ...state.devices_by_id,
      [status_message.device_id]: {
        ...current_device,
        online: status_message.online,
        status: status_message.status ?? current_device.status,
        last_seen_ts: to_unix_seconds(status_message.ts) ?? current_device.last_seen_ts
      }
    }
  };
}

function remove_device_snapshot(
  state: BusinessRealtimeState,
  device_id: string
): Pick<BusinessRealtimeState, 'devices_by_id' | 'telemetry_by_device' | 'device_status'> {
  const devices_by_id = { ...state.devices_by_id };
  const telemetry_by_device = { ...state.telemetry_by_device };
  const device_status = { ...state.device_status };

  delete devices_by_id[device_id];
  delete telemetry_by_device[device_id];
  delete device_status[device_id];

  return {
    devices_by_id,
    telemetry_by_device,
    device_status
  };
}

function apply_binding_upsert_message(
  state: BusinessRealtimeState,
  message: Extract<BusinessWsMessage, { type: 'binding_upsert' }>
): Pick<BusinessRealtimeState, 'devices_by_id'> {
  const current_device = state.devices_by_id[message.data.wristband_id];
  if (!current_device) {
    return { devices_by_id: state.devices_by_id };
  }
  return {
    devices_by_id: {
      ...state.devices_by_id,
      [message.data.wristband_id]: {
        ...current_device,
        online: true,
        status: message.data.status ?? current_device.status,
        last_seen_ts: to_unix_seconds(message.data.ts) ?? current_device.last_seen_ts,
        last_payload: {
          ...current_device.last_payload,
          current_equipment_id: message.data.equipment_id
        }
      }
    }
  };
}

function apply_binding_remove_message(
  state: BusinessRealtimeState,
  message: Extract<BusinessWsMessage, { type: 'binding_remove' }>
): Pick<BusinessRealtimeState, 'devices_by_id'> {
  const current_device = state.devices_by_id[message.data.wristband_id];
  if (!current_device) {
    return { devices_by_id: state.devices_by_id };
  }
  return {
    devices_by_id: {
      ...state.devices_by_id,
      [message.data.wristband_id]: {
        ...current_device,
        online: true,
        status: message.data.status ?? current_device.status,
        last_seen_ts: to_unix_seconds(message.data.ts) ?? current_device.last_seen_ts,
        last_payload: {
          ...current_device.last_payload,
          current_equipment_id: null
        }
      }
    }
  };
}

function handle_business_message(state: BusinessRealtimeState, message: BusinessWsMessage): Partial<BusinessRealtimeState> | null {
  switch (message.type) {
    case 'telemetry':
      return null;
    case 'alert':
      return apply_alert_message(state, message.data);
    case 'device_status':
      return apply_status_message(state, message.data);
    case 'device_upsert':
      return {
        devices_by_id: {
          ...state.devices_by_id,
          [message.data.device_id]: message.data
        }
      };
    case 'device_delete':
      return remove_device_snapshot(state, message.data.device_id);
    case 'binding_upsert':
      return apply_binding_upsert_message(state, message);
    case 'binding_remove':
      return apply_binding_remove_message(state, message);
    case 'ai_report':
      return {
        ai_reports_by_id: {
          ...state.ai_reports_by_id,
          [message.data.report_id]: message.data
        }
      };
    default:
      return null;
  }
}

export const use_business_realtime_store = create<BusinessRealtimeState>((set, get) => ({
  ws_state: 'idle',
  telemetry_by_device: {},
  recent_alerts: [],
  device_status: {},
  devices_by_id: {},
  alerts_by_id: {},
  ai_reports_by_id: {},
  connect: () => {
    if (websocket && (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const session = get_auth_session();
    if (!session?.access_token) {
      should_reconnect = false;
      clear_timers();
      clear_pending_telemetry();
      set({ ws_state: 'idle' });
      return;
    }

    should_reconnect = true;
    clear_timers();
    clear_pending_telemetry();
    set({ ws_state: 'connecting' });
    websocket = create_business_websocket();

    websocket.onopen = () => {
      reconnect_delay_ms = 1000;
      set({ ws_state: 'open' });
      ping_timer = window.setInterval(() => {
        if (websocket?.readyState === WebSocket.OPEN) {
          websocket.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    websocket.onmessage = (event) => {
      const message = parse_business_message(event.data);
      if (message.type === 'telemetry') {
        pending_telemetry_by_device[message.data.device_id] = message.data;
        if (telemetry_flush_timer === null) {
          telemetry_flush_timer = window.setTimeout(() => {
            telemetry_flush_timer = null;
            const pending_messages = Object.values(pending_telemetry_by_device);
            clear_pending_telemetry();
            if (pending_messages.length > 0) {
              set((state) => apply_telemetry_messages(state, pending_messages));
            }
          }, telemetry_flush_interval_ms);
        }
        return;
      }
      set((state) => handle_business_message(state, message) ?? {});
    };

    websocket.onclose = () => {
      clear_timers();
      websocket = null;
      set({ ws_state: 'closed' });
      if (!should_reconnect) {
        return;
      }
      reconnect_timer = window.setTimeout(() => {
        reconnect_delay_ms = Math.min(reconnect_delay_ms * 2, 30000);
        get().connect();
      }, reconnect_delay_ms);
    };
  },
  disconnect: () => {
    should_reconnect = false;
    clear_timers();
    clear_pending_telemetry();
    if (websocket) {
      websocket.close();
      websocket = null;
    }
    set({ ws_state: 'closed' });
  },
  hydrate_snapshot: ({ devices, alerts }) => {
    set((state) => ({
      devices_by_id: Object.fromEntries(devices.map((item) => [item.device_id, item])),
      alerts_by_id: trim_alert_index(Object.fromEntries(alerts.map((item) => [item.id, item]))),
      recent_alerts: state.recent_alerts.filter((item) => !item.is_ack).slice(0, max_alerts)
    }));
  },
  clear_snapshot: () => {
    clear_pending_telemetry();
    set({
      telemetry_by_device: {},
      recent_alerts: [],
      device_status: {},
      devices_by_id: {},
      alerts_by_id: {},
      ai_reports_by_id: {}
    });
  },
  replace_ai_reports: (reports) => {
    set({
      ai_reports_by_id: Object.fromEntries(reports.map((item) => [item.report_id, item]))
    });
  },
  upsert_ai_report: (report) => {
    set((state) => ({
      ai_reports_by_id: {
        ...state.ai_reports_by_id,
        [report.report_id]: report
      }
    }));
  },
  clear_recent_alert: (alert_id: number) => {
    set((state) => ({
      recent_alerts: state.recent_alerts.filter((item) => item.id !== alert_id)
    }));
  }
}));
