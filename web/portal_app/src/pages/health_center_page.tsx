import { lazy, Suspense } from 'react';
import { Alert, Button, Layout, Spin, Statistic } from 'antd';

import { ModuleSummaryList } from '../components/module_summary_list';
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

const OpsAlertPanel = lazy(async () =>
  import('../components/ops_alert_panel').then((module) => ({
    default: module.OpsAlertPanel
  }))
);

export function HealthCenterPage() {
  use_ops_bootstrap();

  const loading = use_ops_store((state) => state.loading);
  const summaries = use_ops_store((state) => state.summaries);
  const detail = use_ops_store((state) => state.detail);
  const alerts = use_ops_store((state) => state.alerts);
  const error = use_ops_store((state) => state.error);
  const ws_state = use_ops_store((state) => state.ws_state);
  const selected_module_id = use_ops_store((state) => state.selected_module_id);
  const bootstrap = use_ops_store((state) => state.bootstrap);
  const select_module = use_ops_store((state) => state.select_module);
  const close_alert = use_ops_store((state) => state.close_alert);

  const healthy_count = summaries.filter((item) => item.health_status === 'healthy').length;
  const degraded_count = summaries.filter((item) => item.health_status === 'degraded').length;
  const offline_count = summaries.filter((item) => item.health_status === 'offline').length;

  return (
    <Layout className="page_shell">
      <section className="hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 系统健康中心</div>
          <h1>基础设施正在被看见</h1>
          <p>
            统一查看网关、后台与关键组件的健康状态，告警关闭与状态刷新都直接对接
            <code>ops_observer</code>。
          </p>
        </div>
        <div className="hero_actions">
          <Button type="primary" size="large" onClick={() => void bootstrap()}>
            手动刷新
          </Button>
          <div className="ws_indicator">运维 WS: {ws_state}</div>
        </div>
      </section>

      {error ? <Alert type="error" message="加载失败" description={error} showIcon /> : null}

      <section className="metric_grid">
        <div className="panel_surface metric_card"><Statistic title="模块总数" value={summaries.length} /></div>
        <div className="panel_surface metric_card"><Statistic title="健康模块" value={healthy_count} /></div>
        <div className="panel_surface metric_card"><Statistic title="降级模块" value={degraded_count} /></div>
        <div className="panel_surface metric_card"><Statistic title="离线模块" value={offline_count} /></div>
      </section>

      <section className="content_grid">
        <div className="left_column">
          <div className="panel_surface chart_surface">
            <div className="panel_header">
              <div>
                <div className="eyebrow">健康占比</div>
                <h3>模块状态分布</h3>
              </div>
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
          <ModuleSummaryList
            summaries={summaries}
            selected_module_id={selected_module_id}
            on_select={(module_id) => void select_module(module_id)}
          />
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
          <Suspense
            fallback={
              <div className="panel_surface loading_surface">
                <Spin size="large" />
              </div>
            }
          >
            <OpsAlertPanel alerts={alerts} on_close={(alert_id) => void close_alert(alert_id)} />
          </Suspense>
        </div>
      </section>
    </Layout>
  );
}
