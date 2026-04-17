import { useState } from 'react';

import { Collapse, Drawer, Empty, List, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { ModuleComponent, OpsHealthDetailResponse } from '../types/ops';
import { format_time } from '../utils/time';
import { HealthStatusBadge } from './health_status_badge';

const columns: ColumnsType<ModuleComponent> = [
  {
    title: '组件',
    dataIndex: 'display_name',
    key: 'display_name'
  },
  {
    title: '状态',
    dataIndex: 'health_status',
    key: 'health_status',
    render: (_, record) => <HealthStatusBadge status={record.health_status} />
  },
  {
    title: '延迟',
    dataIndex: 'latency_ms',
    key: 'latency_ms',
    render: (value) => (typeof value === 'number' ? `${value} ms` : '--')
  },
  {
    title: '检查时间',
    dataIndex: 'checked_at',
    key: 'checked_at',
    render: (value) => format_time(value)
  },
  {
    title: '详情',
    dataIndex: 'detail',
    key: 'detail',
    ellipsis: true,
    render: (value: string | null | undefined) => value ?? '--'
  }
];

function render_component_list(items: ModuleComponent[], empty_text: string) {
  if (items.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty_text} />;
  }

  return (
    <List
      dataSource={items}
      renderItem={(item) => (
        <List.Item>
          <List.Item.Meta
            title={
              <span>
                {item.display_name} <HealthStatusBadge status={item.health_status} />
              </span>
            }
            description={`${item.component_id} · ${item.detail ?? '--'} · ${format_time(item.checked_at)}`}
          />
        </List.Item>
      )}
    />
  );
}

export function ModuleDetailPanel({ detail }: { detail: OpsHealthDetailResponse | null }) {
  const [active_drawer, set_active_drawer] = useState<'all' | 'healthy' | 'abnormal' | 'check_time' | null>(null);

  if (!detail) {
    return (
      <div className="panel_surface detail_surface empty_state">
        <div className="eyebrow">模块详情</div>
        <h3>请先从模块卡片打开模块列表，再选择目标模块</h3>
      </div>
    );
  }

  const current_detail = detail;
  const healthy_components = current_detail.components.filter((item) => item.health_status === 'healthy');
  const degraded_or_offline_components = current_detail.components.filter((item) => item.health_status !== 'healthy');
  const abnormal_count = current_detail.summary.degraded_components + current_detail.summary.offline_components;

  const drawer_title =
    active_drawer === 'all'
      ? '全部组件'
      : active_drawer === 'healthy'
        ? '健康组件'
        : active_drawer === 'abnormal'
          ? '异常组件'
          : '模块摘要';

  function render_drawer_content() {
    if (active_drawer === 'all') {
      return <Table rowKey="component_id" dataSource={current_detail.components} columns={columns} pagination={false} size="small" />;
    }
    if (active_drawer === 'healthy') {
      return render_component_list(healthy_components, '当前没有健康组件明细');
    }
    if (active_drawer === 'abnormal') {
      return render_component_list(degraded_or_offline_components, '当前没有异常组件');
    }
    if (active_drawer === 'check_time') {
      return (
        <div className="module_meta_stack">
          <div>模块 ID：{current_detail.summary.module_id}</div>
          <div>整体状态：{current_detail.summary.health_status}</div>
          <div>最近检查：{format_time(current_detail.summary.checked_at)}</div>
          <div>最近错误：{current_detail.summary.last_error ?? '无'}</div>
        </div>
      );
    }
    return null;
  }

  return (
    <>
      <div className="panel_surface detail_surface">
        <div className="panel_header">
          <div>
            <div className="eyebrow">模块详情</div>
            <h3>{detail.summary.display_name ?? detail.summary.module_id}</h3>
          </div>
          <HealthStatusBadge status={detail.summary.health_status} />
        </div>
        <div className="detail_grid">
          <button
            type="button"
            className={`detail_metric detail_metric_button${current_detail.summary.component_total === 0 ? ' is_disabled' : ''}`}
            onClick={() => current_detail.summary.component_total > 0 && set_active_drawer('all')}
          >
            <span>总组件数</span>
            <strong>{current_detail.summary.component_total === 0 ? '无' : current_detail.summary.component_total}</strong>
          </button>
          <button
            type="button"
            className={`detail_metric detail_metric_button${current_detail.summary.healthy_components === 0 ? ' is_disabled' : ''}`}
            onClick={() => current_detail.summary.healthy_components > 0 && set_active_drawer('healthy')}
          >
            <span>健康组件</span>
            <strong>{current_detail.summary.healthy_components === 0 ? '无' : current_detail.summary.healthy_components}</strong>
          </button>
          <button
            type="button"
            className={`detail_metric detail_metric_button${abnormal_count === 0 ? ' is_disabled' : ''}`}
            onClick={() => abnormal_count > 0 && set_active_drawer('abnormal')}
          >
            <span>异常组件</span>
            <strong>{abnormal_count === 0 ? '无' : abnormal_count}</strong>
          </button>
          <button type="button" className="detail_metric detail_metric_button" onClick={() => set_active_drawer('check_time')}>
            <span>最近检查</span>
            <strong>{format_time(current_detail.summary.checked_at)}</strong>
          </button>
        </div>
      </div>

      <div className="panel_surface">
        <div className="panel_header compact_panel_header">
          <div>
            <div className="eyebrow">模块统计</div>
            <h3>统计数据</h3>
          </div>
        </div>
        <Collapse
          className="inline_collapse"
          items={[
            {
              key: 'module-stats',
              label: '查看统计数据（JSON）',
              children: <pre className="stats_panel collapsed_stats_panel">{JSON.stringify(current_detail.stats?.data ?? {}, null, 2)}</pre>
            }
          ]}
        />
      </div>

      <Drawer title={drawer_title} placement="right" width={520} open={active_drawer !== null} onClose={() => set_active_drawer(null)}>
        {render_drawer_content()}
      </Drawer>
    </>
  );
}
