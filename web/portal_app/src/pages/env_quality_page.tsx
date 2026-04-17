import { useEffect, useMemo, useState } from 'react';

import { Alert, Button, Collapse, Form, InputNumber, List, Select, Space, Spin, Statistic, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';

import { fetch_devices, fetch_env_aggregate, fetch_env_telemetry, publish_device_config } from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { TimeSeriesChart } from '../components/time_series_chart';
import { use_auth_store } from '../store/auth_store';
import { use_business_realtime_store } from '../store/business_realtime_store';
import type { DeviceConfigPublishResult, DeviceSummary, EnvTelemetryAggregateRecord, TelemetryRecord } from '../types/backend';

const range_options = [
  { label: '1 分钟', value: '1m', interval: '5s' },
  { label: '5 分钟', value: '5m', interval: '15s' },
  { label: '15 分钟', value: '15m', interval: '1m' },
  { label: '1 小时', value: '1h', interval: '10m' },
  { label: '6 小时', value: '6h', interval: '30m' },
  { label: '24 小时', value: '24h', interval: '1h' },
  { label: '7 天', value: '7d', interval: '6h' }
] as const;

const empty_realtime_points: Array<Record<string, unknown>> = [];

function to_number(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function format_last_seen(value: number | null): string {
  return value ? new Date(value * 1000).toLocaleString() : '--';
}

function build_start(range: string): string {
  const amount = Number(range.slice(0, -1));
  const unit = range.slice(-1);
  const now = new Date();
  const start = new Date(now);
  if (unit === 'm') {
    start.setMinutes(now.getMinutes() - amount);
  } else if (unit === 'h') {
    start.setHours(now.getHours() - amount);
  } else if (unit === 'd') {
    start.setDate(now.getDate() - amount);
  }
  return start.toISOString();
}

function build_start_ms(range: (typeof range_options)[number]['value']): number {
  return Date.parse(build_start(range));
}

function to_timestamp_ms(value: unknown): number | null {
  if (typeof value === 'number') {
    return value > 1_000_000_000_000 ? value : value * 1000;
  }
  if (typeof value === 'string') {
    const numeric = Number(value);
    if (!Number.isNaN(numeric) && value.trim() !== '') {
      return numeric > 1_000_000_000_000 ? numeric : numeric * 1000;
    }
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
}

export function EnvQualityPage() {
  const navigate = useNavigate();
  const { device_id: route_device_id } = useParams<{ device_id?: string }>();
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [selected_range, set_selected_range] = useState<(typeof range_options)[number]['value']>('24h');
  const [telemetry, set_telemetry] = useState<TelemetryRecord[]>([]);
  const [aggregate, set_aggregate] = useState<EnvTelemetryAggregateRecord[]>([]);
  const [command_result, set_command_result] = useState<DeviceConfigPublishResult | null>(null);
  const [command_loading, set_command_loading] = useState(false);
  const [form] = Form.useForm<{ telemetry_interval_s: number }>();

  const selected_device_id = route_device_id ?? null;
  const is_overview = route_device_id === undefined;
  const realtime_points = use_business_realtime_store((state) =>
    selected_device_id ? state.telemetry_by_device[selected_device_id] ?? empty_realtime_points : empty_realtime_points
  );
  const connect = use_business_realtime_store((state) => state.connect);
  const disconnect = use_business_realtime_store((state) => state.disconnect);
  const session = use_auth_store((state) => state.session);
  const can_publish_config = session?.user.role === 'admin';
  const is_read_only = Boolean(session && !can_publish_config);

  useEffect(() => {
    if (!session) {
      disconnect();
      return;
    }
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect, session]);

  useEffect(() => {
    if (!session) {
      set_loading(false);
      set_error(null);
      set_devices([]);
      return;
    }

    let mounted = true;
    async function load_devices() {
      set_loading(true);
      try {
        const env_devices = await fetch_devices({ type: 'env' });
        if (!mounted) {
          return;
        }
        set_devices(env_devices);
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
  }, [session]);

  useEffect(() => {
    if (!session) {
      set_telemetry([]);
      set_aggregate([]);
      return;
    }

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
  }, [selected_device_id, selected_range, session]);

  const selected_device = devices.find((item) => item.device_id === selected_device_id) ?? null;
  const latest_payload = selected_device?.last_payload ?? {};
  const chart_window_start = build_start_ms(selected_range);
  const chart_window_end = Date.now();
  const chart_rows = (realtime_points.length > 0
    ? realtime_points
    : aggregate.map((item) => ({
        ts: item.bucket_start,
        temperature_c: item.metrics.temperature_c?.avg,
        humidity: item.metrics.humidity?.avg,
        co2_ppm: item.metrics.co2_ppm?.avg,
        pm2_5: item.metrics.pm2_5?.avg
      }))
  ).filter((row) => {
    const ts_ms = to_timestamp_ms(row.ts);
    return ts_ms === null ? false : ts_ms >= chart_window_start && ts_ms <= chart_window_end;
  });

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
          const ts_ms = to_timestamp_ms(row.ts);
          if (value === null || ts_ms === null) {
            return null;
          }
          return {
            ts_ms,
            value
          };
        })
        .filter((item): item is { ts_ms: number; value: number } => item !== null)
    }))
    .filter((item) => item.points.length > 0);
  const selected_range_label = range_options.find((item) => item.value === selected_range)?.label ?? selected_range;

  const threshold_flags = useMemo(() => {
    const entries = [
      { label: 'CO₂', value: to_number(latest_payload.co2_ppm), limit: 1000 },
      { label: 'PM2.5', value: to_number(latest_payload.pm2_5), limit: 35 },
      { label: '温度', value: to_number(latest_payload.temperature_c) ?? to_number(latest_payload.temperature), limit: 30 }
    ];
    return entries.filter((item) => item.value !== null && item.value >= item.limit);
  }, [latest_payload]);

  const overview_summary = {
    total: devices.length,
    online: devices.filter((item) => item.online).length,
    over_limit: devices.filter((device) => {
      const payload = device.last_payload ?? {};
      return (
        (to_number(payload.co2_ppm) ?? 0) >= 1000 ||
        (to_number(payload.pm2_5) ?? 0) >= 35 ||
        (to_number(payload.temperature_c) ?? to_number(payload.temperature) ?? 0) >= 30
      );
    }).length,
    avg_temperature:
      devices.length > 0
        ? devices
            .map((item) => to_number(item.last_payload.temperature_c) ?? to_number(item.last_payload.temperature))
            .filter((value): value is number => value !== null)
            .reduce((sum, value, _, list) => sum + value / list.length, 0)
        : 0
  };

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 环境总览"
        title="先看全部环境节点"
        description="统一查看环境节点清单并进入实例详情。"
      />
    );
  }

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
          <div className="eyebrow">{is_overview ? '06 网页端 / 环境总览' : '06 网页端 / 环境总览 / 实例详情'}</div>
          <h1>{is_overview ? '先看全部环境节点' : '查看单个环境节点'}</h1>
          <p>{is_overview ? '统一查看环境节点清单并进入实例详情。' : '统一查看单个节点状态、趋势与配置。'}</p>
        </div>
        {!is_overview ? (
          <div className="hero_actions">
            <Button onClick={() => navigate('/env-quality')}>返回环境总览</Button>
          </div>
        ) : null}
      </section>

      {error ? <Alert type="error" message="环境页面异常" description={error} showIcon /> : null}

      {loading ? (
        <div className="panel_surface loading_surface"><Spin size="large" /></div>
      ) : is_overview ? (
        <>
          <section className="metric_grid">
            <div className="panel_surface metric_card"><Statistic title="节点总数" value={overview_summary.total} /></div>
            <div className="panel_surface metric_card"><Statistic title="在线节点" value={overview_summary.online} /></div>
            <div className="panel_surface metric_card"><Statistic title="超标节点" value={overview_summary.over_limit} /></div>
            <div className="panel_surface metric_card"><Statistic title="平均温度(°C)" value={overview_summary.avg_temperature} precision={1} /></div>
          </section>

          <div className="panel_surface">
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">环境总览</div>
                <h3>全部环境节点</h3>
              </div>
              <div className="panel_meta_text">点击卡片进入实例详情</div>
            </div>
            <section className="overview_card_grid">
              {devices.map((device) => {
                const payload = device.last_payload ?? {};
                return (
                  <button
                    key={device.device_id}
                    type="button"
                    className="device_overview_card"
                    onClick={() => navigate(`/env-quality/${device.device_id}`)}
                  >
                    <div className="device_overview_header">
                      <div>
                        <strong>{device.device_id}</strong>
                        <div className="device_overview_subtitle">{device.gym_id}</div>
                      </div>
                      <Tag color={device.online ? 'green' : 'red'}>{device.status}</Tag>
                    </div>
                    <div className="device_overview_metrics">
                      <span>温度 {to_number(payload.temperature_c) ?? to_number(payload.temperature) ?? 0} °C</span>
                      <span>湿度 {to_number(payload.humidity) ?? 0} %</span>
                      <span>CO₂ {to_number(payload.co2_ppm) ?? 0} ppm</span>
                    </div>
                    <div className="device_overview_footer">最后时间：{format_last_seen(device.last_seen_ts)}</div>
                  </button>
                );
              })}
            </section>
          </div>
        </>
      ) : selected_device ? (
        <>
          <section className="metric_grid">
            <div className="panel_surface metric_card"><Statistic title="温度(°C)" value={to_number(latest_payload.temperature_c) ?? to_number(latest_payload.temperature) ?? 0} precision={1} /></div>
            <div className="panel_surface metric_card"><Statistic title="湿度(%)" value={to_number(latest_payload.humidity) ?? 0} precision={1} /></div>
            <div className="panel_surface metric_card"><Statistic title="CO₂(ppm)" value={to_number(latest_payload.co2_ppm) ?? 0} /></div>
            <div className="panel_surface metric_card"><Statistic title="PM2.5" value={to_number(latest_payload.pm2_5) ?? 0} /></div>
          </section>

          <section className="dashboard_grid">
            <div className="left_column">
              <TimeSeriesChart
                title={`${selected_device.device_id} 趋势图`}
                subtitle={`时间范围：${selected_range_label}`}
                series={chart_series}
                empty_message="当前时间范围内没有环境数据"
                window_start_ms={chart_window_start}
                window_end_ms={chart_window_end}
                header_extra={
                  <Space wrap>
                    <Select
                      value={selected_device_id ?? undefined}
                      placeholder="选择环境节点"
                      onChange={(value) => navigate(`/env-quality/${value}`)}
                      options={devices.map((item) => ({ value: item.device_id, label: item.device_id }))}
                      style={{ minWidth: 220 }}
                    />
                    <Select
                      value={selected_range}
                      onChange={set_selected_range}
                      options={range_options.map((item) => ({ value: item.value, label: item.label }))}
                      style={{ minWidth: 140 }}
                    />
                  </Space>
                }
              />
            </div>

            <div className="right_column">
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

              {can_publish_config ? (
                <div className="panel_surface">
                  <div className="panel_header compact_panel_header">
                    <div>
                      <div className="eyebrow">动态配置</div>
                      <h3>修改上报周期</h3>
                    </div>
                  </div>
                  <Collapse
                    className="inline_collapse"
                    items={[
                      {
                        key: 'env-config',
                        label: '动态配置',
                        children: (
                          <>
                            <div className="explanation_note">
                              <strong className="explanation_title"><code>telemetry_interval_s</code> 的含义</strong>
                              <div>
                                这里下发的是环境节点的上报周期字段 <code>telemetry_interval_s</code>。设备侧采样策略不在前端修改范围内，
                                当前仅调整遥测发送频率。
                              </div>
                            </div>
                            <Form form={form} layout="vertical" onFinish={(values) => void submit_command(values)}>
                              <Form.Item
                                name="telemetry_interval_s"
                                label="上报周期（秒）"
                                rules={[{ required: true, message: '请输入上报周期' }]}
                              >
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
                          </>
                        )
                      }
                    ]}
                  />
                </div>
              ) : null}

              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">环境快照</div>
                    <h3>最新上报字段</h3>
                  </div>
                  <Space wrap>
                    {is_read_only ? <Tag color="default">只读</Tag> : null}
                    <Tag color={selected_device.online ? 'green' : 'red'}>{selected_device.status}</Tag>
                  </Space>
                </div>
                <Collapse
                  className="inline_collapse"
                  items={[
                    {
                      key: 'env-payload',
                      label: '查看最新上报字段（JSON）',
                      children: <pre className="stats_panel collapsed_stats_panel">{JSON.stringify(latest_payload, null, 2)}</pre>
                    }
                  ]}
                />
              </div>
            </div>
          </section>
        </>
      ) : devices.length === 0 ? (
        <div className="panel_surface empty_state">当前没有环境节点</div>
      ) : (
        <div className="panel_surface empty_state">
          <Space direction="vertical" size="middle" align="center">
            <div>未找到对应环境节点</div>
            <Button onClick={() => navigate('/env-quality')}>返回环境总览</Button>
          </Space>
        </div>
      )}
    </section>
  );
}
