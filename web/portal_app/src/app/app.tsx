import { ConfigProvider, theme } from 'antd';
import { RouterProvider } from 'react-router-dom';

import { router } from './router';

export function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#125b56',
          colorInfo: '#125b56',
          borderRadius: 18,
          fontFamily: 'Avenir Next, PingFang SC, Hiragino Sans GB, sans-serif'
        }
      }}
    >
      <RouterProvider router={router} />
    </ConfigProvider>
  );
}
