import { Button, Empty, List } from 'antd';

import type { OpsAlertRecord } from '../types/ops';
import { format_time } from '../utils/time';

interface OpsAlertPanelProps {
  alerts: OpsAlertRecord[];
  on_close: (alert_id: number) => void;
}

export function OpsAlertPanel({ alerts, on_close }: OpsAlertPanelProps) {
  return (
    <div className="panel_surface alert_surface">
      <div className="panel_header">
        <div>
          <div className="eyebrow">运维告警</div>
          <h3>待处理告警</h3>
        </div>
      </div>
      {alerts.length === 0 ? (
        <Empty description="当前没有打开的运维告警" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          itemLayout="horizontal"
          dataSource={alerts}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button key={`close-${item.id}`} type="link" onClick={() => on_close(item.id)}>
                  关闭
                </Button>
              ]}
            >
              <List.Item.Meta
                title={item.title}
                description={`${item.detail} | ${format_time(item.created_at)}`}
              />
            </List.Item>
          )}
        />
      )}
    </div>
  );
}
