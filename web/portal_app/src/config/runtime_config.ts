export interface RuntimeConfig {
  app_name: string;
  backend_base_url: string;
  backend_ws_url: string;
  ops_base_url: string;
  ops_ws_url: string;
  refresh_interval_ms: number;
}

declare global {
  interface Window {
    __motion_sense_runtime__?: Partial<RuntimeConfig>;
  }
}

const default_config: RuntimeConfig = {
  app_name: '粤动智感运维门户',
  backend_base_url: 'http://127.0.0.1:18000',
  backend_ws_url: 'ws://127.0.0.1:18000/api/ws',
  ops_base_url: 'http://127.0.0.1:18090',
  ops_ws_url: 'ws://127.0.0.1:18090/api/ws/ops',
  refresh_interval_ms: 15000
};

export function get_runtime_config(): RuntimeConfig {
  return {
    ...default_config,
    ...window.__motion_sense_runtime__
  };
}
