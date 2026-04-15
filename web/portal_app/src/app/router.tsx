import type { ComponentType, LazyExoticComponent } from 'react';
import { lazy, Suspense } from 'react';
import { createBrowserRouter, NavLink, Outlet } from 'react-router-dom';
import { Layout, Spin } from 'antd';

import { AuthSessionPanel } from '../components/auth_session_panel';
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

const EquipmentPage = lazy(async () =>
  import('../pages/equipment_page').then((module) => ({
    default: module.EquipmentPage
  }))
);

const EnvQualityPage = lazy(async () =>
  import('../pages/env_quality_page').then((module) => ({
    default: module.EnvQualityPage
  }))
);

const AlertsPage = lazy(async () =>
  import('../pages/alerts_page').then((module) => ({
    default: module.AlertsPage
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
          <NavLink to="/equipment" className={({ isActive }) => `nav_link${isActive ? ' active' : ''}`}>
            器材管理
          </NavLink>
          <NavLink to="/env-quality" className={({ isActive }) => `nav_link${isActive ? ' active' : ''}`}>
            环境质量
          </NavLink>
          <NavLink to="/alerts" className={({ isActive }) => `nav_link${isActive ? ' active' : ''}`}>
            告警管理
          </NavLink>
          <NavLink
            to="/health-center"
            className={({ isActive }) => `nav_link${isActive ? ' active' : ''}`}
          >
            系统健康中心
          </NavLink>
        </nav>
        <AuthSessionPanel />
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
      { index: true, element: render_lazy_page(RealtimeDashboardPage) },
      { path: 'dashboard', element: render_lazy_page(RealtimeDashboardPage) },
      { path: 'equipment', element: render_lazy_page(EquipmentPage) },
      { path: 'env-quality', element: render_lazy_page(EnvQualityPage) },
      { path: 'alerts', element: render_lazy_page(AlertsPage) },
      { path: 'health-center', element: render_lazy_page(HealthCenterPage) }
    ]
  }
]);
