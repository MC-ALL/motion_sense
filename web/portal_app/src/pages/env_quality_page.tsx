import { useEffect, useMemo, useState } from 'react';

import { Alert, Button, Form, InputNumber, List, Select, Space, Spin, Statistic, Tag } from 'antd';

import { fetch_devices, fetch_env_aggregate, fetch_env_telemetry, publish_device_config } from '../api/backend_client';
import { TimeSeriesChart } from '../components/time_series_chart';
import { use_business_realtime_store } from '../store/business_realtime_store';
import type { DeviceConfigPublishResult, DeviceSummary, EnvTelemetryAggregateRecord, TelemetryRecord } from '../types/backend';

const range_options = [
  { label: '1 小时', value: '1h', interval: '10m' },
  { label: '6 小时', value: '6h', interval: '30m' },
  { label: '24 小时', value: '24h', interval: '1h' },
  { label: '7 天', value: '7d', interval: '6h' }
] as const;

const empty_realtime_points: Array<Record<string, unknown>> = [];

function to_number(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function build_start(range: string): string {
  const amount = Number(range.slice(0, -1));
  const unit = range.slice(-1);
  const now = new Date();
  const start = new Date(now);
  if (unit === 'h') {
    start.setHours(now.getHours() - amount);
  } else if (unit === 'd') {
    start.setDate(now.getDate() - amount);
  }
  return start.toISOString();
}

export function EnvQualityPage() {
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [selected_device_id, set_selected_device_id] = useState<string | null>(null);
  const [selected_range, set_selected_range] = useState<(typeof range_options)[number]['value']>('24h');
  const [telemetry, set_telemetry] = useState<TelemetryRecord[]>([]);
  const [aggregate, set_aggregate] = useState<EnvTelemetryAggregateRecord[]>([]);
  const [command_result, set_command_result] = useState<DeviceConfigPublishResult | null>(null);
  const [command_loading, set_command_loading] = useState(false);
  const [form] = Form.useForm<{ telemetry_interval_s: number }>();

  const realtime_points = use_business_realtime_store((state) =>
    selected_device_id ? state.telemetry_by_device[selected_device_id] ?? empty_realtime_points : empty_realtime_points
  );
  const connect = use_business_realtime_store((state) => state.connect);

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    let mounted = true;
    async function load_devices() {
      set_loading(true);
      try {
        const env_devices = await fetch_devices({ type: 'env' });
        if (!mounted) {
          return;
        }
        set_devices(env_devices);
        set_selected_device_id((current) => current ?? env_devices[0]?.device_id ?? null);
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : '环境节点加载失败');
        }
      } finally {
        if (mounted) {
          set_loading(false);
        }
      }
    }
    void load_devices();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    async function load_data() {
      if (!selected_device_id) {
        return;
      }
      const range_option = range_options.find((item) => item.value === selected_range) ?? range_options[2];
      const start = build_start(selected_range);
      const end = new Date().toISOString();

      try {
        const [telemetry_items, aggregate_items] = await Promise.all([
          fetch_env_telemetry(selected_device_id, { start, end, limit: 200 }),
          fetch_env_aggregate(selected_device_id, { start, end, interval: range_option.interval, limit: 200 })
        ]);
        if (!mounted) {
          return;
        }
        set_telemetry(telemetry_items);
        set_aggregate(aggregate_items.reverse());
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : '环境数据加载失败');
        }
      }
    }
    void load_data();
    return () => {
      mounted = false;
    };
  }, [selected_device_id, selected_range]);

  const selected_device = devices.find((item) => item.device_id === selected_device_id) ?? null;
  const latest_payload = selected_device?.last_payload ?? {};
  const chart_rows = realtime_points.length > 0 ? realtime_points : aggregate.map((item) => ({
    ts: item.bucket_start,
    temperature_c: item.metrics.temperature_c?.avg,
    humidity: item.metrics.humidity?.avg,
    co2_ppm: item.metrics.co2_ppm?.avg,
    pm2_5: item.metrics.pm2_5?.avg
  }));

  const chart_series = [
    { name: '温度', color: '#c2410c', key: 'temperature_c' },
    { name: '湿度', color: '#2563eb', key: 'humidity' },
    { name: 'CO₂', color: '#125b56', key: 'co2_ppm' }
  ]
    .map((metric) => ({
      name: metric.name,
      color: metric.color,
      points: chart_rows
        .map((row) => {
          const value = to_number(row[metric.key as keyof typeof row]);
          if (value === null) {
            return null;
          }
          return {
            label: new Date(String(row.ts)).toLocaleString(),
            value
          };
        })
        .filter((item): item is { label: string; value: number } => item !== null)
    }))
    .filter((item) => item.points.length > 0);

  const threshold_flags = useMemo(() => {
    const entries = [
      { label: 'CO₂', value: to_number(latest_payload.co2_ppm), limit: 1000 },
      { label: 'PM2.5', value: to_number(latest_payload.pm2_5), limit: 35 },
      { label: '温度', value: to_number(latest_payload.temperature_c) ?? to_number(latest_payload.temperature), limit: 30 }
    ];
    return entries.filter((item) => item.value !== null && item.value >= item.limit);
  }, [latest_payload]);

  async function submit_command(values: { telemetry_interval_s: number }) {
    if (!selected_device) {
      return;
    }

    set_command_loading(true);
    set_error(null);
    try {
      const result = await publish_device_config(selected_device.device_id, {
        gym_id: selected_device.gym_id,
        device_type: 'env',
        config: {
          ts: Math.floor(Date.now() / 1000),
          telemetry_interval_s: values.telemetry_interval_s
        }
      });
      set_command_result(result);
    } catch (submit_error) {
      set_error(submit_error instanceof Error ? submit_error.message : '环境配置下发失败');
    } finally {
      set_command_loading(false);
    }
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 环境质量</div>
          <h1>区域环境节点实时卡片与趋势图</h1>
          <p>环境页面展示实时快照、聚合趋势和超标提示，同时可通过后台接口下发新的上报周期。</p>
        </div>
        <Space wrap>
          <Select
            value={selected_device_id ?? undefined}
            placeholder="选择环境节点"
            onChange={set_selected_device_id}
            options={devices.map((item) => ({ value: item.device_id, label: item.device_id }))}
            style={{ minWidth: 220 }}
          />
          <Select value={selected_range} onChange={set_selected_range} options={range_options.map((item) => ({ value: item.value, label: item.label }))} />
        </Space>
      </section>

      {error ? <Alert type="error" message="环境页面异常" description={error} showIcon /> : null}

      {selected_device ? (
        <>
          <section className="metric_grid">
            <div className="panel_surface metric_card"><Statistic title="温度(°C)" value={to_number(latest_payload.temperature_c) ?? to_number(latest_payload.temperature) ?? 0} precision={1} /></div>
            <div className="panel_surface metric_card"><Statistic title="湿度(%)" value={to_number(latest_payload.humidity) ?? 0} precision={1} /></div>
            <div className="panel_surface metric_card"><Statistic title="CO₂(ppm)" value={to_number(latest_payload.co2_ppm) ?? 0} /></div>
            <div className="panel_surface metric_card"><Statistic title="PM2.5" value={to_number(latest_payload.pm2_5) ?? 0} /></div>
          </section>

          <section className="dashboard_grid">
            <div className="left_column">
              <TimeSeriesChart title={`${selected_device.device_id} 趋势图`} subtitle={`时间范围：${selected_range}`} series={chart_series} empty_message="当前时间范围内没有环境数据" />

              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">超标提示</div>
                    <h3>当前阈值命中</h3>
                  </div>
                </div>
                <List
                  locale={{ emptyText: '当前快照未发现超标项' }}
                  dataSource={threshold_flags}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta title={`${item.label} 超标`} description={`当前值 ${item.value}，阈值 ${item.limit}`} />
                    </List.Item>
                  )}
                />
              </div>
            </div>

            <div className="right_column">
              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">动态配置</div>
                    <h3>修改上报周期</h3>
                  </div>
                </div>
                <Form form={form} layout="vertical" onFinish={(values) => void submit_command(values)}>
                  <Form.Item name="telemetry_interval_s" label="上报周期（秒）" rules={[{ required: true, message: '请输入上报周期' }]}>
                    <InputNumber min={1} max={3600} style={{ width: '100%' }} />
                  </Form.Item>
                  <Button htmlType="submit" type="primary" loading={command_loading} block>
                    下发到网关
                  </Button>
                </Form>
                {command_result ? (
                  <Alert
                    className="inline_alert"
                    type={command_result.status === 'pending' ? 'info' : 'success'}
                    message={`命令状态：${command_result.status}`}
                    description={`command_id=${command_result.command_id}`}
                    showIcon
                  />
                ) : null}
              </div>

              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">环境快照</div>
                    <h3>最新上报字段</h3>
                  </div>
                  <Tag color={selected_device.online ? 'green' : 'red'}>{selected_device.status}</Tag>
                </div>
                <pre className="stats_panel">{JSON.stringify(latest_payload, null, 2)}</pre>
              </div>
            </div>
          </section>
        </>
      ) : loading ? (
        <div className="panel_surface loading_surface"><Spin size="large" /></div>
      ) : (
        <div className="panel_surface empty_state">当前没有环境节点</div>
      )}
    </section>
  );
}
