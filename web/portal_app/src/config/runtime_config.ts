export interface RuntimeConfig {
  app_name: string;
  backend_base_url: string;
  backend_ws_url: string;
  ops_base_url: string;
  ops_ws_url: string;
}

declare global {
  interface Window {
    __motion_sense_runtime__?: Partial<RuntimeConfig>;
  }
}

const default_config: RuntimeConfig = {
  app_name: '粤动智感运维门户',
  backend_base_url: '',
  backend_ws_url: '/api/ws',
  ops_base_url: '',
  ops_ws_url: '/api/ws/ops'
};

export function get_runtime_config(): RuntimeConfig {
  return {
    ...default_config,
    ...window.__motion_sense_runtime__
  };
}
