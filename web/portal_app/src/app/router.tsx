import type { ComponentType, LazyExoticComponent } from 'react';
import { lazy, Suspense } from 'react';
import { createBrowserRouter, NavLink, Outlet } from 'react-router-dom';
import { Layout, Spin } from 'antd';

import { get_runtime_config } from '../config/runtime_config';

const HealthCenterPage = lazy(async () =>
  import('../pages/health_center_page').then((module) => ({
    default: module.HealthCenterPage
  }))
);

const RealtimeDashboardPage = lazy(async () =>
  import('../pages/realtime_dashboard_page').then((module) => ({
    default: module.RealtimeDashboardPage
  }))
);

function RouteFallback() {
  return (
    <section className="panel_surface loading_surface">
      <Spin size="large" />
    </section>
  );
}

function render_lazy_page(PageComponent: LazyExoticComponent<ComponentType>) {
  return (
    <Suspense fallback={<RouteFallback />}>
      <PageComponent />
    </Suspense>
  );
}

function AppLayout() {
  const runtime_config = get_runtime_config();

  return (
    <Layout className="app_layout">
      <aside className="app_sidebar">
        <div className="brand_block">
          <div className="brand_mark">MS</div>
          <div>
            <div className="eyebrow">粤动智感</div>
            <strong>{runtime_config.app_name}</strong>
          </div>
        </div>
        <nav className="nav_group">
          <NavLink to="/dashboard" className={({ isActive }) => `nav_link${isActive ? ' active' : ''}`}>
            实时仪表盘
          </NavLink>
          <NavLink
            to="/health-center"
            className={({ isActive }) => `nav_link${isActive ? ' active' : ''}`}
          >
            系统健康中心
          </NavLink>
        </nav>
      </aside>
      <main className="app_main">
        <Outlet />
      </main>
    </Layout>
  );
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: render_lazy_page(HealthCenterPage) },
      { path: 'dashboard', element: render_lazy_page(RealtimeDashboardPage) },
      { path: 'health-center', element: render_lazy_page(HealthCenterPage) }
    ]
  }
]);
