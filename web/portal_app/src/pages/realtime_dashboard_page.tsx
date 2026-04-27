import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Drawer, List, Space, Statistic, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

import { fetch_business_alerts, fetch_devices } from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { DeviceRuntimeStatusTag } from '../components/device_ui';
import { PageNotice } from '../components/notice_card';
import { use_auth_store } from '../store/auth_store';
import { use_business_realtime_store } from '../store/business_realtime_store';
import type { DeviceSummary } from '../types/backend';
import { page_error_fallbacks, page_notice_titles } from '../ui/message_catalog';
import { is_device_runtime_active } from '../utils/device_status';
import { format_time } from '../utils/time';

type DrawerMode = 'all_devices' | 'offline_devices' | 'business_alerts' | null;
type TrendDirection = 'up' | 'down' | 'flat';

type BindingViewRecord = {
  wristband_id: string;
  equipment_id: string;
  relayed_by: string | null;
  status: string;
  last_seen_ts: number | null;
};

type DashboardDeviceView = {
  devices: DeviceSummary[];
  offline_devices: DeviceSummary[];
  current_bindings: BindingViewRecord[];
  totals: {
    all: number;
    offline: number;
    bindings: number;
  };
  env_summary: {
    avg_temperature: number | null;
    avg_humidity: number | null;
    avg_co2: number | null;
    avg_pm25: number | null;
  };
  energy_summary: {
    active_equipment_count: number;
    total_power_w: number;
    average_power_w: number | null;
    total_energy_wh: number;
  };
  device_type_summary: {
    equipment: number;
    env: number;
    wristband: number;
  };
  offline_type_summary: {
    equipment: number;
    env: number;
    wristband: number;
  };
};

function to_number(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function get_device_type_label(device_type: string): string {
  if (device_type === 'equipment') {
    return '器材';
  }
  if (device_type === 'env') {
    return '环境';
  }
  if (device_type === 'wristband') {
    return '手环';
  }
  return device_type;
}

function average_from_sum(sum: number, count: number): number | null {
  if (count === 0) {
    return null;
  }
  return sum / count;
}

function compare_values(current: number | null, previous: number | null): TrendDirection {
  if (current === null || previous === null || current === previous) {
    return 'flat';
  }
  return current > previous ? 'up' : 'down';
}

function normalize_equipment_binding_id(value: unknown): string | null {
  if (typeof value === 'string') {
    if (value === '' || value === '255' || value.toLowerCase() === 'none') {
      return null;
    }
    return value;
  }
  if (typeof value === 'number') {
    if (value === 255) {
      return null;
    }
    return `eq-${String(value).padStart(3, '0')}`;
  }
  return null;
}

function create_empty_device_view(devices: DeviceSummary[]): DashboardDeviceView {
  return {
    devices,
    offline_devices: [],
    current_bindings: [],
    totals: {
      all: devices.length,
      offline: 0,
      bindings: 0
    },
    env_summary: {
      avg_temperature: null,
      avg_humidity: null,
      avg_co2: null,
      avg_pm25: null
    },
    energy_summary: {
      active_equipment_count: 0,
      total_power_w: 0,
      average_power_w: null,
      total_energy_wh: 0
    },
    device_type_summary: {
      equipment: 0,
      env: 0,
      wristband: 0
    },
    offline_type_summary: {
      equipment: 0,
      env: 0,
      wristband: 0
    }
  };
}

function build_device_view(devices: DeviceSummary[]): DashboardDeviceView {
  const view = create_empty_device_view(devices);
  let env_temperature_sum = 0;
  let env_temperature_count = 0;
  let env_humidity_sum = 0;
  let env_humidity_count = 0;
  let env_co2_sum = 0;
  let env_co2_count = 0;
  let env_pm25_sum = 0;
  let env_pm25_count = 0;
  let equipment_power_count = 0;

  for (const device of devices) {
    if (device.device_type === 'equipment' || device.device_type === 'env' || device.device_type === 'wristband') {
      view.device_type_summary[device.device_type] += 1;
    }

    if (!device.online) {
      view.offline_devices.push(device);
      if (device.device_type === 'equipment' || device.device_type === 'env' || device.device_type === 'wristband') {
        view.offline_type_summary[device.device_type] += 1;
      }
      continue;
    }

    if (device.device_type === 'env') {
      const temperature = to_number(device.last_payload.temperature_c) ?? to_number(device.last_payload.temperature);
      const humidity = to_number(device.last_payload.humidity);
      const co2 = to_number(device.last_payload.co2_ppm);
      const pm25 = to_number(device.last_payload.pm2_5);
      if (temperature !== null) {
        env_temperature_sum += temperature;
        env_temperature_count += 1;
      }
      if (humidity !== null) {
        env_humidity_sum += humidity;
        env_humidity_count += 1;
      }
      if (co2 !== null) {
        env_co2_sum += co2;
        env_co2_count += 1;
      }
      if (pm25 !== null) {
        env_pm25_sum += pm25;
        env_pm25_count += 1;
      }
    }

    if (device.device_type === 'equipment') {
      const power = to_number(device.last_payload.power_w);
      const energy = to_number(device.last_payload.energy_wh) ?? to_number(device.last_payload.energy_wh_x100);
      if (power !== null) {
        view.energy_summary.total_power_w += power;
        equipment_power_count += 1;
      }
      if (energy !== null) {
        view.energy_summary.total_energy_wh += energy;
      }
      if (is_device_runtime_active(device.status, String(device.last_payload.status ?? ''))) {
        view.energy_summary.active_equipment_count += 1;
      }
    }

    if (device.device_type === 'wristband') {
      const equipment_id = normalize_equipment_binding_id(device.last_payload.current_equipment_id);
      if (equipment_id !== null) {
        view.current_bindings.push({
          wristband_id: device.device_id,
          equipment_id,
          relayed_by: typeof device.last_payload.relayed_by === 'string' ? device.last_payload.relayed_by : null,
          status: device.status,
          last_seen_ts: device.last_seen_ts
        });
      }
    }
  }

  view.totals.offline = view.offline_devices.length;
  view.totals.bindings = view.current_bindings.length;
  view.env_summary.avg_temperature = average_from_sum(env_temperature_sum, env_temperature_count);
  view.env_summary.avg_humidity = average_from_sum(env_humidity_sum, env_humidity_count);
  view.env_summary.avg_co2 = average_from_sum(env_co2_sum, env_co2_count);
  view.env_summary.avg_pm25 = average_from_sum(env_pm25_sum, env_pm25_count);
  view.energy_summary.average_power_w = average_from_sum(view.energy_summary.total_power_w, equipment_power_count);
  return view;
}

function MetricGlyph({ kind }: { kind: 'temperature' | 'humidity' | 'co2' | 'pm25' }) {
  if (kind === 'temperature') {
    return (
      <svg viewBox="0 0 48 48" className="dashboard_metric_icon" aria-hidden="true">
        <path d="M22 10a4 4 0 1 1 8 0v14.8a9 9 0 1 1-8 0Z" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M26 16v14" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (kind === 'humidity') {
    return (
      <svg viewBox="0 0 48 48" className="dashboard_metric_icon" aria-hidden="true">
        <path d="M24 8c6.6 8 10 13.4 10 19.2A10 10 0 0 1 14 27.2C14 21.4 17.4 16 24 8Z" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinejoin="round" />
        <path d="M20 29.5c1.7 2 5.6 2 7.3 0" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (kind === 'co2') {
    return (
      <svg viewBox="0 0 48 48" className="dashboard_metric_icon" aria-hidden="true">
        <circle cx="18" cy="24" r="8" fill="none" stroke="currentColor" strokeWidth="3.5" />
        <circle cx="30" cy="18" r="6" fill="none" stroke="currentColor" strokeWidth="3.5" />
        <circle cx="31" cy="30" r="7" fill="none" stroke="currentColor" strokeWidth="3.5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 48 48" className="dashboard_metric_icon" aria-hidden="true">
      <path d="M11 29h7l3-10 6 18 4-8h6" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M13 18h5M15 13h8" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
    </svg>
  );
}

function TrendArrow({ direction }: { direction: TrendDirection }) {
  return (
    <span className={`energy_trend_badge is_${direction}`} aria-hidden="true">
      <svg viewBox="0 0 16 16" className="energy_trend_icon">
        {direction === 'flat' ? (
          <path d="M3 8h10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        ) : (
          <path d={direction === 'up' ? 'M8 3l4 5H9.4V13H6.6V8H4z' : 'M8 13l-4-5h2.6V3h2.8v5H12z'} fill="currentColor" />
        )}
      </svg>
    </span>
  );
}

function format_binding_time(last_seen_ts: number | null): string {
  return last_seen_ts ? dayjs.unix(last_seen_ts).format('MM-DD HH:mm:ss') : '--';
}

export function RealtimeDashboardPage() {
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [drawer_mode, set_drawer_mode] = useState<DrawerMode>(null);
  const binding_section_ref = useRef<HTMLDivElement | null>(null);
  const previous_energy_summary_ref = useRef<{
    active_equipment_count: number;
    total_power_w: number;
    average_power_w: number | null;
    total_energy_wh: number;
  } | null>(null);
  const [energy_trends, set_energy_trends] = useState({
    active_equipment_count: 'flat' as TrendDirection,
    total_power_w: 'flat' as TrendDirection,
    average_power_w: 'flat' as TrendDirection,
    total_energy_wh: 'flat' as TrendDirection
  });

  const ws_state = use_business_realtime_store((state) => state.ws_state);
  const devices_by_id = use_business_realtime_store((state) => state.devices_by_id);
  const alerts_by_id = use_business_realtime_store((state) => state.alerts_by_id);
  const connect = use_business_realtime_store((state) => state.connect);
  const disconnect = use_business_realtime_store((state) => state.disconnect);
  const hydrate_snapshot = use_business_realtime_store((state) => state.hydrate_snapshot);
  const clear_snapshot = use_business_realtime_store((state) => state.clear_snapshot);
  const session = use_auth_store((state) => state.session);
  const previous_ws_state_ref = useRef<'idle' | 'connecting' | 'open' | 'closed'>('idle');
  const has_seen_open_once_ref = useRef(false);

  useEffect(() => {
    if (!session) {
      disconnect();
      previous_ws_state_ref.current = 'idle';
      has_seen_open_once_ref.current = false;
      return;
    }
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect, session]);

  const load_snapshot = useCallback(
    async (options?: { silent?: boolean }) => {
      const silent = options?.silent ?? false;
      if (!session) {
        set_loading(false);
        set_error(null);
        clear_snapshot();
        return;
      }

      if (!silent) {
        set_loading(true);
      }
      set_error(null);
      const [device_items, alert_items] = await Promise.all([fetch_devices(), fetch_business_alerts({ is_ack: false })]);
      hydrate_snapshot({ devices: device_items, alerts: alert_items });
      if (!silent) {
        set_loading(false);
      }
    },
    [clear_snapshot, hydrate_snapshot, session]
  );

  useEffect(() => {
    if (!session) {
      set_loading(false);
      set_error(null);
      clear_snapshot();
      return;
    }

    let mounted = true;

    async function load() {
      try {
        await load_snapshot();
      } catch (load_error) {
        if (!mounted) {
          return;
        }
        set_error(load_error instanceof Error ? load_error.message : page_error_fallbacks.dashboard_load_failed);
        set_loading(false);
      }
    }

    void load();

    return () => {
      mounted = false;
    };
  }, [clear_snapshot, load_snapshot, session]);

  useEffect(() => {
    const previous_ws_state = previous_ws_state_ref.current;
    previous_ws_state_ref.current = ws_state;

    if (!session || ws_state !== 'open' || previous_ws_state === 'open') {
      return;
    }
    if (!has_seen_open_once_ref.current) {
      has_seen_open_once_ref.current = true;
      return;
    }

    void load_snapshot({ silent: true }).catch((load_error) => {
      set_error(load_error instanceof Error ? load_error.message : page_error_fallbacks.dashboard_load_failed);
    });
  }, [load_snapshot, session, ws_state]);

  const devices = useMemo(() => Object.values(devices_by_id), [devices_by_id]);
  const {
    offline_devices,
    current_bindings,
    totals,
    env_summary,
    energy_summary,
    device_type_summary,
    offline_type_summary
  } = useMemo(() => build_device_view(devices), [devices]);
  const open_alerts = useMemo(() => Object.values(alerts_by_id).filter((item) => !item.is_ack), [alerts_by_id]);
  const sorted_open_alerts = useMemo(() => {
    if (drawer_mode !== 'business_alerts') {
      return open_alerts.slice(0, 50);
    }
    return [...open_alerts].sort((left, right) => {
      const left_ts = Date.parse(left.triggered_at);
      const right_ts = Date.parse(right.triggered_at);
      if (!Number.isNaN(left_ts) && !Number.isNaN(right_ts) && left_ts !== right_ts) {
        return right_ts - left_ts;
      }
      return right.id - left.id;
    });
  }, [drawer_mode, open_alerts]);
  const alert_count = open_alerts.length;
  const alert_level_summary = {
    critical: open_alerts.filter((item) => item.level === 'critical').length,
    warning: open_alerts.filter((item) => item.level === 'warning').length,
    info: open_alerts.filter((item) => item.level === 'info').length
  };

  useEffect(() => {
    const previous = previous_energy_summary_ref.current;
    if (previous) {
      set_energy_trends({
        active_equipment_count: compare_values(energy_summary.active_equipment_count, previous.active_equipment_count),
        total_power_w: compare_values(energy_summary.total_power_w, previous.total_power_w),
        average_power_w: compare_values(energy_summary.average_power_w, previous.average_power_w),
        total_energy_wh: compare_values(energy_summary.total_energy_wh, previous.total_energy_wh)
      });
    }
    previous_energy_summary_ref.current = energy_summary;
  }, [
    energy_summary.active_equipment_count,
    energy_summary.average_power_w,
    energy_summary.total_energy_wh,
    energy_summary.total_power_w
  ]);

  const device_columns: ColumnsType<DeviceSummary> = [
    { title: '设备', dataIndex: 'device_id', key: 'device_id' },
    {
      title: '类型',
      dataIndex: 'device_type',
      key: 'device_type',
      render: (value: string) => <Tag>{get_device_type_label(value)}</Tag>
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

  const drawer_title =
    drawer_mode === 'all_devices'
      ? '设备总数'
      : drawer_mode === 'offline_devices'
        ? '离线设备'
        : '未确认业务告警';

  function scroll_to_bindings() {
    binding_section_ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 实时仪表盘"
        title="先看现场状态"
        description="统一查看离线态势、环境均值与绑定关系。"
      />
    );
  }

  return (
    <section className="page_shell">
      <section className="hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 实时仪表盘</div>
          <h1>先看现场状态</h1>
          <p>统一查看离线态势、环境均值与绑定关系。</p>
        </div>
        <div className="hero_actions">
          <div className="ws_indicator">业务 WS: {ws_state}</div>
        </div>
      </section>

      {error ? <PageNotice tone="error" title={page_notice_titles.dashboard_error} description={error} /> : null}

      <section className="metric_grid">
        <button type="button" className="panel_surface metric_card interactive_metric_card dashboard_summary_card" onClick={() => set_drawer_mode('all_devices')}>
          <div className="dashboard_summary_header">
            <span className="dashboard_summary_title">设备总数</span>
            <strong className="dashboard_summary_value">{totals.all}</strong>
          </div>
          <div className="dashboard_summary_meta">
            <span>器材 {device_type_summary.equipment}</span>
            <span>环境 {device_type_summary.env}</span>
            <span>手环 {device_type_summary.wristband}</span>
          </div>
        </button>
        <button type="button" className="panel_surface metric_card interactive_metric_card dashboard_summary_card" onClick={() => set_drawer_mode('offline_devices')}>
          <div className="dashboard_summary_header">
            <span className="dashboard_summary_title">离线设备</span>
            <strong className="dashboard_summary_value">{totals.offline}</strong>
          </div>
          <div className="dashboard_summary_meta">
            <span>器材 {offline_type_summary.equipment}</span>
            <span>环境 {offline_type_summary.env}</span>
            <span>手环 {offline_type_summary.wristband}</span>
          </div>
        </button>
        <button type="button" className="panel_surface metric_card interactive_metric_card dashboard_summary_card" onClick={() => set_drawer_mode('business_alerts')}>
          <div className="dashboard_summary_header">
            <span className="dashboard_summary_title">未确认告警</span>
            <strong className="dashboard_summary_value">{alert_count}</strong>
          </div>
          <div className="dashboard_summary_meta">
            <span>严重 {alert_level_summary.critical}</span>
            <span>警告 {alert_level_summary.warning}</span>
            <span>提示 {alert_level_summary.info}</span>
          </div>
        </button>
        <button type="button" className="panel_surface metric_card interactive_metric_card dashboard_summary_card" onClick={scroll_to_bindings}>
          <div className="dashboard_summary_header">
            <span className="dashboard_summary_title">当前绑定关系</span>
            <strong className="dashboard_summary_value">{totals.bindings}</strong>
          </div>
          <div className="dashboard_summary_meta">
            <span>手环与器材实时关联</span>
            <span>点击定位到绑定视图</span>
          </div>
        </button>
      </section>

      <div className="panel_surface dashboard_section_surface">
        <div className="panel_header compact_panel_header">
          <div>
            <div className="eyebrow">环境均值</div>
            <h3>在线环境节点快照</h3>
          </div>
        </div>
        <section className="metric_grid">
          <article className="panel_surface metric_card dashboard_feature_card env_card temperature_card">
            <div className="dashboard_metric_icon_shell"><MetricGlyph kind="temperature" /></div>
            <div className="dashboard_metric_copy">
              <span className="dashboard_metric_label">平均温度</span>
              <strong>{env_summary.avg_temperature !== null ? `${env_summary.avg_temperature.toFixed(1)} °C` : '--'}</strong>
              <span className="dashboard_metric_hint">覆盖全部在线环境节点</span>
            </div>
          </article>
          <article className="panel_surface metric_card dashboard_feature_card env_card humidity_card">
            <div className="dashboard_metric_icon_shell"><MetricGlyph kind="humidity" /></div>
            <div className="dashboard_metric_copy">
              <span className="dashboard_metric_label">平均湿度</span>
              <strong>{env_summary.avg_humidity !== null ? `${env_summary.avg_humidity.toFixed(1)} %` : '--'}</strong>
              <span className="dashboard_metric_hint">关注通风与体感舒适度</span>
            </div>
          </article>
          <article className="panel_surface metric_card dashboard_feature_card env_card co2_card">
            <div className="dashboard_metric_icon_shell"><MetricGlyph kind="co2" /></div>
            <div className="dashboard_metric_copy">
              <span className="dashboard_metric_label">平均 CO₂</span>
              <strong>{env_summary.avg_co2 !== null ? `${env_summary.avg_co2.toFixed(0)} ppm` : '--'}</strong>
              <span className="dashboard_metric_hint">反映当前场馆空气负荷</span>
            </div>
          </article>
          <article className="panel_surface metric_card dashboard_feature_card env_card pm25_card">
            <div className="dashboard_metric_icon_shell"><MetricGlyph kind="pm25" /></div>
            <div className="dashboard_metric_copy">
              <span className="dashboard_metric_label">平均 PM2.5</span>
              <strong>{env_summary.avg_pm25 !== null ? env_summary.avg_pm25.toFixed(1) : '--'}</strong>
              <span className="dashboard_metric_hint">颗粒物水平与训练舒适度</span>
            </div>
          </article>
        </section>
      </div>

      <div className="panel_surface dashboard_section_surface">
        <div className="panel_header compact_panel_header">
          <div>
            <div className="eyebrow">能耗汇总</div>
            <h3>在线器材快照</h3>
          </div>
        </div>
        <section className="metric_grid">
          <article className="panel_surface metric_card dashboard_feature_card energy_card">
            <div className="dashboard_metric_heading">
              <span className="dashboard_metric_label">活跃器材数</span>
              <TrendArrow direction={energy_trends.active_equipment_count} />
            </div>
            <strong>{energy_summary.active_equipment_count}</strong>
            <span className="dashboard_metric_hint">与上一轮采样快照相比</span>
          </article>
          <article className="panel_surface metric_card dashboard_feature_card energy_card">
            <div className="dashboard_metric_heading">
              <span className="dashboard_metric_label">当前总功率</span>
              <TrendArrow direction={energy_trends.total_power_w} />
            </div>
            <strong>{energy_summary.total_power_w.toFixed(1)} W</strong>
            <span className="dashboard_metric_hint">在线器材瞬时负载汇总</span>
          </article>
          <article className="panel_surface metric_card dashboard_feature_card energy_card">
            <div className="dashboard_metric_heading">
              <span className="dashboard_metric_label">平均功率</span>
              <TrendArrow direction={energy_trends.average_power_w} />
            </div>
            <strong>{energy_summary.average_power_w !== null ? `${energy_summary.average_power_w.toFixed(1)} W` : '--'}</strong>
            <span className="dashboard_metric_hint">当前活跃器材的平均负荷</span>
          </article>
          <article className="panel_surface metric_card dashboard_feature_card energy_card">
            <div className="dashboard_metric_heading">
              <span className="dashboard_metric_label">累计能耗</span>
              <TrendArrow direction={energy_trends.total_energy_wh} />
            </div>
            <strong>{energy_summary.total_energy_wh.toFixed(1)} Wh</strong>
            <span className="dashboard_metric_hint">累计训练能耗总量</span>
          </article>
        </section>
      </div>

      <div className="panel_surface dashboard_section_surface binding_view_surface" ref={binding_section_ref}>
        <div className="panel_header compact_panel_header">
          <div>
            <div className="eyebrow">绑定视图</div>
            <h3>当前手环与器材关联</h3>
          </div>
          <div className="panel_meta_text">共 {totals.bindings} 组绑定关系</div>
        </div>
        {current_bindings.length > 0 ? (
          <section className="binding_scene">
            {current_bindings.map((item) => (
              <article key={`${item.wristband_id}-${item.equipment_id}`} className="binding_pair_card">
                <div className="binding_pair_orbit">
                  <div className="binding_circle wristband_node">
                    <span>手环</span>
                    <strong>{item.wristband_id}</strong>
                  </div>
                  <div className="binding_circle equipment_node">
                    <span>器材</span>
                    <strong>{item.equipment_id}</strong>
                  </div>
                </div>
                <div className="binding_pair_copy">
                  <div className="binding_pair_header">
                    <span>{item.wristband_id}</span>
                    <span className="binding_pair_link">↔</span>
                    <span>{item.equipment_id}</span>
                  </div>
                  <div className="binding_pair_meta">
                    <DeviceRuntimeStatusTag status={item.status} />
                    <span>转发：{item.relayed_by ?? '--'}</span>
                    <span>最后上报：{format_binding_time(item.last_seen_ts)}</span>
                  </div>
                </div>
              </article>
            ))}
          </section>
        ) : (
          <div className="binding_empty_state">当前没有可展示的绑定关系</div>
        )}
      </div>

      {loading ? <div className="panel_surface loading_surface"><Statistic title="加载中" value="请稍候" /></div> : null}

      <Drawer title={drawer_title} placement="right" width={520} open={drawer_mode !== null} onClose={() => set_drawer_mode(null)}>
        {drawer_mode === 'business_alerts' ? (
          <List
            locale={{ emptyText: '当前没有未确认业务告警' }}
            dataSource={sorted_open_alerts}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <Space>
                      <Tag color={item.level === 'critical' ? 'red' : item.level === 'warning' ? 'orange' : 'blue'}>{item.level}</Tag>
                      {item.message}
                    </Space>
                  }
                  description={`${item.device_id} · ${item.code} · ${format_time(item.triggered_at)}`}
                />
              </List.Item>
            )}
          />
        ) : drawer_mode === 'offline_devices' && offline_devices.length === 0 ? (
          <div className="drawer_empty_state">当前无设备离线</div>
        ) : (
          <Table
            rowKey="device_id"
            dataSource={drawer_mode === 'offline_devices' ? offline_devices : devices}
            columns={device_columns}
            pagination={{ defaultPageSize: 8 }}
          />
        )}
      </Drawer>
    </section>
  );
}
