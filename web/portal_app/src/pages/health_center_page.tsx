import { lazy, Suspense, useMemo, useState } from 'react';
import { Alert, Button, Drawer, Layout, Spin, Statistic } from 'antd';
import { useNavigate } from 'react-router-dom';

import { ModuleSummaryList } from '../components/module_summary_list';
import { use_auth_store } from '../store/auth_store';
import { use_ops_bootstrap } from '../hooks/use_ops_bootstrap';
import { use_ops_store } from '../store/ops_store';

const HealthOverviewChart = lazy(async () =>
  import('../components/health_overview_chart').then((module) => ({
    default: module.HealthOverviewChart
  }))
);

const ModuleDetailPanel = lazy(async () =>
  import('../components/module_detail_panel').then((module) => ({
    default: module.ModuleDetailPanel
  }))
);

type ModuleFilter = 'all' | 'healthy' | 'degraded' | 'offline';

function filter_summaries<T extends { health_status: string }>(items: T[], filter: ModuleFilter): T[] {
  if (filter === 'all') {
    return items;
  }
  return items.filter((item) => item.health_status === filter);
}

function HealthMetricCard({
  title,
  value,
  on_open
}: {
  title: string;
  value: number;
  on_open: (() => void) | null;
}) {
  const is_clickable = value > 0 && on_open !== null;

  if (!is_clickable) {
    return (
      <div className="panel_surface metric_card metric_card_disabled">
        <Statistic title={title} value={value === 0 ? '无' : value} />
      </div>
    );
  }

  return (
    <button type="button" className="panel_surface metric_card interactive_metric_card" onClick={on_open}>
      <Statistic title={title} value={value} />
    </button>
  );
}

export function HealthCenterPage() {
  const navigate = useNavigate();
  const session = use_auth_store((state) => state.session);
  const is_admin = session?.user.role === 'admin';
  const [drawer_filter, set_drawer_filter] = useState<ModuleFilter>('all');
  const [drawer_open, set_drawer_open] = useState(false);

  use_ops_bootstrap({ enabled: is_admin });

  const loading = use_ops_store((state) => state.loading);
  const summaries = use_ops_store((state) => state.summaries);
  const detail = use_ops_store((state) => state.detail);
  const alerts = use_ops_store((state) => state.alerts);
  const error = use_ops_store((state) => state.error);
  const ws_state = use_ops_store((state) => state.ws_state);
  const selected_module_id = use_ops_store((state) => state.selected_module_id);
  const bootstrap = use_ops_store((state) => state.bootstrap);
  const select_module = use_ops_store((state) => state.select_module);

  if (!session || !is_admin) {
    return (
      <Layout className="page_shell">
        <section className="hero_banner compact_hero_banner">
          <div>
            <div className="eyebrow">06 网页端 / 系统健康中心</div>
            <h1>当前账号没有运维观测权限</h1>
            <p>运维健康视图当前仅对 <code>admin</code> 角色开放。</p>
          </div>
        </section>
        <Alert
          type="warning"
          message={session ? '需要管理员权限' : '请先登录后台管理员账号'}
          description={session ? `当前角色：${session.user.role}` : '未登录时不会访问 ops_observer 接口'}
          showIcon
        />
      </Layout>
    );
  }

  const healthy_count = summaries.filter((item) => item.health_status === 'healthy').length;
  const degraded_count = summaries.filter((item) => item.health_status === 'degraded').length;
  const offline_count = summaries.filter((item) => item.health_status === 'offline').length;
  const drawer_items = useMemo(() => filter_summaries(summaries, drawer_filter), [drawer_filter, summaries]);

  function open_module_drawer(filter: ModuleFilter) {
    set_drawer_filter(filter);
    set_drawer_open(true);
  }

  return (
    <Layout className="page_shell">
      <section className="hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 系统健康中心</div>
          <h1>基础设施正在被看见</h1>
          <p>统一查看网关、后台与关键组件的健康状态。</p>
        </div>
        <div className="hero_actions">
          <Button type="primary" size="large" onClick={() => void bootstrap()}>
            手动刷新
          </Button>
          <div className="ws_indicator">运维 WS: {ws_state}</div>
        </div>
      </section>

      {error ? <Alert type="error" message="加载失败" description={error} showIcon /> : null}

      <section className="metric_grid metric_grid_five">
        <HealthMetricCard title="模块总数" value={summaries.length} on_open={summaries.length > 0 ? () => open_module_drawer('all') : null} />
        <HealthMetricCard title="健康模块" value={healthy_count} on_open={healthy_count > 0 ? () => open_module_drawer('healthy') : null} />
        <HealthMetricCard title="降级模块" value={degraded_count} on_open={degraded_count > 0 ? () => open_module_drawer('degraded') : null} />
        <HealthMetricCard title="离线模块" value={offline_count} on_open={offline_count > 0 ? () => open_module_drawer('offline') : null} />
        <button
          type="button"
          className="panel_surface metric_card interactive_metric_card"
          onClick={() => navigate('/alerts?tab=ops')}
        >
          <Statistic title="运维告警" value={alerts.length} />
        </button>
      </section>

      <section className="content_grid health_content_grid">
        <div className="left_column">
          <div className="panel_surface chart_surface">
            <div className="panel_header">
              <div>
                <div className="eyebrow">健康占比</div>
                <h3>模块状态分布</h3>
              </div>
              <Button onClick={() => open_module_drawer('all')}>打开模块列表</Button>
            </div>
            <Suspense
              fallback={
                <div className="loading_surface">
                  <Spin size="large" />
                </div>
              }
            >
              <HealthOverviewChart summaries={summaries} />
            </Suspense>
          </div>
        </div>

        <div className="right_column">
          {loading ? (
            <div className="panel_surface loading_surface">
              <Spin size="large" />
            </div>
          ) : (
            <Suspense
              fallback={
                <div className="panel_surface loading_surface">
                  <Spin size="large" />
                </div>
              }
            >
              <ModuleDetailPanel detail={detail} />
            </Suspense>
          )}
        </div>
      </section>

      <Drawer
        title={`模块列表 · ${drawer_filter === 'all' ? '全部' : drawer_filter}`}
        placement="right"
        width={420}
        onClose={() => set_drawer_open(false)}
        open={drawer_open}
      >
        <ModuleSummaryList
          summaries={drawer_items}
          selected_module_id={selected_module_id}
          on_select={(module_id) => {
            void select_module(module_id);
            set_drawer_open(false);
          }}
        />
      </Drawer>
    </Layout>
  );
}
