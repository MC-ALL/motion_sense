import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Alert, Button, Select, Space, Statistic, Table, Tabs, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { ack_business_alert, batch_ack_business_alerts, fetch_business_alerts, fetch_devices } from '../api/backend_client';
import { close_ops_alert, fetch_ops_alerts } from '../api/ops_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { use_auth_store } from '../store/auth_store';
import type { BusinessAlertRecord, DeviceSummary } from '../types/backend';
import type { OpsAlertRecord } from '../types/ops';
import { describe_user_scope } from '../utils/user_scope';
import { format_time } from '../utils/time';

type AlertTab = 'business' | 'ops';

export function AlertsPage() {
  const [search_params, set_search_params] = useSearchParams();
  const session = use_auth_store((state) => state.session);
  const can_ack_business_alerts = session?.user.role === 'admin' || session?.user.role === 'teacher';
  const can_manage_ops_alerts = session?.user.role === 'admin';
  const scope_description = describe_user_scope(session?.user);

  const [loading, set_loading] = useState(true);
  const [action_loading, set_action_loading] = useState(false);
  const [error, set_error] = useState<string | null>(null);
  const [business_alerts, set_business_alerts] = useState<BusinessAlertRecord[]>([]);
  const [ops_alerts, set_ops_alerts] = useState<OpsAlertRecord[]>([]);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [level, set_level] = useState<string | undefined>(undefined);
  const [device_id, set_device_id] = useState<string | undefined>(undefined);
  const [ack_filter, set_ack_filter] = useState<'all' | 'acked' | 'open'>('open');
  const [selected_ids, set_selected_ids] = useState<number[]>([]);
  const [ops_status_filter, set_ops_status_filter] = useState<'open' | 'closed'>('open');
  const [ops_severity_filter, set_ops_severity_filter] = useState<string | undefined>(undefined);
  const [ops_module_filter, set_ops_module_filter] = useState<string | undefined>(undefined);
  const [selected_ops_ids, set_selected_ops_ids] = useState<number[]>([]);

  const requested_tab = search_params.get('tab');
  const active_tab: AlertTab = requested_tab === 'ops' && can_manage_ops_alerts ? 'ops' : 'business';

  useEffect(() => {
    if (requested_tab === 'ops' && !can_manage_ops_alerts) {
      set_search_params({ tab: 'business' }, { replace: true });
    }
  }, [can_manage_ops_alerts, requested_tab, set_search_params]);

  async function load_business_alerts() {
    const response = await fetch_business_alerts({
      level,
      device_id,
      is_ack: ack_filter === 'all' ? undefined : ack_filter === 'acked'
    });
    set_business_alerts(response);
  }

  async function load_ops_alert_items() {
    if (!can_manage_ops_alerts) {
      set_ops_alerts([]);
      return;
    }
    const response = await fetch_ops_alerts(ops_status_filter);
    const filtered_items = response.items.filter((item) => {
      if (ops_severity_filter && item.severity !== ops_severity_filter) {
        return false;
      }
      if (ops_module_filter && item.module_id !== ops_module_filter) {
        return false;
      }
      return true;
    });
    set_ops_alerts(filtered_items);
  }

  useEffect(() => {
    if (!session) {
      set_loading(false);
      set_error(null);
      set_business_alerts([]);
      set_ops_alerts([]);
      return;
    }

    let mounted = true;
    async function load() {
      set_loading(true);
      set_error(null);
      try {
        await Promise.all([
          load_business_alerts(),
          active_tab === 'ops' ? load_ops_alert_items() : Promise.resolve()
        ]);
        if (!mounted) {
          return;
        }
      } catch (load_error) {
        if (!mounted) {
          return;
        }
        set_error(load_error instanceof Error ? load_error.message : '告警加载失败');
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
  }, [ack_filter, active_tab, device_id, level, ops_module_filter, ops_severity_filter, ops_status_filter, session]);

  useEffect(() => {
    if (!session) {
      set_devices([]);
      return;
    }

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
  }, [session]);

  async function ack_one(alert_id: number) {
    set_action_loading(true);
    try {
      await ack_business_alert(alert_id);
      set_selected_ids((current) => current.filter((item) => item !== alert_id));
      await load_business_alerts();
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
      await load_business_alerts();
    } catch (action_error) {
      set_error(action_error instanceof Error ? action_error.message : '批量确认失败');
    } finally {
      set_action_loading(false);
    }
  }

  async function close_one_ops_alert(alert_id: number) {
    set_action_loading(true);
    try {
      await close_ops_alert(alert_id);
      set_selected_ops_ids((current) => current.filter((item) => item !== alert_id));
      await load_ops_alert_items();
    } catch (action_error) {
      set_error(action_error instanceof Error ? action_error.message : '运维告警关闭失败');
    } finally {
      set_action_loading(false);
    }
  }

  async function close_selected_ops_alerts() {
    if (selected_ops_ids.length === 0) {
      return;
    }
    set_action_loading(true);
    try {
      await Promise.all(selected_ops_ids.map((alert_id) => close_ops_alert(alert_id)));
      set_selected_ops_ids([]);
      await load_ops_alert_items();
    } catch (action_error) {
      set_error(action_error instanceof Error ? action_error.message : '批量关闭运维告警失败');
    } finally {
      set_action_loading(false);
    }
  }

  const business_columns: ColumnsType<BusinessAlertRecord> = [
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
        <Button size="small" disabled={record.is_ack || !can_ack_business_alerts} onClick={() => void ack_one(record.id)}>
          确认
        </Button>
      )
    }
  ];

  const ops_columns: ColumnsType<OpsAlertRecord> = [
    {
      title: '级别',
      dataIndex: 'severity',
      key: 'severity',
      render: (value: string) => <Tag color={value === 'critical' ? 'red' : value === 'warning' ? 'orange' : 'blue'}>{value}</Tag>
    },
    { title: '模块', dataIndex: 'module_id', key: 'module_id' },
    { title: '类型', dataIndex: 'alert_type', key: 'alert_type' },
    { title: '标题', dataIndex: 'title', key: 'title' },
    { title: '详情', dataIndex: 'detail', key: 'detail', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value: string) => <Tag color={value === 'open' ? 'volcano' : 'green'}>{value}</Tag>
    },
    {
      title: '触发时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value: string) => format_time(value)
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button
          size="small"
          disabled={record.status !== 'open' || !can_manage_ops_alerts}
          onClick={() => void close_one_ops_alert(record.id)}
        >
          关闭
        </Button>
      )
    }
  ];

  const business_summary = useMemo(
    () => ({
      total: business_alerts.length,
      open: business_alerts.filter((item) => !item.is_ack).length,
      critical: business_alerts.filter((item) => item.level === 'critical').length,
      selected: selected_ids.length
    }),
    [business_alerts, selected_ids.length]
  );

  const ops_summary = useMemo(
    () => ({
      total: ops_alerts.length,
      open: ops_alerts.filter((item) => item.status === 'open').length,
      critical: ops_alerts.filter((item) => item.severity === 'critical').length,
      module_count: new Set(ops_alerts.map((item) => item.module_id)).size,
      selected: selected_ops_ids.length
    }),
    [ops_alerts, selected_ops_ids.length]
  );

  const ops_module_options = Array.from(new Set(ops_alerts.map((item) => item.module_id))).map((item) => ({ value: item, label: item }));

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 告警管理"
        title="登录后可查看并处理告警"
        description="告警列表与处理操作需要后台 JWT；未登录时页面不会再向业务与运维告警接口发起请求。"
      />
    );
  }

  if (session.user.role === 'student') {
    return (
      <section className="page_shell">
        <section className="hero_banner compact_hero_banner">
          <div>
            <div className="eyebrow">06 网页端 / 告警管理</div>
            <h1>当前账号没有告警管理权限</h1>
            <p>学生账号当前不可访问告警管理页面，也不会发起后台告警接口调用。</p>
          </div>
        </section>
        <Alert
          type="warning"
          message="该页面仅对管理员和教师开放"
          description={`当前角色：${session.user.role}；数据范围：${scope_description}`}
          showIcon
        />
      </section>
    );
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 告警管理</div>
          <h1>告警都在这里</h1>
          <p>统一查看业务告警与系统健康告警。</p>
        </div>
      </section>

      {error ? <Alert type="error" message="告警管理异常" description={error} showIcon /> : null}
      {!can_ack_business_alerts ? (
        <Alert
          type="info"
          message="当前角色为只读模式"
          description={`当前数据范围：${scope_description}`}
          showIcon
        />
      ) : null}

      <Tabs
        activeKey={active_tab}
        onChange={(key) => set_search_params({ tab: key })}
        items={[
          {
            key: 'business',
            label: '业务告警',
            children: (
              <Space direction="vertical" size="large" style={{ width: '100%' }}>
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
                  <Button type="primary" onClick={() => void ack_batch()} loading={action_loading} disabled={selected_ids.length === 0 || !can_ack_business_alerts}>
                    批量确认
                  </Button>
                </Space>

                <section className="metric_grid">
                  <div className="panel_surface metric_card"><Statistic title="当前结果数" value={business_summary.total} /></div>
                  <div className="panel_surface metric_card"><Statistic title="未确认" value={business_summary.open} /></div>
                  <div className="panel_surface metric_card"><Statistic title="严重告警" value={business_summary.critical} /></div>
                  <div className="panel_surface metric_card"><Statistic title="已选择" value={business_summary.selected} suffix={device_id ? `/${device_id}` : ''} /></div>
                </section>

                <div className="panel_surface">
                  <Table
                    rowKey="id"
                    loading={loading && active_tab === 'business'}
                    dataSource={business_alerts}
                    columns={business_columns}
                    rowSelection={{
                      selectedRowKeys: selected_ids,
                      onChange: (keys) => set_selected_ids(keys as number[]),
                      getCheckboxProps: (record) => ({ disabled: record.is_ack || !can_ack_business_alerts })
                    }}
                    pagination={{ pageSize: 10 }}
                  />
                </div>
              </Space>
            )
          },
          ...(can_manage_ops_alerts
            ? [
                {
                  key: 'ops',
                  label: '系统健康告警',
                  children: (
                    <Space direction="vertical" size="large" style={{ width: '100%' }}>
                      <Space wrap>
                        <Select
                          value={ops_status_filter}
                          onChange={(value) => set_ops_status_filter(value)}
                          options={[
                            { value: 'open', label: '仅打开' },
                            { value: 'closed', label: '仅关闭' }
                          ]}
                          style={{ minWidth: 160 }}
                        />
                        <Select
                          allowClear
                          placeholder="按级别筛选"
                          value={ops_severity_filter}
                          onChange={(value) => set_ops_severity_filter(value)}
                          options={[
                            { value: 'info', label: 'info' },
                            { value: 'warning', label: 'warning' },
                            { value: 'critical', label: 'critical' }
                          ]}
                          style={{ minWidth: 160 }}
                        />
                        <Select
                          allowClear
                          placeholder="按模块筛选"
                          value={ops_module_filter}
                          onChange={(value) => set_ops_module_filter(value)}
                          options={ops_module_options}
                          style={{ minWidth: 220 }}
                        />
                        <Button
                          type="primary"
                          onClick={() => void close_selected_ops_alerts()}
                          loading={action_loading}
                          disabled={selected_ops_ids.length === 0}
                        >
                          批量关闭
                        </Button>
                      </Space>

                      <section className="metric_grid">
                        <div className="panel_surface metric_card"><Statistic title="当前结果数" value={ops_summary.total} /></div>
                        <div className="panel_surface metric_card"><Statistic title="打开告警" value={ops_summary.open} /></div>
                        <div className="panel_surface metric_card"><Statistic title="严重告警" value={ops_summary.critical} /></div>
                        <div className="panel_surface metric_card"><Statistic title="已选择" value={ops_summary.selected} suffix={`/ ${ops_summary.module_count} 模块`} /></div>
                      </section>

                      <div className="panel_surface">
                        <Table
                          rowKey="id"
                          loading={loading && active_tab === 'ops'}
                          dataSource={ops_alerts}
                          columns={ops_columns}
                          rowSelection={{
                            selectedRowKeys: selected_ops_ids,
                            onChange: (keys) => set_selected_ops_ids(keys as number[]),
                            getCheckboxProps: (record) => ({ disabled: record.status !== 'open' })
                          }}
                          pagination={{ pageSize: 10 }}
                        />
                      </div>
                    </Space>
                  )
                }
              ]
            : [])
        ]}
      />
    </section>
  );
}
