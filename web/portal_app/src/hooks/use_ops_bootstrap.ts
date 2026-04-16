import { useEffect } from 'react';

import { use_ops_store } from '../store/ops_store';

export function use_ops_bootstrap(options?: { enabled?: boolean }): void {
  const enabled = options?.enabled ?? true;
  const bootstrap = use_ops_store((state) => state.bootstrap);
  const connect_websocket = use_ops_store((state) => state.connect_websocket);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    void bootstrap();
    connect_websocket();
  }, [bootstrap, connect_websocket, enabled]);
}
