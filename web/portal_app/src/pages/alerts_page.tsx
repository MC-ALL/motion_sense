import { useEffect, useMemo, useState } from 'react';

import { Alert, Button, Select, Space, Statistic, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { ack_business_alert, batch_ack_business_alerts, fetch_business_alerts, fetch_devices } from '../api/backend_client';
import { use_auth_store } from '../store/auth_store';
import type { BusinessAlertRecord, DeviceSummary } from '../types/backend';
import { format_time } from '../utils/time';

export function AlertsPage() {
  const [loading, set_loading] = useState(true);
  const [action_loading, set_action_loading] = useState(false);
  const [error, set_error] = useState<string | null>(null);
  const [alerts, set_alerts] = useState<BusinessAlertRecord[]>([]);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [level, set_level] = useState<string | undefined>(undefined);
  const [device_id, set_device_id] = useState<string | undefined>(undefined);
  const [ack_filter, set_ack_filter] = useState<'all' | 'acked' | 'open'>('open');
  const [selected_ids, set_selected_ids] = useState<number[]>([]);
  const session = use_auth_store((state) => state.session);
  const can_ack_alerts = session?.user.role === 'admin' || session?.user.role === 'teacher';

  async function load() {
    set_loading(true);
    set_error(null);
    try {
      const response = await fetch_business_alerts({
        level,
        device_id,
        is_ack: ack_filter === 'all' ? undefined : ack_filter === 'acked'
      });
      set_alerts(response);
    } catch (load_error) {
      set_error(load_error instanceof Error ? load_error.message : '告警加载失败');
    } finally {
      set_loading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [level, device_id, ack_filter]);

  useEffect(() => {
    let mounted = true;

    async function load_devices_for_filter() {
      try {
        const response = await fetch_devices();
        if (mounted) {
          set_devices(response);
        }
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : '设备筛选项加载失败');
        }
      }
    }

    void load_devices_for_filter();
    return () => {
      mounted = false;
    };
  }, []);

  async function ack_one(alert_id: number) {
    set_action_loading(true);
    try {
      await ack_business_alert(alert_id);
      set_selected_ids((current) => current.filter((item) => item !== alert_id));
      await load();
    } catch (action_error) {
      set_error(action_error instanceof Error ? action_error.message : '告警确认失败');
    } finally {
      set_action_loading(false);
    }
  }

  async function ack_batch() {
    if (selected_ids.length === 0) {
      return;
    }
    set_action_loading(true);
    try {
      await batch_ack_business_alerts(selected_ids);
      set_selected_ids([]);
      await load();
    } catch (action_error) {
      set_error(action_error instanceof Error ? action_error.message : '批量确认失败');
    } finally {
      set_action_loading(false);
    }
  }

  const columns: ColumnsType<BusinessAlertRecord> = [
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      render: (value: string) => <Tag color={value === 'critical' ? 'red' : value === 'warning' ? 'orange' : 'blue'}>{value}</Tag>
    },
    { title: '设备', dataIndex: 'device_id', key: 'device_id' },
    { title: '代码', dataIndex: 'code', key: 'code' },
    { title: '消息', dataIndex: 'message', key: 'message' },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (value: string | null | undefined) => value ?? '--'
    },
    {
      title: '触发时间',
      dataIndex: 'triggered_at',
      key: 'triggered_at',
      render: (value: string) => format_time(value)
    },
    {
      title: '状态',
      dataIndex: 'is_ack',
      key: 'is_ack',
      render: (value: boolean) => <Tag color={value ? 'green' : 'volcano'}>{value ? '已确认' : '未确认'}</Tag>
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button size="small" disabled={record.is_ack || !can_ack_alerts} onClick={() => void ack_one(record.id)}>
          确认
        </Button>
      )
    }
  ];

  const summary = useMemo(
    () => ({
      total: alerts.length,
      open: alerts.filter((item) => !item.is_ack).length,
      critical: alerts.filter((item) => item.level === 'critical').length,
      selected: selected_ids.length
    }),
    [alerts, selected_ids.length]
  );

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 告警管理</div>
          <h1>按级别筛选并确认业务告警</h1>
          <p>当前页面对接后台 `GET /api/v1/alerts`、`PATCH /api/v1/alerts/{'{id}'}/ack` 与 `POST /api/v1/alerts/batch-ack`。</p>
        </div>
        <Space wrap>
          <Select
            allowClear
            placeholder="按级别筛选"
            value={level}
            onChange={(value) => set_level(value)}
            options={[
              { value: 'info', label: 'info' },
              { value: 'warning', label: 'warning' },
              { value: 'critical', label: 'critical' }
            ]}
            style={{ minWidth: 160 }}
          />
          <Select
            allowClear
            showSearch
            placeholder="按设备筛选"
            value={device_id}
            onChange={(value) => set_device_id(value)}
            options={devices.map((item) => ({
              value: item.device_id,
              label: `${item.device_id} · ${item.device_type}`
            }))}
            filterOption={(input, option) => String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            style={{ minWidth: 220 }}
          />
          <Select
            value={ack_filter}
            onChange={(value) => set_ack_filter(value)}
            options={[
              { value: 'open', label: '仅未确认' },
              { value: 'acked', label: '仅已确认' },
              { value: 'all', label: '全部' }
            ]}
            style={{ minWidth: 160 }}
          />
          <Button type="primary" onClick={() => void ack_batch()} loading={action_loading} disabled={selected_ids.length === 0 || !can_ack_alerts}>
            批量确认
          </Button>
        </Space>
      </section>

      {error ? <Alert type="error" message="告警管理异常" description={error} showIcon /> : null}
      {!can_ack_alerts ? <Alert type="info" message="当前角色为只读模式" description="学生当前只能查看告警，不能执行确认操作。" showIcon /> : null}

      <section className="metric_grid">
        <div className="panel_surface metric_card"><Statistic title="当前结果数" value={summary.total} /></div>
        <div className="panel_surface metric_card"><Statistic title="未确认" value={summary.open} /></div>
        <div className="panel_surface metric_card"><Statistic title="严重告警" value={summary.critical} /></div>
        <div className="panel_surface metric_card"><Statistic title="已选择" value={summary.selected} suffix={device_id ? `/${device_id}` : ''} /></div>
      </section>

      <div className="panel_surface">
        <Table
          rowKey="id"
          loading={loading}
          dataSource={alerts}
          columns={columns}
          rowSelection={{
            selectedRowKeys: selected_ids,
            onChange: (keys) => set_selected_ids(keys as number[]),
            getCheckboxProps: (record) => ({ disabled: record.is_ack || !can_ack_alerts })
          }}
          pagination={{ pageSize: 10 }}
        />
      </div>
    </section>
  );
}
