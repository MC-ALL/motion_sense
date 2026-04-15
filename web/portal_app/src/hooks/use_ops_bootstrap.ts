import { useEffect } from 'react';

import { use_ops_store } from '../store/ops_store';

export function use_ops_bootstrap(): void {
  const bootstrap = use_ops_store((state) => state.bootstrap);
  const connect_websocket = use_ops_store((state) => state.connect_websocket);

  useEffect(() => {
    void bootstrap();
    connect_websocket();
  }, [bootstrap, connect_websocket]);
}
