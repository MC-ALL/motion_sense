import { create } from 'zustand';

import {
  close_ops_alert,
  create_ops_websocket,
  fetch_ops_alerts,
  fetch_ops_health,
  fetch_ops_health_detail,
  fetch_ops_stats
} from '../api/ops_client';
import type {
  ModuleHealthSummary,
  OpsAlertRecord,
  OpsHealthDetailResponse,
  OpsMessage,
  OpsStatsResponse
} from '../types/ops';

interface OpsStoreState {
  loading: boolean;
  selected_module_id: string | null;
  summaries: ModuleHealthSummary[];
  detail: OpsHealthDetailResponse | null;
  alerts: OpsAlertRecord[];
  stats: OpsStatsResponse['items'];
  ws_state: 'idle' | 'connecting' | 'open' | 'closed';
  error: string | null;
  bootstrap: () => Promise<void>;
  select_module: (module_id: string) => Promise<void>;
  refresh_alerts: (status?: 'open' | 'closed') => Promise<void>;
  close_alert: (alert_id: number) => Promise<void>;
  connect_websocket: () => void;
}

let websocket: WebSocket | null = null;
let reconnect_timer: number | null = null;

export const use_ops_store = create<OpsStoreState>((set, get) => ({
  loading: false,
  selected_module_id: null,
  summaries: [],
  detail: null,
  alerts: [],
  stats: [],
  ws_state: 'idle',
  error: null,
  bootstrap: async () => {
    set({ loading: true, error: null });
    try {
      const [health, alerts, stats] = await Promise.all([
        fetch_ops_health(),
        fetch_ops_alerts('open'),
        fetch_ops_stats()
      ]);
      const selected_module_id = get().selected_module_id ?? health.items[0]?.module_id ?? null;
      const detail = selected_module_id ? await fetch_ops_health_detail(selected_module_id) : null;
      set({
        loading: false,
        summaries: health.items,
        alerts: alerts.items,
        stats: stats.items,
        selected_module_id,
        detail
      });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : 'load failed'
      });
    }
  },
  select_module: async (module_id: string) => {
    set({ selected_module_id: module_id, loading: true, error: null });
    try {
      const detail = await fetch_ops_health_detail(module_id);
      set({ detail, loading: false });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : 'detail load failed'
      });
    }
  },
  refresh_alerts: async (status = 'open') => {
    const alerts = await fetch_ops_alerts(status);
    set({ alerts: alerts.items });
  },
  close_alert: async (alert_id: number) => {
    await close_ops_alert(alert_id);
    await get().refresh_alerts('open');
  },
  connect_websocket: () => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      return;
    }

    if (reconnect_timer !== null) {
      window.clearTimeout(reconnect_timer);
      reconnect_timer = null;
    }

    set({ ws_state: 'connecting' });
    websocket = create_ops_websocket();

    websocket.onopen = () => {
      set({ ws_state: 'open' });
    };

    websocket.onmessage = async (event) => {
      const message = JSON.parse(event.data) as OpsMessage;
      if (message.type === 'ops_snapshot') {
        await get().bootstrap();
      }
      if (message.type === 'ops_alert') {
        await get().refresh_alerts('open');
      }
    };

    websocket.onclose = () => {
      set({ ws_state: 'closed' });
      reconnect_timer = window.setTimeout(() => {
        get().connect_websocket();
      }, 3000);
    };
  }
}));
