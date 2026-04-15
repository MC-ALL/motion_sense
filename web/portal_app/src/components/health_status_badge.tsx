import { Tag } from 'antd';

import type { HealthStatus } from '../types/ops';

const color_map: Record<HealthStatus, string> = {
  healthy: 'green',
  degraded: 'orange',
  offline: 'red',
  unknown: 'default'
};

const label_map: Record<HealthStatus, string> = {
  healthy: '健康',
  degraded: '降级',
  offline: '离线',
  unknown: '未知'
};

export function HealthStatusBadge({ status }: { status: HealthStatus }) {
  return <Tag color={color_map[status]}>{label_map[status]}</Tag>;
}
