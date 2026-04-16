import { create } from 'zustand';

import { create_business_websocket, parse_business_message } from '../api/backend_client';
import type { BusinessAlertRecord, DeviceStatusMessage, TelemetryMessage } from '../types/backend';
import { get_auth_session } from '../utils/auth_session';

const max_points = 200;
const max_alerts = 50;

interface BusinessRealtimeState {
  ws_state: 'idle' | 'connecting' | 'open' | 'closed';
  telemetry_by_device: Record<string, TelemetryMessage['data'][]>;
  recent_alerts: BusinessAlertRecord[];
  device_status: Record<string, DeviceStatusMessage>;
  connect: () => void;
  disconnect: () => void;
  clear_recent_alert: (alert_id: number) => void;
}

let websocket: WebSocket | null = null;
let reconnect_timer: number | null = null;
let ping_timer: number | null = null;
let reconnect_delay_ms = 1000;
let should_reconnect = true;

function clear_timers(): void {
  if (reconnect_timer !== null) {
    window.clearTimeout(reconnect_timer);
    reconnect_timer = null;
  }
  if (ping_timer !== null) {
    window.clearInterval(ping_timer);
    ping_timer = null;
  }
}

export const use_business_realtime_store = create<BusinessRealtimeState>((set, get) => ({
  ws_state: 'idle',
  telemetry_by_device: {},
  recent_alerts: [],
  device_status: {},
  connect: () => {
    if (websocket && (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const session = get_auth_session();
    if (!session?.access_token) {
      should_reconnect = false;
      clear_timers();
      set({ ws_state: 'idle' });
      return;
    }

    should_reconnect = true;
    clear_timers();
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
        set((state) => ({
          telemetry_by_device: {
            ...state.telemetry_by_device,
            [message.data.device_id]: [...(state.telemetry_by_device[message.data.device_id] ?? []), message.data].slice(-max_points)
          }
        }));
        return;
      }

      if (message.type === 'alert') {
        set((state) => ({
          recent_alerts: [message.data, ...state.recent_alerts.filter((item) => item.id !== message.data.id)].slice(0, max_alerts)
        }));
        return;
      }

      if (message.type === 'device_status') {
        set((state) => ({
          device_status: {
            ...state.device_status,
            [message.data.device_id]: message.data
          }
        }));
      }
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
    if (websocket) {
      websocket.close();
      websocket = null;
    }
    set({ ws_state: 'closed' });
  },
  clear_recent_alert: (alert_id: number) => {
    set((state) => ({
      recent_alerts: state.recent_alerts.filter((item) => item.id !== alert_id)
    }));
  }
}));
