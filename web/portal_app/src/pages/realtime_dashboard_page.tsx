import { useEffect, useMemo, useState } from 'react';

import { Alert, List, Select, Space, Spin, Statistic, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

import {
  fetch_business_alerts,
  fetch_devices,
  fetch_env_telemetry,
  fetch_equipment_telemetry,
  fetch_wristband_bindings
} from '../api/backend_client';
import { TimeSeriesChart, type TimeSeriesDefinition } from '../components/time_series_chart';
import { use_business_realtime_store } from '../store/business_realtime_store';
import type { BindingEventRecord, BusinessAlertRecord, DeviceSummary, TelemetryRecord } from '../types/backend';
import { format_time } from '../utils/time';

const focus_metric_candidates: Record<string, { key: string; name: string; color: string }[]> = {
  equipment: [
    { key: 'power_w', name: '功率', color: '#125b56' },
    { key: 'rep_count', name: '次数', color: '#d97706' }
  ],
  env: [
    { key: 'temperature_c', name: '温度', color: '#c2410c' },
    { key: 'co2_ppm', name: 'CO₂', color: '#125b56' },
    { key: 'humidity', name: '湿度', color: '#2563eb' }
  ],
  wristband: [
    { key: 'heart_rate', name: '心率', color: '#c2410c' },
    { key: 'step_count', name: '步数', color: '#125b56' }
  ]
};

function to_number(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function build_series(device_type: string, rows: Array<Record<string, unknown>>): TimeSeriesDefinition[] {
  return (focus_metric_candidates[device_type] ?? [])
    .map((metric) => ({
      name: metric.name,
      color: metric.color,
      points: rows
        .map((row) => {
          const raw = row[metric.key];
          const value = to_number(raw);
          const label = typeof row.ts === 'string' ? dayjs(row.ts).format('HH:mm:ss') : dayjs.unix(Number(row.ts ?? 0)).format('HH:mm:ss');
          if (value === null) {
            return null;
          }
          return { label, value };
        })
        .filter((item): item is { label: string; value: number } => item !== null)
    }))
    .filter((item) => item.points.length > 0);
}

export function RealtimeDashboardPage() {
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [alerts, set_alerts] = useState<BusinessAlertRecord[]>([]);
  const [focus_device_id, set_focus_device_id] = useState<string | null>(null);
  const [focus_history, set_focus_history] = useState<TelemetryRecord[]>([]);
  const [latest_bindings, set_latest_bindings] = useState<BindingEventRecord[]>([]);

  const ws_state = use_business_realtime_store((state) => state.ws_state);
  const telemetry_by_device = use_business_realtime_store((state) => state.telemetry_by_device);
  const device_status = use_business_realtime_store((state) => state.device_status);
  const recent_alerts = use_business_realtime_store((state) => state.recent_alerts);
  const connect = use_business_realtime_store((state) => state.connect);

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      set_loading(true);
      set_error(null);
      try {
        const [device_items, alert_items] = await Promise.all([fetch_devices(), fetch_business_alerts({ is_ack: false })]);
        if (!mounted) {
          return;
        }
        set_devices(device_items);
        set_alerts(alert_items);
        set_focus_device_id((current) => current ?? device_items[0]?.device_id ?? null);
      } catch (load_error) {
        if (!mounted) {
          return;
        }
        set_error(load_error instanceof Error ? load_error.message : '仪表盘加载失败');
      } finally {
        if (mounted) {
          set_loading(false);
        }
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    async function load_focus_data() {
      if (!focus_device_id) {
        return;
      }
      const device = devices.find((item) => item.device_id === focus_device_id);
      if (!device) {
        return;
      }

      try {
        if (device.device_type === 'equipment') {
          const [telemetry, bindings] = await Promise.all([
            fetch_equipment_telemetry(focus_device_id, { limit: 120 }),
            fetch_devices({ type: 'wristband' }).then((items) =>
              items
                .filter((item) => item.last_payload.current_equipment_id === focus_device_id)
                .map((item, index) => ({
                  id: index + 1,
                  wristband_id: item.device_id,
                  equipment_id: focus_device_id,
                  gym_id: item.gym_id,
                  action: 'bind',
                  reason: 'device_snapshot',
                  ts: new Date().toISOString(),
                  duration_s: null
                }))
            )
          ]);
          if (mounted) {
            set_focus_history(telemetry);
            set_latest_bindings(bindings);
          }
          return;
        }

        if (device.device_type === 'env') {
          const telemetry = await fetch_env_telemetry(focus_device_id, { limit: 120 });
          if (mounted) {
            set_focus_history(telemetry);
            set_latest_bindings([]);
          }
          return;
        }

        if (device.device_type === 'wristband') {
          const bindings = await fetch_wristband_bindings(focus_device_id, { limit: 20 });
          if (mounted) {
            set_focus_history([]);
            set_latest_bindings(bindings);
          }
          return;
        }

        if (mounted) {
          set_focus_history([]);
          set_latest_bindings([]);
        }
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : '焦点设备数据加载失败');
        }
      }
    }
    void load_focus_data();
    return () => {
      mounted = false;
    };
  }, [devices, focus_device_id]);

  const merged_devices = useMemo(
    () =>
      devices.map((device) => ({
        ...device,
        online: device_status[device.device_id]?.online ?? device.online,
        status: device_status[device.device_id]?.status ?? device.status
      })),
    [device_status, devices]
  );

  const focus_device = merged_devices.find((item) => item.device_id === focus_device_id) ?? null;
  const live_rows = focus_device_id ? telemetry_by_device[focus_device_id] ?? [] : [];
  const history_rows = focus_history.map((item) => ({ ts: item.ts, ...item.payload }));
  const chart_rows = live_rows.length > 0 ? live_rows : history_rows;
  const chart_series = focus_device ? build_series(String(focus_device.device_type), chart_rows) : [];
  const displayed_alerts = recent_alerts.length > 0 ? recent_alerts : alerts;

  const device_columns: ColumnsType<DeviceSummary> = [
    { title: '设备', dataIndex: 'device_id', key: 'device_id' },
    {
      title: '类型',
      dataIndex: 'device_type',
      key: 'device_type',
      render: (value: string) => <Tag>{value}</Tag>
    },
    {
      title: '状态',
      dataIndex: 'online',
      key: 'online',
      render: (value: boolean, record) => <Tag color={value ? 'green' : 'red'}>{record.status}</Tag>
    },
    {
      title: '最后时间',
      dataIndex: 'last_seen_ts',
      key: 'last_seen_ts',
      render: (value: number | null) => (value ? dayjs.unix(value).format('YYYY-MM-DD HH:mm:ss') : '--')
    }
  ];

  const totals = {
    all: merged_devices.length,
    online: merged_devices.filter((item) => item.online).length,
    alerts: displayed_alerts.filter((item) => !item.is_ack).length,
    bindings: latest_bindings.length
  };

  return (
    <section className="page_shell">
      <section className="hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 实时仪表盘</div>
          <h1>训练现场与基础状态同屏汇聚</h1>
          <p>业务数据从后台 REST 和 WebSocket 接入。当前页面聚焦实时设备概览、最近告警、焦点设备曲线和绑定关系。</p>
        </div>
        <div className="hero_actions">
          <div className="ws_indicator">业务 WS: {ws_state}</div>
          <div className="panel_meta_text">设备快照默认按后台当前状态加载，实时曲线保留最近 200 个点。</div>
        </div>
      </section>

      {error ? <Alert type="error" message="仪表盘异常" description={error} showIcon /> : null}

      <section className="metric_grid">
        <div className="panel_surface metric_card"><Statistic title="设备总数" value={totals.all} /></div>
        <div className="panel_surface metric_card"><Statistic title="在线设备" value={totals.online} /></div>
        <div className="panel_surface metric_card"><Statistic title="未确认告警" value={totals.alerts} /></div>
        <div className="panel_surface metric_card"><Statistic title="焦点绑定记录" value={totals.bindings} /></div>
      </section>

      <section className="dashboard_grid">
        <div className="left_column">
          <div className="panel_surface">
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">焦点设备</div>
                <h3>实时曲线</h3>
              </div>
              <Select
                value={focus_device_id ?? undefined}
                placeholder="选择设备"
                onChange={set_focus_device_id}
                options={merged_devices.map((item) => ({
                  value: item.device_id,
                  label: `${item.device_id} · ${item.device_type}`
                }))}
                style={{ minWidth: 260 }}
              />
            </div>
            {focus_device ? (
              <TimeSeriesChart
                title={`${focus_device.device_id} 实时数据`}
                subtitle={`类型：${focus_device.device_type}`}
                series={chart_series}
                empty_message="当前设备尚未收到实时数据"
              />
            ) : (
              <div className="loading_surface"><Spin /></div>
            )}
          </div>

          <div className="panel_surface">
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">绑定视图</div>
                <h3>最近关联关系</h3>
              </div>
            </div>
            <List
              locale={{ emptyText: '当前焦点设备没有可展示的绑定记录' }}
              dataSource={latest_bindings}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={`${item.wristband_id} ↔ ${item.equipment_id}`}
                    description={`${item.action} · ${item.reason ?? '无原因'} · ${format_time(item.ts)}`}
                  />
                </List.Item>
              )}
            />
          </div>
        </div>

        <div className="right_column">
          <div className="panel_surface">
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">设备快照</div>
                <h3>当前在线态势</h3>
              </div>
            </div>
            <Table rowKey="device_id" dataSource={merged_devices} columns={device_columns} pagination={{ pageSize: 6 }} />
          </div>

          <div className="panel_surface">
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">实时告警</div>
                <h3>最新业务告警</h3>
              </div>
            </div>
            <List
              locale={{ emptyText: '当前没有未确认告警' }}
              dataSource={displayed_alerts.slice(0, 8)}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Space><Tag color={item.level === 'critical' ? 'red' : item.level === 'warning' ? 'orange' : 'blue'}>{item.level}</Tag>{item.message}</Space>}
                    description={`${item.device_id} · ${item.code} · ${format_time(item.triggered_at)}`}
                  />
                </List.Item>
              )}
            />
          </div>
        </div>
      </section>

      {loading ? <div className="panel_surface loading_surface"><Spin size="large" /></div> : null}
    </section>
  );
}
