import { useEffect, useState } from 'react';

import { Button, Collapse, Form, InputNumber, List, Select, Space, Spin, Statistic, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { fetch_devices, fetch_equipment_telemetry, publish_device_config } from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { DeviceCommandResultNotice, DeviceRuntimeStatusTag, ReadonlyTag } from '../components/device_ui';
import { PageNotice } from '../components/notice_card';
import { TimeSeriesChart } from '../components/time_series_chart';
import { use_auth_store } from '../store/auth_store';
import { use_business_realtime_store } from '../store/business_realtime_store';
import type { DeviceConfigPublishResult, DeviceSummary, TelemetryRecord } from '../types/backend';
import { page_error_fallbacks, page_notice_titles } from '../ui/message_catalog';
import { describe_device_runtime_status, is_device_runtime_active } from '../utils/device_status';
import { normalize_equipment_binding_id } from '../utils/equipment_binding';

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

type ChartRow = Record<string, unknown> & {
  ts?: string | number;
};

export function EquipmentPage() {
  const navigate = useNavigate();
  const { device_id: route_device_id } = useParams<{ device_id?: string }>();
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [wristbands, set_wristbands] = useState<DeviceSummary[]>([]);
  const [selected_window, set_selected_window] = useState<ChartWindow>('2h');
  const [telemetry, set_telemetry] = useState<TelemetryRecord[]>([]);
  const [command_result, set_command_result] = useState<DeviceConfigPublishResult | null>(null);
  const [command_loading, set_command_loading] = useState(false);
  const [form] = Form.useForm<{ target_reps: number }>();

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
      set_wristbands([]);
      return;
    }

    let mounted = true;
    async function load() {
      set_loading(true);
      set_error(null);
      try {
        const [equipment_devices, wristband_devices] = await Promise.all([
          fetch_devices({ type: 'equipment' }),
          fetch_devices({ type: 'wristband' })
        ]);
        if (!mounted) {
          return;
        }
        set_devices(equipment_devices);
        set_wristbands(wristband_devices);
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : page_error_fallbacks.equipment_list_load_failed);
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
      return;
    }

    let mounted = true;
    async function load_telemetry() {
      if (!selected_device_id) {
        return;
      }
      try {
        const response = await fetch_equipment_telemetry(selected_device_id, {
          start: new Date(build_window_start(selected_window)).toISOString(),
          end: new Date().toISOString(),
          limit: 200
        });
        if (mounted) {
          set_telemetry(response);
        }
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : page_error_fallbacks.equipment_telemetry_load_failed);
        }
      }
    }
    void load_telemetry();
    return () => {
      mounted = false;
    };
  }, [selected_device_id, selected_window, session]);

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 器材总览"
        title="先看全部器材"
        description="器材管理依赖后台受保护的设备列表、遥测查询与配置下发接口，未登录时不再触发这些请求。"
      />
    );
  }

  const selected_device = devices.find((item) => item.device_id === selected_device_id) ?? null;
  const bound_wristbands = wristbands.filter(
    (item) => normalize_equipment_binding_id(item.last_payload.current_equipment_id, item.last_payload.relayed_by) === selected_device_id
  );
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
      name: '功率',
      color: '#125b56',
      points: chart_rows
        .map((row) => {
          const value = to_number(row['power_w']);
          const ts_ms = to_timestamp_ms(row.ts);
          if (value === null || ts_ms === null) {
            return null;
          }
          return { ts_ms, value };
        })
        .filter((item): item is { ts_ms: number; value: number } => item !== null)
    },
    {
      name: '重复次数',
      color: '#d97706',
      points: chart_rows
        .map((row) => {
          const value = to_number(row['rep_count']);
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

  const latest_payload = selected_device?.last_payload ?? {};
  const overview_summary = {
    total: devices.length,
    online: devices.filter((item) => item.online).length,
    active: devices.filter((item) => is_device_runtime_active(item.status, String(item.last_payload.status ?? ''))).length,
    bound: wristbands.filter((item) => normalize_equipment_binding_id(item.last_payload.current_equipment_id, item.last_payload.relayed_by) !== null).length
  };

  async function submit_command(values: { target_reps: number }) {
    if (!selected_device) {
      return;
    }

    set_command_loading(true);
    set_error(null);
    try {
      const result = await publish_device_config(selected_device.device_id, {
        gym_id: selected_device.gym_id,
        gateway_id: selected_device.gateway_id,
        device_type: 'equipment',
        config: {
          ts: Math.floor(Date.now() / 1000),
          target_reps: values.target_reps
        }
      });
      set_command_result(result);
    } catch (submit_error) {
      set_error(submit_error instanceof Error ? submit_error.message : page_error_fallbacks.equipment_config_publish_failed);
    } finally {
      set_command_loading(false);
    }
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">{is_overview ? '06 网页端 / 器材总览' : '06 网页端 / 器材总览 / 实例详情'}</div>
          <h1>{is_overview ? '先看全部器材' : '查看单台器材'}</h1>
          <p>{is_overview ? '统一查看器材清单并进入实例详情。' : '统一查看单台器材状态、曲线与配置。'}</p>
        </div>
        {!is_overview ? (
          <div className="hero_actions">
            <Button onClick={() => navigate('/equipment')}>返回器材总览</Button>
          </div>
        ) : null}
      </section>

      {error ? <PageNotice tone="error" title={page_notice_titles.equipment_error} description={error} /> : null}

      {loading ? (
        <div className="panel_surface loading_surface"><Spin size="large" /></div>
      ) : is_overview ? (
        <>
          <section className="metric_grid">
            <div className="panel_surface metric_card"><Statistic title="器材总数" value={overview_summary.total} /></div>
            <div className="panel_surface metric_card"><Statistic title="在线器材" value={overview_summary.online} /></div>
            <div className="panel_surface metric_card"><Statistic title="活跃器材" value={overview_summary.active} /></div>
            <div className="panel_surface metric_card"><Statistic title="绑定中的手环" value={overview_summary.bound} /></div>
          </section>

          <div className="panel_surface">
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">器材总览</div>
                <h3>全部器材实例</h3>
              </div>
              <div className="panel_meta_text">点击卡片进入实例详情</div>
            </div>
            <section className="overview_card_grid">
              {devices.map((device) => {
                const payload = device.last_payload ?? {};
                const current_bound_wristbands = wristbands.filter(
                  (item) => normalize_equipment_binding_id(item.last_payload.current_equipment_id, item.last_payload.relayed_by) === device.device_id
                ).length;
                return (
                  <button
                    key={device.device_id}
                    type="button"
                    className="device_overview_card"
                    onClick={() => navigate(`/equipment/${device.device_id}`)}
                  >
                    <div className="device_overview_header">
                      <div>
                        <strong>{device.device_id}</strong>
                        <div className="device_overview_subtitle">{device.gym_id}</div>
                      </div>
                      <DeviceRuntimeStatusTag status={device.status} />
                    </div>
                    <div className="device_overview_metrics">
                      <span>功率 {to_number(payload.power_w) ?? 0} W</span>
                      <span>次数 {to_number(payload.rep_count) ?? 0}</span>
                      <span>手环 {current_bound_wristbands}</span>
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
            <div className="panel_surface metric_card"><Statistic title="在线状态" value={selected_device.online ? '在线' : '离线'} /></div>
            <div className="panel_surface metric_card"><Statistic title="当前功率(W)" value={to_number(latest_payload.power_w) ?? 0} precision={1} /></div>
            <div className="panel_surface metric_card"><Statistic title="重复次数" value={to_number(latest_payload.rep_count) ?? 0} /></div>
            <div className="panel_surface metric_card"><Statistic title="累计能耗" value={to_number(latest_payload.energy_wh) ?? to_number(latest_payload.energy_wh_x100) ?? 0} /></div>
          </section>

          <section className="dashboard_grid">
            <div className="left_column">
              <TimeSeriesChart
                title={`${selected_device.device_id} 训练曲线`}
                subtitle={`最近更新时间：${selected_device.last_seen_ts ? new Date(selected_device.last_seen_ts * 1000).toISOString() : '--'} · 观察窗口：${selected_window_label}`}
                series={chart_series}
                empty_message="当前器材还没有曲线数据"
                window_start_ms={chart_window_start}
                window_end_ms={chart_window_end}
                header_extra={
                  <Space wrap>
                    <Select
                      value={selected_device_id ?? undefined}
                      placeholder="选择器材"
                      onChange={(value) => navigate(`/equipment/${value}`)}
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
                    <div className="eyebrow">绑定手环</div>
                    <h3>当前关联快照</h3>
                  </div>
                </div>
                <List
                  locale={{ emptyText: '当前没有发现绑定到该器材的手环快照' }}
                  dataSource={bound_wristbands}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta
                        title={item.device_id}
                        description={`状态：${describe_device_runtime_status(item.status).label} · 最后时间：${format_last_seen(item.last_seen_ts)}`}
                      />
                    </List.Item>
                  )}
                />
              </div>

              {can_publish_config ? (
                <div className="panel_surface">
                  <div className="panel_header compact_panel_header">
                    <div>
                      <div className="eyebrow">配置下发</div>
                      <h3>目标重复次数</h3>
                    </div>
                  </div>
                  <Collapse
                    className="inline_collapse"
                    items={[
                      {
                        key: 'equipment-config',
                        label: '配置下发',
                        children: (
                          <>
                            <div className="explanation_note">
                              <strong className="explanation_title"><code>target_reps</code> 的含义</strong>
                              <div>
                                这里的“目标重复次数”对应下发字段 <code>target_reps</code>，用于给器材端设置本轮训练目标或计数基线。
                                它不是后台统计结果，而是主动下发的配置值。
                              </div>
                            </div>
                            <Form form={form} layout="vertical" onFinish={(values) => void submit_command(values)}>
                              <Form.Item
                                name="target_reps"
                                label="目标重复次数（target_reps）"
                                rules={[{ required: true, message: '请输入目标次数' }]}
                              >
                                <InputNumber min={1} max={9999} style={{ width: '100%' }} />
                              </Form.Item>
                              <Button htmlType="submit" type="primary" loading={command_loading} block>
                                下发到网关
                              </Button>
                            </Form>
                            {command_result ? <DeviceCommandResultNotice result={command_result} /> : null}
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
                    {is_read_only ? <ReadonlyTag /> : null}
                    <DeviceRuntimeStatusTag status={selected_device?.status} />
                  </Space>
                </div>
                <Collapse
                  className="inline_collapse"
                  items={[
                    {
                      key: 'equipment-payload',
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
        <div className="panel_surface empty_state">当前没有器材设备</div>
      ) : (
        <div className="panel_surface empty_state">
          <Space direction="vertical" size="middle" align="center">
            <div>未找到对应器材实例</div>
            <Button onClick={() => navigate('/equipment')}>返回器材总览</Button>
          </Space>
        </div>
      )}
    </section>
  );
}
