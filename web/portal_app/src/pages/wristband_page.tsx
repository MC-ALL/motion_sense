import { useEffect, useState } from 'react';

import { Alert, Button, Collapse, Form, InputNumber, List, Select, Space, Spin, Statistic, Switch, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';

import {
  fetch_devices,
  fetch_wristband_bindings,
  fetch_wristband_telemetry,
  publish_device_config
} from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { TimeSeriesChart } from '../components/time_series_chart';
import { use_auth_store } from '../store/auth_store';
import { use_business_realtime_store } from '../store/business_realtime_store';
import type { BindingEventRecord, DeviceConfigPublishResult, DeviceSummary, TelemetryRecord } from '../types/backend';
import { format_time } from '../utils/time';

const empty_realtime_points: Array<Record<string, unknown>> = [];
const chart_window_options = [
  { label: '1 分钟', value: '1m' },
  { label: '5 分钟', value: '5m' },
  { label: '15 分钟', value: '15m' },
  { label: '30 分钟', value: '30m' },
  { label: '2 小时', value: '2h' },
  { label: '6 小时', value: '6h' },
  { label: '24 小时', value: '24h' }
] as const;

type ChartWindow = (typeof chart_window_options)[number]['value'];

type WristbandConfigForm = {
  hr_alert_threshold_high: number;
  hr_alert_threshold_low: number;
  notify_interval_ms: number;
  fall_detect_enabled: boolean;
};

type ChartRow = Record<string, unknown> & {
  ts?: string | number;
};

function to_number(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function format_last_seen(value: number | null): string {
  return value ? new Date(value * 1000).toLocaleString() : '--';
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

function build_window_start(window_value: ChartWindow): number {
  const now = Date.now();
  if (window_value === '1m') {
    return now - 60 * 1000;
  }
  if (window_value === '5m') {
    return now - 5 * 60 * 1000;
  }
  if (window_value === '15m') {
    return now - 15 * 60 * 1000;
  }
  if (window_value === '30m') {
    return now - 30 * 60 * 1000;
  }
  if (window_value === '2h') {
    return now - 2 * 60 * 60 * 1000;
  }
  if (window_value === '6h') {
    return now - 6 * 60 * 60 * 1000;
  }
  return now - 24 * 60 * 60 * 1000;
}

function normalize_equipment_binding_id(value: unknown): string {
  if (typeof value === 'string') {
    if (value === '' || value === '255' || value.toLowerCase() === 'none') {
      return '未绑定';
    }
    return value;
  }
  if (typeof value === 'number') {
    if (value === 255) {
      return '未绑定';
    }
    return `eq-${String(value).padStart(3, '0')}`;
  }
  return '未绑定';
}

export function WristbandPage() {
  const navigate = useNavigate();
  const { device_id: route_device_id } = useParams<{ device_id?: string }>();
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [selected_window, set_selected_window] = useState<ChartWindow>('15m');
  const [telemetry, set_telemetry] = useState<TelemetryRecord[]>([]);
  const [bindings, set_bindings] = useState<BindingEventRecord[]>([]);
  const [command_result, set_command_result] = useState<DeviceConfigPublishResult | null>(null);
  const [command_loading, set_command_loading] = useState(false);
  const [form] = Form.useForm<WristbandConfigForm>();

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
    async function load() {
      set_loading(true);
      set_error(null);
      try {
        const wristband_devices = await fetch_devices({ type: 'wristband' });
        if (!mounted) {
          return;
        }
        set_devices(wristband_devices);
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : '手环列表加载失败');
        }
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
  }, [session]);

  useEffect(() => {
    if (!session) {
      set_telemetry([]);
      set_bindings([]);
      return;
    }

    let mounted = true;
    async function load_wristband_data() {
      if (!selected_device_id) {
        return;
      }
      try {
        const start = new Date(build_window_start(selected_window)).toISOString();
        const end = new Date().toISOString();
        const [telemetry_items, binding_items] = await Promise.all([
          fetch_wristband_telemetry(selected_device_id, { start, end, limit: 200 }),
          fetch_wristband_bindings(selected_device_id, { limit: 20 })
        ]);
        if (mounted) {
          set_telemetry(telemetry_items);
          set_bindings(binding_items);
        }
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : '手环数据加载失败');
        }
      }
    }
    void load_wristband_data();
    return () => {
      mounted = false;
    };
  }, [selected_device_id, selected_window, session]);

  const selected_device = devices.find((item) => item.device_id === selected_device_id) ?? null;
  const latest_payload = selected_device?.last_payload ?? {};
  const chart_window_start = build_window_start(selected_window);
  const chart_window_end = Date.now();
  const chart_rows: ChartRow[] =
    realtime_points.length > 0
      ? realtime_points
          .filter((item) => {
            const ts_ms = to_timestamp_ms(item.ts);
            return ts_ms === null ? false : ts_ms >= chart_window_start && ts_ms <= chart_window_end;
          })
          .map((item) => item as ChartRow)
      : telemetry
          .map((item) => ({ ts: item.ts, ...item.payload }))
          .filter((item) => {
            const ts_ms = to_timestamp_ms(item.ts);
            return ts_ms === null ? false : ts_ms >= chart_window_start && ts_ms <= chart_window_end;
          });

  const chart_series = [
    {
      name: '心率',
      color: '#c2410c',
      points: chart_rows
        .map((row) => {
          const value = to_number(row['heart_rate']);
          const ts_ms = to_timestamp_ms(row.ts);
          if (value === null || ts_ms === null) {
            return null;
          }
          return { ts_ms, value };
        })
        .filter((item): item is { ts_ms: number; value: number } => item !== null)
    },
    {
      name: '步数',
      color: '#125b56',
      points: chart_rows
        .map((row) => {
          const value = to_number(row['step_count']);
          const ts_ms = to_timestamp_ms(row.ts);
          if (value === null || ts_ms === null) {
            return null;
          }
          return { ts_ms, value };
        })
        .filter((item): item is { ts_ms: number; value: number } => item !== null)
    },
    {
      name: '电量',
      color: '#2563eb',
      points: chart_rows
        .map((row) => {
          const value = to_number(row['battery_pct']);
          const ts_ms = to_timestamp_ms(row.ts);
          if (value === null || ts_ms === null) {
            return null;
          }
          return { ts_ms, value };
        })
        .filter((item): item is { ts_ms: number; value: number } => item !== null)
    }
  ].filter((item) => item.points.length > 0);

  const selected_window_label =
    chart_window_options.find((item) => item.value === selected_window)?.label ?? selected_window;

  const overview_summary = {
    total: devices.length,
    online: devices.filter((item) => item.online).length,
    active: devices.filter((item) => (to_number(item.last_payload.heart_rate) ?? 0) > 0).length,
    bound: devices.filter((item) => normalize_equipment_binding_id(item.last_payload.current_equipment_id) !== '未绑定').length
  };

  useEffect(() => {
    form.setFieldsValue({
      hr_alert_threshold_high: 180,
      hr_alert_threshold_low: 40,
      notify_interval_ms: 100,
      fall_detect_enabled: true
    });
  }, [form, selected_device_id]);

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 手环总览"
        title="先看全部手环"
        description="统一查看手环清单并进入实例详情。"
      />
    );
  }

  async function submit_command(values: WristbandConfigForm) {
    if (!selected_device) {
      return;
    }

    set_command_loading(true);
    set_error(null);
    try {
      const result = await publish_device_config(selected_device.device_id, {
        gym_id: selected_device.gym_id,
        device_type: 'wristband',
        config: {
          ts: Math.floor(Date.now() / 1000),
          hr_alert_threshold_high: values.hr_alert_threshold_high,
          hr_alert_threshold_low: values.hr_alert_threshold_low,
          notify_interval_ms: values.notify_interval_ms,
          fall_detect_enabled: values.fall_detect_enabled
        }
      });
      set_command_result(result);
    } catch (submit_error) {
      set_error(submit_error instanceof Error ? submit_error.message : '手环配置下发失败');
    } finally {
      set_command_loading(false);
    }
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">{is_overview ? '06 网页端 / 手环总览' : '06 网页端 / 手环总览 / 实例详情'}</div>
          <h1>{is_overview ? '先看全部手环' : '查看单只手环'}</h1>
          <p>{is_overview ? '统一查看手环清单并进入实例详情。' : '统一查看单只手环状态、曲线与配置。'}</p>
        </div>
        {!is_overview ? (
          <div className="hero_actions">
            <Button onClick={() => navigate('/wristband')}>返回手环总览</Button>
          </div>
        ) : null}
      </section>

      {error ? <Alert type="error" message="手环管理异常" description={error} showIcon /> : null}

      {loading ? (
        <div className="panel_surface loading_surface"><Spin size="large" /></div>
      ) : is_overview ? (
        <>
          <section className="metric_grid">
            <div className="panel_surface metric_card"><Statistic title="手环总数" value={overview_summary.total} /></div>
            <div className="panel_surface metric_card"><Statistic title="在线手环" value={overview_summary.online} /></div>
            <div className="panel_surface metric_card"><Statistic title="活跃手环" value={overview_summary.active} /></div>
            <div className="panel_surface metric_card"><Statistic title="已绑定手环" value={overview_summary.bound} /></div>
          </section>

          <div className="panel_surface">
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">手环总览</div>
                <h3>全部手环实例</h3>
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
                    onClick={() => navigate(`/wristband/${device.device_id}`)}
                  >
                    <div className="device_overview_header">
                      <div>
                        <strong>{device.device_id}</strong>
                        <div className="device_overview_subtitle">{device.gym_id}</div>
                      </div>
                      <Tag color={device.online ? 'green' : 'red'}>{device.status}</Tag>
                    </div>
                    <div className="device_overview_metrics">
                      <span>心率 {to_number(payload.heart_rate) ?? '--'}</span>
                      <span>步数 {to_number(payload.step_count) ?? '--'}</span>
                      <span>电量 {to_number(payload.battery_pct) ?? '--'} %</span>
                    </div>
                    <div className="device_overview_footer">
                      绑定器材：{normalize_equipment_binding_id(payload.current_equipment_id)} · 最后时间：{format_last_seen(device.last_seen_ts)}
                    </div>
                  </button>
                );
              })}
            </section>
          </div>
        </>
      ) : selected_device ? (
        <>
          <section className="metric_grid">
            <div className="panel_surface metric_card"><Statistic title="在线状态" value={selected_device.online ? '在线' : '离线'} /></div>
            <div className="panel_surface metric_card"><Statistic title="当前心率(bpm)" value={to_number(latest_payload.heart_rate) ?? '--'} /></div>
            <div className="panel_surface metric_card"><Statistic title="当前步数" value={to_number(latest_payload.step_count) ?? '--'} /></div>
            <div className="panel_surface metric_card"><Statistic title="电量(%)" value={to_number(latest_payload.battery_pct) ?? '--'} /></div>
          </section>

          <section className="dashboard_grid">
            <div className="left_column">
              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">绑定历史</div>
                    <h3>最近绑定事件</h3>
                  </div>
                </div>
                <Collapse
                  className="inline_collapse"
                  items={[
                    {
                      key: 'wristband-bindings',
                      label: '查看绑定历史',
                      children: (
                        <List
                          locale={{ emptyText: '当前没有可展示的绑定历史' }}
                          dataSource={bindings}
                          pagination={{ pageSize: 6, size: 'small' }}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                title={`${item.wristband_id} ↔ ${item.equipment_id}`}
                                description={`${item.action} · ${item.reason ?? '无原因'} · ${format_time(item.ts)}`}
                              />
                            </List.Item>
                          )}
                        />
                      )
                    }
                  ]}
                />
              </div>

              <TimeSeriesChart
                title={`${selected_device.device_id} 生命体征曲线`}
                subtitle={`观察窗口：${selected_window_label}`}
                series={chart_series}
                empty_message="当前手环还没有曲线数据"
                window_start_ms={chart_window_start}
                window_end_ms={chart_window_end}
                header_extra={
                  <Space wrap>
                    <Select
                      value={selected_device_id ?? undefined}
                      placeholder="选择手环"
                      onChange={(value) => navigate(`/wristband/${value}`)}
                      options={devices.map((item) => ({ value: item.device_id, label: item.device_id }))}
                      style={{ minWidth: 220 }}
                    />
                    <Select
                      value={selected_window}
                      onChange={(value) => set_selected_window(value as ChartWindow)}
                      options={chart_window_options.map((item) => ({ value: item.value, label: item.label }))}
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
                    <div className="eyebrow">绑定状态</div>
                    <h3>当前绑定与转发器材</h3>
                  </div>
                </div>
                <List
                  dataSource={[
                    {
                      label: '当前绑定器材',
                      value: normalize_equipment_binding_id(latest_payload.current_equipment_id)
                    },
                    {
                      label: '当前转发器材',
                      value: typeof latest_payload.relayed_by === 'string' ? latest_payload.relayed_by : '--'
                    }
                  ]}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta title={item.label} description={item.value} />
                    </List.Item>
                  )}
                />
              </div>

              {can_publish_config ? (
                <div className="panel_surface">
                  <div className="panel_header compact_panel_header">
                    <div>
                      <div className="eyebrow">配置下发</div>
                      <h3>心率阈值与 Notify 周期</h3>
                    </div>
                  </div>
                  <Collapse
                    className="inline_collapse"
                    items={[
                      {
                        key: 'wristband-config',
                        label: '配置下发',
                        children: (
                          <>
                            <div className="explanation_note">
                              <strong className="explanation_title">手环配置字段说明</strong>
                              <div>
                                当前支持下发 <code>hr_alert_threshold_high</code>、<code>hr_alert_threshold_low</code>、<code>notify_interval_ms</code> 与 <code>fall_detect_enabled</code>。
                                设备侧当前没有 ACK，成功仅表示网关已转发到局域网链路。
                              </div>
                            </div>
                            <Form form={form} layout="vertical" onFinish={(values) => void submit_command(values)}>
                              <Form.Item
                                name="hr_alert_threshold_high"
                                label="高心率阈值（bpm）"
                                rules={[{ required: true, message: '请输入高心率阈值' }]}
                              >
                                <InputNumber min={60} max={240} style={{ width: '100%' }} />
                              </Form.Item>
                              <Form.Item
                                name="hr_alert_threshold_low"
                                label="低心率阈值（bpm）"
                                rules={[{ required: true, message: '请输入低心率阈值' }]}
                              >
                                <InputNumber min={20} max={120} style={{ width: '100%' }} />
                              </Form.Item>
                              <Form.Item
                                name="notify_interval_ms"
                                label="Notify 周期（毫秒）"
                                rules={[{ required: true, message: '请输入 Notify 周期' }]}
                              >
                                <InputNumber min={20} max={5000} style={{ width: '100%' }} />
                              </Form.Item>
                              <Form.Item name="fall_detect_enabled" label="跌倒检测" valuePropName="checked">
                                <Switch checkedChildren="启用" unCheckedChildren="关闭" />
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
                                description={`command_id=${command_result.command_id}，topic=${command_result.topic}`}
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
                    <div className="eyebrow">设备快照</div>
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
                      key: 'wristband-payload',
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
        <div className="panel_surface empty_state">当前没有手环设备</div>
      ) : (
        <div className="panel_surface empty_state">
          <Space direction="vertical" size="middle" align="center">
            <div>未找到对应手环实例</div>
            <Button onClick={() => navigate('/wristband')}>返回手环总览</Button>
          </Space>
        </div>
      )}
    </section>
  );
}
