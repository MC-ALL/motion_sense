import { Table } from 'antd';
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

export function ModuleDetailPanel({ detail }: { detail: OpsHealthDetailResponse | null }) {
  if (!detail) {
    return (
      <div className="panel_surface detail_surface empty_state">
        <div className="eyebrow">模块详情</div>
        <h3>请选择左侧模块</h3>
      </div>
    );
  }

  return (
    <div className="panel_surface detail_surface">
      <div className="panel_header">
        <div>
          <div className="eyebrow">模块详情</div>
          <h3>{detail.summary.display_name ?? detail.summary.module_id}</h3>
        </div>
        <HealthStatusBadge status={detail.summary.health_status} />
      </div>
      <div className="detail_grid">
        <div className="detail_metric">
          <span>总组件数</span>
          <strong>{detail.summary.component_total}</strong>
        </div>
        <div className="detail_metric">
          <span>健康组件</span>
          <strong>{detail.summary.healthy_components}</strong>
        </div>
        <div className="detail_metric">
          <span>离线组件</span>
          <strong>{detail.summary.offline_components}</strong>
        </div>
        <div className="detail_metric">
          <span>最近检查</span>
          <strong>{format_time(detail.summary.checked_at)}</strong>
        </div>
      </div>
      <Table
        rowKey="component_id"
        dataSource={detail.components}
        columns={columns}
        pagination={false}
        size="small"
      />
      <pre className="stats_panel">{JSON.stringify(detail.stats?.data ?? {}, null, 2)}</pre>
    </div>
  );
}
