import { useEffect, useMemo, useState } from 'react';

import { Alert, Button, Form, InputNumber, List, Select, Space, Spin, Statistic, Tag } from 'antd';

import { fetch_devices, fetch_equipment_telemetry, publish_device_config } from '../api/backend_client';
import { TimeSeriesChart } from '../components/time_series_chart';
import { use_business_realtime_store } from '../store/business_realtime_store';
import type { DeviceConfigPublishResult, DeviceSummary, TelemetryRecord } from '../types/backend';
import { format_time } from '../utils/time';

function to_number(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

type ChartRow = Record<string, unknown> & {
  ts?: string | number;
};

export function EquipmentPage() {
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [wristbands, set_wristbands] = useState<DeviceSummary[]>([]);
  const [selected_device_id, set_selected_device_id] = useState<string | null>(null);
  const [telemetry, set_telemetry] = useState<TelemetryRecord[]>([]);
  const [command_result, set_command_result] = useState<DeviceConfigPublishResult | null>(null);
  const [command_loading, set_command_loading] = useState(false);
  const [form] = Form.useForm<{ target_reps: number }>();

  const realtime_points = use_business_realtime_store((state) =>
    selected_device_id ? state.telemetry_by_device[selected_device_id] ?? [] : []
  );
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
        const [equipment_devices, wristband_devices] = await Promise.all([
          fetch_devices({ type: 'equipment' }),
          fetch_devices({ type: 'wristband' })
        ]);
        if (!mounted) {
          return;
        }
        set_devices(equipment_devices);
        set_wristbands(wristband_devices);
        set_selected_device_id((current) => current ?? equipment_devices[0]?.device_id ?? null);
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : '器材列表加载失败');
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
  }, []);

  useEffect(() => {
    let mounted = true;
    async function load_telemetry() {
      if (!selected_device_id) {
        return;
      }
      try {
        const response = await fetch_equipment_telemetry(selected_device_id, { limit: 120 });
        if (mounted) {
          set_telemetry(response);
        }
      } catch (load_error) {
        if (mounted) {
          set_error(load_error instanceof Error ? load_error.message : '器材遥测加载失败');
        }
      }
    }
    void load_telemetry();
    return () => {
      mounted = false;
    };
  }, [selected_device_id]);

  const selected_device = devices.find((item) => item.device_id === selected_device_id) ?? null;
  const bound_wristbands = wristbands.filter((item) => item.last_payload.current_equipment_id === selected_device_id);
  const chart_rows: ChartRow[] =
    realtime_points.length > 0
      ? realtime_points.map((item) => item as ChartRow)
      : telemetry.map((item) => ({ ts: item.ts, ...item.payload }));
  const chart_series = [
    {
      name: '功率',
      color: '#125b56',
      points: chart_rows
        .map((row) => {
          const value = to_number(row['power_w']);
          if (value === null) {
            return null;
          }
          return { label: format_time(typeof row.ts === 'string' ? row.ts : new Date(Number(row.ts) * 1000).toISOString()).slice(11), value };
        })
        .filter((item): item is { label: string; value: number } => item !== null)
    },
    {
      name: '重复次数',
      color: '#d97706',
      points: chart_rows
        .map((row) => {
          const value = to_number(row['rep_count']);
          if (value === null) {
            return null;
          }
          return { label: format_time(typeof row.ts === 'string' ? row.ts : new Date(Number(row.ts) * 1000).toISOString()).slice(11), value };
        })
        .filter((item): item is { label: string; value: number } => item !== null)
    }
  ].filter((item) => item.points.length > 0);

  const latest_payload = selected_device?.last_payload ?? {};

  async function submit_command(values: { target_reps: number }) {
    if (!selected_device) {
      return;
    }

    set_command_loading(true);
    set_error(null);
    try {
      const result = await publish_device_config(selected_device.device_id, {
        gym_id: selected_device.gym_id,
        device_type: 'equipment',
        config: {
          ts: Math.floor(Date.now() / 1000),
          target_reps: values.target_reps
        }
      });
      set_command_result(result);
    } catch (submit_error) {
      set_error(submit_error instanceof Error ? submit_error.message : '器材配置下发失败');
    } finally {
      set_command_loading(false);
    }
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 器材管理</div>
          <h1>单台器材详情、实时曲线与配置下发</h1>
          <p>器材详情当前使用后台设备快照、历史遥测和实时 WebSocket 叠加展示。配置下发直接调用后台设备配置接口。</p>
        </div>
        <Select
          value={selected_device_id ?? undefined}
          placeholder="选择器材"
          onChange={set_selected_device_id}
          options={devices.map((item) => ({ value: item.device_id, label: item.device_id }))}
          style={{ minWidth: 240 }}
        />
      </section>

      {error ? <Alert type="error" message="器材管理异常" description={error} showIcon /> : null}

      {selected_device ? (
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
                subtitle={`最近更新时间：${selected_device.last_seen_ts ? new Date(selected_device.last_seen_ts * 1000).toISOString() : '--'}`}
                series={chart_series}
                empty_message="当前器材还没有曲线数据"
              />

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
                        description={`状态：${item.status} · 最后时间：${item.last_seen_ts ? new Date(item.last_seen_ts * 1000).toLocaleString() : '--'}`}
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
                    <div className="eyebrow">配置下发</div>
                    <h3>目标次数</h3>
                  </div>
                </div>
                <Form form={form} layout="vertical" onFinish={(values) => void submit_command(values)}>
                  <Form.Item name="target_reps" label="目标重复次数" rules={[{ required: true, message: '请输入目标次数' }]}>
                    <InputNumber min={1} max={9999} style={{ width: '100%' }} />
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
              </div>

              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">设备快照</div>
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
        <div className="panel_surface empty_state">当前没有器材设备</div>
      )}
    </section>
  );
}
