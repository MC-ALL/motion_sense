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
  refresh_snapshot: (options?: { include_alerts?: boolean }) => Promise<void>;
  select_module: (module_id: string) => Promise<void>;
  refresh_alerts: (status?: 'open' | 'closed') => Promise<void>;
  close_alert: (alert_id: number) => Promise<void>;
  connect_websocket: () => void;
}

let websocket: WebSocket | null = null;
let reconnect_timer: number | null = null;

async function load_ops_snapshot(
  selected_module_id: string | null,
  options?: { include_alerts?: boolean }
): Promise<{
  summaries: ModuleHealthSummary[];
  detail: OpsHealthDetailResponse | null;
  alerts: OpsAlertRecord[] | null;
  stats: OpsStatsResponse['items'];
  selected_module_id: string | null;
}> {
  const include_alerts = options?.include_alerts ?? true;
  const [health, alerts, stats] = await Promise.all([
    fetch_ops_health(),
    include_alerts ? fetch_ops_alerts('open') : Promise.resolve(null),
    fetch_ops_stats()
  ]);
  const next_selected_module_id = selected_module_id ?? health.items[0]?.module_id ?? null;
  const detail = next_selected_module_id ? await fetch_ops_health_detail(next_selected_module_id) : null;

  return {
    summaries: health.items,
    detail,
    alerts: alerts ? alerts.items : null,
    stats: stats.items,
    selected_module_id: next_selected_module_id
  };
}

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
      const snapshot = await load_ops_snapshot(get().selected_module_id, { include_alerts: true });
      set({
        loading: false,
        summaries: snapshot.summaries,
        alerts: snapshot.alerts ?? [],
        stats: snapshot.stats,
        selected_module_id: snapshot.selected_module_id,
        detail: snapshot.detail
      });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : 'load failed'
      });
    }
  },
  refresh_snapshot: async (options = { include_alerts: false }) => {
    try {
      const snapshot = await load_ops_snapshot(get().selected_module_id, options);
      set((state) => ({
        error: null,
        summaries: snapshot.summaries,
        stats: snapshot.stats,
        selected_module_id: snapshot.selected_module_id,
        detail: snapshot.detail,
        alerts: snapshot.alerts ?? state.alerts
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'refresh failed'
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
        await get().refresh_snapshot({ include_alerts: false });
      }
      if (message.type === 'ops_alert') {
        await Promise.all([get().refresh_snapshot({ include_alerts: false }), get().refresh_alerts('open')]);
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
