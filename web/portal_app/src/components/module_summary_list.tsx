import { Button } from 'antd';

import { format_time } from '../utils/time';
import type { ModuleHealthSummary } from '../types/ops';
import { HealthStatusBadge } from './health_status_badge';

interface ModuleSummaryListProps {
  summaries: ModuleHealthSummary[];
  selected_module_id: string | null;
  on_select: (module_id: string) => void;
}

export function ModuleSummaryList({
  summaries,
  selected_module_id,
  on_select
}: ModuleSummaryListProps) {
  return (
    <div className="panel_surface module_list_surface">
      <div className="panel_header">
        <div>
          <div className="eyebrow">模块列表</div>
          <h3>当前健康快照</h3>
        </div>
      </div>
      <div className="module_list">
        {summaries.map((item) => {
          const active = item.module_id === selected_module_id;
          return (
            <button
              key={item.module_id}
              className={`module_item${active ? ' is_active' : ''}`}
              type="button"
              onClick={() => on_select(item.module_id)}
            >
              <div className="module_item_header">
                <div>
                  <strong>{item.display_name ?? item.module_id}</strong>
                  <div className="module_hint">{item.module_id}</div>
                </div>
                <HealthStatusBadge status={item.health_status} />
              </div>
              <div className="module_meta_row">
                <span>更新时间</span>
                <span>{format_time(item.checked_at)}</span>
              </div>
              <div className="module_meta_row">
                <span>异常组件</span>
                <span>{item.degraded_components + item.offline_components}</span>
              </div>
            </button>
          );
        })}
      </div>
      <Button type="default" block onClick={() => selected_module_id && on_select(selected_module_id)}>
        刷新当前详情
      </Button>
    </div>
  );
}
