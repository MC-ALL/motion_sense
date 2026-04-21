import { useEffect, useMemo, useState } from 'react';

import {
  AutoComplete,
  Button,
  Collapse,
  Form,
  Input,
  Modal,
  Popconfirm,
  Popover,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  type TableProps
} from 'antd';
import type { AxiosError } from 'axios';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  create_device_registration,
  create_user_wristband_binding,
  delete_device_registration,
  end_user_wristband_binding,
  fetch_devices,
  fetch_user_wristband_binding_overview,
  fetch_users,
  update_device_registration
} from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { DeviceConnectivityTag, DeviceRuntimeStatusStack } from '../components/device_ui';
import { PageNotice } from '../components/notice_card';
import { page_error_fallbacks, page_notice_titles } from '../ui/message_catalog';
import { use_auth_store } from '../store/auth_store';
import type {
  DeviceRegistrationRequest,
  DeviceRegistrationUpdateRequest,
  DeviceRegistryType,
  DeviceSummary,
  UserSummary,
  UserWristbandBindingSummary
} from '../types/backend';
import { format_time } from '../utils/time';

const device_type_options: Array<{ label: string; value: DeviceRegistryType }> = [
  { label: '手环', value: 'wristband' },
  { label: '器材', value: 'equipment' },
  { label: '环境节点', value: 'env' },
  { label: '网关', value: 'gateway' }
];

const device_type_filter_options = [
  { label: '全部类型', value: 'all' },
  ...device_type_options
];

const device_management_tabs = [
  { key: 'devices', label: '设备清单' },
  { key: 'wristband-bindings', label: '手环绑定' },
  { key: 'binding-history', label: '绑定历史' }
] as const;

type DeviceManagementTabKey = (typeof device_management_tabs)[number]['key'];

type DeviceFormValues = {
  gym_id: string;
  device_type: DeviceRegistryType;
  device_id: string;
  gateway_id?: string;
  display_name?: string;
  location?: string;
  metadata_json: string;
};

type BindingFormValues = {
  username: string;
  wristband_id: string;
  note?: string;
};

function parse_metadata_json(raw: string): Record<string, unknown> {
  const text = raw.trim();
  if (!text) {
    return {};
  }
  const parsed = JSON.parse(text) as unknown;
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('metadata 必须是 JSON 对象');
  }
  return parsed as Record<string, unknown>;
}

function describe_error(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const detail = (error as AxiosError<{ detail?: string }>).response?.data?.detail;
    if (typeof detail === 'string' && detail) {
      return detail;
    }
  }
  return error instanceof Error ? error.message : fallback;
}

function build_device_form_values(device?: DeviceSummary | null): DeviceFormValues {
  return {
    gym_id: device?.gym_id ?? '',
    device_type: (device?.device_type as DeviceRegistryType | undefined) ?? 'equipment',
    device_id: device?.device_id ?? '',
    gateway_id: device?.gateway_id ?? '',
    display_name: device?.display_name ?? '',
    location: device?.location ?? '',
    metadata_json: JSON.stringify(device?.metadata ?? {}, null, 2)
  };
}

function build_binding_status_tag(binding: UserWristbandBindingSummary) {
  return <Tag color={binding.is_active ? 'green' : 'default'}>{binding.is_active ? '已绑定' : '已解绑'}</Tag>;
}

function build_device_id_suggestions(
  device_type: DeviceRegistryType | undefined,
  devices: DeviceSummary[],
) {
  const prefix_map: Record<DeviceRegistryType, string> = {
    wristband: 'wb',
    equipment: 'eq',
    env: 'env',
    gateway: 'gw'
  };
  const prefix = device_type ? prefix_map[device_type] : 'dev';
  const same_type_ids = devices
    .filter((item) => item.device_type === device_type)
    .map((item) => item.device_id)
    .sort((left, right) => left.localeCompare(right));
  const suggestions = new Set<string>();
  for (const item of same_type_ids.slice(-5)) {
    suggestions.add(item);
  }
  let next_numeric_suffix = same_type_ids.length + 1;
  while (suggestions.size < 8) {
    suggestions.add(`${prefix}-${String(next_numeric_suffix).padStart(3, '0')}`);
    next_numeric_suffix += 1;
  }
  return Array.from(suggestions).map((value) => ({ value }));
}

function initial_tab(search_params: URLSearchParams): DeviceManagementTabKey {
  const query_tab = search_params.get('tab');
  if (query_tab === 'wristband-bindings' || query_tab === 'binding-history') {
    return query_tab;
  }
  return 'devices';
}

export function DeviceRegistryPage() {
  const navigate = useNavigate();
  const [search_params, set_search_params] = useSearchParams();
  const session = use_auth_store((state) => state.session);

  const [active_tab, set_active_tab] = useState<DeviceManagementTabKey>(() => initial_tab(search_params));
  const [loading, set_loading] = useState(true);
  const [submitting, set_submitting] = useState(false);
  const [error, set_error] = useState<string | null>(null);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [users, set_users] = useState<UserSummary[]>([]);
  const [active_bindings, set_active_bindings] = useState<UserWristbandBindingSummary[]>([]);
  const [binding_history, set_binding_history] = useState<UserWristbandBindingSummary[]>([]);
  const [type_filter, set_type_filter] = useState<'all' | DeviceRegistryType>('all');
  const [binding_username_filter, set_binding_username_filter] = useState(search_params.get('username') ?? '');
  const [binding_wristband_filter, set_binding_wristband_filter] = useState(search_params.get('wristband_id') ?? '');
  const [binding_gym_filter, set_binding_gym_filter] = useState(search_params.get('gym_id') ?? '');
  const [create_open, set_create_open] = useState(false);
  const [edit_target, set_edit_target] = useState<DeviceSummary | null>(null);
  const [binding_create_open, set_binding_create_open] = useState(false);
  const [unbind_target, set_unbind_target] = useState<UserWristbandBindingSummary | null>(null);
  const [unbind_note, set_unbind_note] = useState('');
  const [create_form] = Form.useForm<DeviceFormValues>();
  const [edit_form] = Form.useForm<DeviceFormValues>();
  const [binding_form] = Form.useForm<BindingFormValues>();
  const create_device_type = Form.useWatch('device_type', create_form) as DeviceRegistryType | undefined;
  const edit_device_type = Form.useWatch('device_type', edit_form) as DeviceRegistryType | undefined;

  useEffect(() => {
    const next_tab = initial_tab(search_params);
    set_active_tab(next_tab);
    set_binding_username_filter(search_params.get('username') ?? '');
    set_binding_wristband_filter(search_params.get('wristband_id') ?? '');
    set_binding_gym_filter(search_params.get('gym_id') ?? '');
  }, [search_params]);

  const student_users = useMemo(() => users.filter((item) => item.role === 'student'), [users]);
  const wristband_devices = useMemo(() => devices.filter((item) => item.device_type === 'wristband'), [devices]);
  const active_binding_usernames = useMemo(() => new Set(active_bindings.map((item) => item.username)), [active_bindings]);
  const active_binding_wristbands = useMemo(() => new Set(active_bindings.map((item) => item.wristband_id)), [active_bindings]);
  const available_students = useMemo(
    () => student_users.filter((item) => !active_binding_usernames.has(item.username)),
    [active_binding_usernames, student_users]
  );
  const available_wristbands = useMemo(
    () => wristband_devices.filter((item) => !active_binding_wristbands.has(item.device_id)),
    [active_binding_wristbands, wristband_devices]
  );
  const known_gym_ids = useMemo(
    () =>
      Array.from(
        new Set([
          ...devices.map((item) => item.gym_id),
          ...users.flatMap((item) => item.gym_ids),
          ...active_bindings.map((item) => item.gym_id),
          ...binding_history.map((item) => item.gym_id)
        ].filter((item) => item && item.trim()))
      )
        .sort((left, right) => left.localeCompare(right))
        .map((value) => ({ value })),
    [active_bindings, binding_history, devices, users]
  );
  const known_gateway_ids = useMemo(
    () =>
      Array.from(
        new Set([
          ...devices.filter((item) => item.device_type === 'gateway').map((item) => item.device_id),
          ...devices.map((item) => item.gateway_id).filter((item): item is string => Boolean(item && item.trim()))
        ])
      )
        .sort((left, right) => left.localeCompare(right))
        .map((value) => ({ value })),
    [devices]
  );
  const create_device_id_options = useMemo(
    () => build_device_id_suggestions(create_device_type, devices),
    [create_device_type, devices]
  );

  async function load_devices() {
    const response = await fetch_devices();
    set_devices(response);
  }

  async function load_users() {
    const response = await fetch_users();
    set_users(response);
  }

  async function load_binding_records() {
    const overview = await fetch_user_wristband_binding_overview({
      active_limit: 500,
      history_limit: 1000,
    });
    set_active_bindings(overview.active_bindings);
    set_binding_history(overview.binding_history);
  }

  async function load_management_data() {
    set_loading(true);
    set_error(null);
    try {
      await Promise.all([load_devices(), load_users(), load_binding_records()]);
    } catch (load_error) {
      set_error(
        describe_error(
          load_error,
          active_tab === 'devices'
            ? page_error_fallbacks.device_registry_list_load_failed
            : page_error_fallbacks.device_binding_list_load_failed
        )
      );
    } finally {
      set_loading(false);
    }
  }

  useEffect(() => {
    if (session?.user.role === 'admin') {
      void load_management_data();
      return;
    }
    setLoadingDefaults();
  }, [session?.user.role]);

  function setLoadingDefaults() {
    set_loading(false);
    set_devices([]);
    set_users([]);
    set_active_bindings([]);
    set_binding_history([]);
  }

  const filtered_devices = useMemo(() => {
    if (type_filter === 'all') {
      return devices;
    }
    return devices.filter((item) => item.device_type === type_filter);
  }, [devices, type_filter]);

  const filtered_active_bindings = useMemo(() => {
    return active_bindings.filter((item) => {
      if (binding_username_filter && item.username !== binding_username_filter) {
        return false;
      }
      if (binding_wristband_filter && item.wristband_id !== binding_wristband_filter) {
        return false;
      }
      if (binding_gym_filter && item.gym_id !== binding_gym_filter) {
        return false;
      }
      return true;
    });
  }, [active_bindings, binding_gym_filter, binding_username_filter, binding_wristband_filter]);

  const filtered_binding_history = useMemo(() => {
    return binding_history.filter((item) => {
      if (binding_username_filter && item.username !== binding_username_filter) {
        return false;
      }
      if (binding_wristband_filter && item.wristband_id !== binding_wristband_filter) {
        return false;
      }
      if (binding_gym_filter && item.gym_id !== binding_gym_filter) {
        return false;
      }
      return true;
    });
  }, [binding_history, binding_gym_filter, binding_username_filter, binding_wristband_filter]);

  const device_columns = useMemo<TableProps<DeviceSummary>['columns']>(
    () => [
      {
        title: '设备 ID',
        dataIndex: 'device_id',
        key: 'device_id'
      },
      {
        title: '类型',
        dataIndex: 'device_type',
        key: 'device_type',
        render: (value: string) => <Tag color="blue">{value}</Tag>
      },
      {
        title: '场馆',
        dataIndex: 'gym_id',
        key: 'gym_id'
      },
      {
        title: '网关',
        dataIndex: 'gateway_id',
        key: 'gateway_id',
        render: (value?: string | null) => value ?? '--'
      },
      {
        title: '显示名称',
        dataIndex: 'display_name',
        key: 'display_name',
        render: (value?: string | null) => value ?? '--'
      },
      {
        title: '位置',
        dataIndex: 'location',
        key: 'location',
        render: (value?: string | null) => value ?? '--'
      },
      {
        title: '连通性',
        key: 'connectivity',
        render: (_, record) => <DeviceConnectivityTag online={record.online} />
      },
      {
        title: '设备状态',
        key: 'device_status',
        render: (_, record) => <DeviceRuntimeStatusStack status={record.status} />
      },
      {
        title: '最近更新',
        dataIndex: 'updated_at',
        key: 'updated_at',
        render: (value?: string | null) => (value ? format_time(value) : '--')
      },
      {
        title: '操作',
        key: 'actions',
        render: (_, record) => (
          <Space wrap>
            <Button
              size="small"
              onClick={() => {
                edit_form.setFieldsValue(build_device_form_values(record));
                set_edit_target(record);
              }}
            >
              编辑
            </Button>
            <Popconfirm
              title={`确认注销设备 ${record.device_id}？`}
              description="设备注销后将从后台注册列表中移除。"
              okText="删除"
              cancelText="取消"
              onConfirm={() => void handle_delete(record.device_id)}
            >
              <Button size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        )
      }
    ],
    [edit_form]
  );

  const current_binding_columns = useMemo<TableProps<UserWristbandBindingSummary>['columns']>(
    () => [
      {
        title: '手环设备',
        dataIndex: 'wristband_id',
        key: 'wristband_id',
        render: (value: string) => <strong>{value}</strong>
      },
      {
        title: '学生账号',
        dataIndex: 'username',
        key: 'username',
        render: (value: string) => <Button type="link" size="small" onClick={() => navigate(`/training-archive/${value}`)}>{value}</Button>
      },
      {
        title: '场馆',
        dataIndex: 'gym_id',
        key: 'gym_id'
      },
      {
        title: '绑定时间',
        dataIndex: 'bound_at',
        key: 'bound_at',
        render: (value: string) => format_time(value)
      },
      {
        title: '来源',
        dataIndex: 'source',
        key: 'source',
        render: (value: string) => <Tag>{value}</Tag>
      },
      {
        title: '备注',
        dataIndex: 'note',
        key: 'note',
        render: (value?: string | null) => value ?? '--'
      },
      {
        title: '状态',
        key: 'status',
        render: (_, record) => build_binding_status_tag(record)
      },
      {
        title: '操作',
        key: 'actions',
        render: (_, record) => (
          <Space wrap>
            <Button
              size="small"
              onClick={() => {
                set_unbind_note('');
                set_unbind_target(record);
              }}
            >
              解绑
            </Button>
            <Button size="small" onClick={() => navigate(`/training-archive/${record.username}`)}>
              查看档案
            </Button>
          </Space>
        )
      }
    ],
    [navigate]
  );

  const binding_history_columns = useMemo<TableProps<UserWristbandBindingSummary>['columns']>(
    () => [
      {
        title: '手环设备',
        dataIndex: 'wristband_id',
        key: 'wristband_id'
      },
      {
        title: '学生账号',
        dataIndex: 'username',
        key: 'username'
      },
      {
        title: '场馆',
        dataIndex: 'gym_id',
        key: 'gym_id'
      },
      {
        title: '状态',
        key: 'status',
        render: (_, record) => build_binding_status_tag(record)
      },
      {
        title: '绑定时间',
        dataIndex: 'bound_at',
        key: 'bound_at',
        render: (value: string) => format_time(value)
      },
      {
        title: '解绑时间',
        dataIndex: 'unbound_at',
        key: 'unbound_at',
        render: (value?: string | null) => (value ? format_time(value) : '--')
      },
      {
        title: '来源',
        dataIndex: 'source',
        key: 'source',
        render: (value: string) => <Tag>{value}</Tag>
      },
      {
        title: '备注',
        dataIndex: 'note',
        key: 'note',
        render: (value?: string | null) => value ?? '--'
      }
    ],
    []
  );

  function sync_search(next: {
    tab?: DeviceManagementTabKey;
    username?: string;
    wristband_id?: string;
    gym_id?: string;
  }) {
    const params = new URLSearchParams(search_params);
    if (next.tab) {
      params.set('tab', next.tab);
    }
    const mappings = [
      ['username', next.username],
      ['wristband_id', next.wristband_id],
      ['gym_id', next.gym_id]
    ] as const;
    for (const [key, value] of mappings) {
      if (typeof value === 'string' && value.trim()) {
        params.set(key, value.trim());
      } else {
        params.delete(key);
      }
    }
    set_search_params(params, { replace: true });
  }

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 设备管理"
        title="登录后可管理设备与手环绑定"
        description="设备管理页只在登录后访问后台设备、账号与手环绑定接口；当前未登录，因此不会发起这些请求。"
      />
    );
  }

  async function handle_create(values: DeviceFormValues) {
    set_submitting(true);
    set_error(null);
    try {
      const metadata = parse_metadata_json(values.metadata_json);
      const payload: DeviceRegistrationRequest = {
        gym_id: values.gym_id.trim(),
        device_type: values.device_type,
        device_id: values.device_id.trim(),
        display_name: values.display_name?.trim() || null,
        location: values.location?.trim() || null,
        metadata
      };
      if (values.device_type !== 'gateway') {
        payload.gateway_id = values.gateway_id?.trim() || null;
      }
      await create_device_registration(payload);
      set_create_open(false);
      create_form.setFieldsValue(build_device_form_values(null));
      await load_devices();
    } catch (submit_error) {
      set_error(describe_error(submit_error, page_error_fallbacks.device_registry_create_failed));
    } finally {
      set_submitting(false);
    }
  }

  async function handle_edit(values: DeviceFormValues) {
    if (!edit_target) {
      return;
    }
    set_submitting(true);
    set_error(null);
    try {
      const metadata = parse_metadata_json(values.metadata_json);
      const payload: DeviceRegistrationUpdateRequest = {
        display_name: values.display_name?.trim() || null,
        location: values.location?.trim() || null,
        metadata
      };
      if (edit_target.device_type !== 'gateway') {
        payload.gateway_id = values.gateway_id?.trim() || null;
      }
      await update_device_registration(edit_target.device_id, payload);
      set_edit_target(null);
      edit_form.resetFields();
      await load_devices();
    } catch (submit_error) {
      set_error(describe_error(submit_error, page_error_fallbacks.device_registry_update_failed));
    } finally {
      set_submitting(false);
    }
  }

  async function handle_delete(device_id: string) {
    set_submitting(true);
    set_error(null);
    try {
      await delete_device_registration(device_id);
      await load_devices();
    } catch (submit_error) {
      set_error(describe_error(submit_error, page_error_fallbacks.device_registry_delete_failed));
    } finally {
      set_submitting(false);
    }
  }

  async function handle_binding_create(values: BindingFormValues) {
    const selected_wristband = wristband_devices.find((item) => item.device_id === values.wristband_id);
    if (!selected_wristband) {
      set_error('选中的手环设备不存在');
      return;
    }
    set_submitting(true);
    set_error(null);
    try {
      await create_user_wristband_binding({
        username: values.username,
        wristband_id: values.wristband_id,
        gym_id: selected_wristband.gym_id,
        source: 'manual',
        note: values.note?.trim() || null
      });
      set_binding_create_open(false);
      binding_form.resetFields();
      await load_binding_records();
    } catch (submit_error) {
      set_error(describe_error(submit_error, page_error_fallbacks.wristband_bind_failed));
    } finally {
      set_submitting(false);
    }
  }

  async function handle_unbind() {
    if (!unbind_target) {
      return;
    }
    set_submitting(true);
    set_error(null);
    try {
      await end_user_wristband_binding(unbind_target.id, {
        note: unbind_note.trim() || null
      });
      set_unbind_target(null);
      set_unbind_note('');
      await load_binding_records();
    } catch (submit_error) {
      set_error(describe_error(submit_error, page_error_fallbacks.wristband_unbind_failed));
    } finally {
      set_submitting(false);
    }
  }

  if (session.user.role !== 'admin') {
    return (
      <section className="page_shell">
        <section className="hero_banner compact_hero_banner">
          <div>
            <div className="eyebrow">06 网页端 / 设备管理</div>
            <h1>当前账号没有设备管理权限</h1>
            <p>当前仅 <code>admin</code> 角色允许访问设备注册、手环绑定与绑定历史管理功能。</p>
          </div>
        </section>
        <PageNotice tone="warning" title={page_notice_titles.admin_required} description={`当前角色：${session.user.role}`} />
      </section>
    );
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 设备管理</div>
          <h1>设备与手环绑定都在这里</h1>
          <p>统一管理设备注册、当前绑定关系和绑定历史；训练档案页只负责展示结果，不再承担绑定写操作。</p>
        </div>
      </section>

      {error ? (
        <PageNotice
          tone="error"
          title={active_tab === 'devices' ? page_notice_titles.device_registry_error : page_notice_titles.device_binding_error}
          description={error}
        />
      ) : null}

      <div className="panel_surface full_width_panel">
        <Tabs
          activeKey={active_tab}
          onChange={(value) => sync_search({ tab: value as DeviceManagementTabKey, username: binding_username_filter, wristband_id: binding_wristband_filter, gym_id: binding_gym_filter })}
          items={device_management_tabs.map((item) => ({ key: item.key, label: item.label }))}
        />

        {active_tab === 'devices' ? (
          <>
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">设备清单</div>
                <h3>当前注册与在线快照</h3>
              </div>
              <Space wrap>
                <Select
                  value={type_filter}
                  options={device_type_filter_options}
                  onChange={(value) => set_type_filter(value as 'all' | DeviceRegistryType)}
                  style={{ minWidth: 160 }}
                />
                <Button onClick={() => void load_management_data()} loading={loading || submitting}>
                  刷新列表
                </Button>
                <Button
                  type="primary"
                  onClick={() => {
                    create_form.setFieldsValue(build_device_form_values(null));
                    set_create_open(true);
                  }}
                >
                  注册设备
                </Button>
                <Popover
                  title="维护约束"
                  content={
                    <Space direction="vertical" size="small" style={{ maxWidth: 360 }}>
                      <span>
                        非网关设备必须绑定所属网关；网关设备默认使用自己的 <code>device_id</code> 作为 <code>gateway_id</code>。
                      </span>
                      <span>
                        <code>metadata</code> 采用 JSON 对象编辑，提交前会做语法校验。
                      </span>
                      <span>
                        “连通性”表示当前网络连通快照；“设备状态”表示注册后最近一次业务状态。新注册但尚未上报的设备会显示为 <code>未连通</code> + <code>待上报</code>。
                      </span>
                    </Space>
                  }
                >
                  <Button type="text" icon={<QuestionCircleOutlined />} className="panel_hint_button">
                    维护约束
                  </Button>
                </Popover>
              </Space>
            </div>
            {loading ? (
              <div className="loading_surface"><Spin size="large" /></div>
            ) : (
              <Table<DeviceSummary>
                rowKey="device_id"
                dataSource={filtered_devices}
                columns={device_columns}
                pagination={{ pageSize: 10 }}
                scroll={{ x: 1240 }}
              />
            )}
          </>
        ) : null}

        {active_tab === 'wristband-bindings' ? (
          <>
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">手环绑定</div>
                <h3>当前激活绑定</h3>
              </div>
              <Space wrap>
                <Select
                  allowClear
                  placeholder="按学生筛选"
                  value={binding_username_filter || undefined}
                  style={{ minWidth: 180 }}
                  options={student_users.map((item) => ({ value: item.username, label: item.username }))}
                  onChange={(value) => sync_search({ tab: 'wristband-bindings', username: value ?? '', wristband_id: binding_wristband_filter, gym_id: binding_gym_filter })}
                />
                <Select
                  allowClear
                  placeholder="按手环筛选"
                  value={binding_wristband_filter || undefined}
                  style={{ minWidth: 220 }}
                  options={wristband_devices.map((item) => ({ value: item.device_id, label: `${item.device_id} · ${item.gym_id}` }))}
                  onChange={(value) => sync_search({ tab: 'wristband-bindings', username: binding_username_filter, wristband_id: value ?? '', gym_id: binding_gym_filter })}
                />
                <Select
                  allowClear
                  placeholder="按场馆筛选"
                  value={binding_gym_filter || undefined}
                  style={{ minWidth: 180 }}
                  options={Array.from(new Set(wristband_devices.map((item) => item.gym_id))).map((gym_id) => ({ value: gym_id, label: gym_id }))}
                  onChange={(value) => sync_search({ tab: 'wristband-bindings', username: binding_username_filter, wristband_id: binding_wristband_filter, gym_id: value ?? '' })}
                />
                <Button onClick={() => void load_management_data()} loading={loading || submitting}>
                  刷新
                </Button>
                <Button
                  type="primary"
                  disabled={available_students.length === 0 || available_wristbands.length === 0}
                  onClick={() => {
                    binding_form.setFieldsValue({
                      username: binding_username_filter || available_students[0]?.username || '',
                      wristband_id: binding_wristband_filter && available_wristbands.some((item) => item.device_id === binding_wristband_filter)
                        ? binding_wristband_filter
                        : available_wristbands[0]?.device_id || '',
                      note: ''
                    });
                    set_binding_create_open(true);
                  }}
                >
                  新建绑定
                </Button>
              </Space>
            </div>
            <div className="archive_notice_stack">
              <PageNotice
                tone="info"
                title="绑定规则说明"
                description="一个学生同一时刻只能有一个激活手环绑定；一个手环同一时刻也只能分配给一个学生。若需更换对象，请先解绑当前记录。"
              />
              {available_students.length === 0 ? (
                <PageNotice tone="warning" title="当前没有可分配学生" description="请先创建学生账号，或先解绑已有激活绑定。" />
              ) : null}
              {available_wristbands.length === 0 ? (
                <PageNotice tone="warning" title="当前没有可分配手环" description="请先注册 wristband 设备，或先解绑已有激活绑定。" />
              ) : null}
            </div>
            {loading ? (
              <div className="loading_surface"><Spin size="large" /></div>
            ) : (
              <Table<UserWristbandBindingSummary>
                rowKey="id"
                dataSource={filtered_active_bindings}
                columns={current_binding_columns}
                pagination={{ pageSize: 10 }}
                locale={{ emptyText: '当前没有激活中的手环绑定' }}
                scroll={{ x: 1180 }}
              />
            )}
          </>
        ) : null}

        {active_tab === 'binding-history' ? (
          <>
            <div className="panel_header compact_panel_header">
              <div>
                <div className="eyebrow">绑定历史</div>
                <h3>最近绑定变更</h3>
              </div>
              <Space wrap>
                <Select
                  allowClear
                  placeholder="按学生筛选"
                  value={binding_username_filter || undefined}
                  style={{ minWidth: 180 }}
                  options={student_users.map((item) => ({ value: item.username, label: item.username }))}
                  onChange={(value) => sync_search({ tab: 'binding-history', username: value ?? '', wristband_id: binding_wristband_filter, gym_id: binding_gym_filter })}
                />
                <Select
                  allowClear
                  placeholder="按手环筛选"
                  value={binding_wristband_filter || undefined}
                  style={{ minWidth: 220 }}
                  options={wristband_devices.map((item) => ({ value: item.device_id, label: `${item.device_id} · ${item.gym_id}` }))}
                  onChange={(value) => sync_search({ tab: 'binding-history', username: binding_username_filter, wristband_id: value ?? '', gym_id: binding_gym_filter })}
                />
                <Select
                  allowClear
                  placeholder="按场馆筛选"
                  value={binding_gym_filter || undefined}
                  style={{ minWidth: 180 }}
                  options={Array.from(new Set(wristband_devices.map((item) => item.gym_id))).map((gym_id) => ({ value: gym_id, label: gym_id }))}
                  onChange={(value) => sync_search({ tab: 'binding-history', username: binding_username_filter, wristband_id: binding_wristband_filter, gym_id: value ?? '' })}
                />
                <Button onClick={() => void load_management_data()} loading={loading || submitting}>
                  刷新
                </Button>
              </Space>
            </div>
            {loading ? (
              <div className="loading_surface"><Spin size="large" /></div>
            ) : (
              <Table<UserWristbandBindingSummary>
                rowKey="id"
                dataSource={filtered_binding_history}
                columns={binding_history_columns}
                pagination={{ pageSize: 12 }}
                locale={{ emptyText: '当前没有符合条件的绑定历史' }}
                scroll={{ x: 1180 }}
              />
            )}
          </>
        ) : null}
      </div>

      <Modal
        title="注册设备"
        open={create_open}
        onCancel={() => {
          set_create_open(false);
          create_form.resetFields();
        }}
        onOk={() => void create_form.submit()}
        confirmLoading={submitting}
        okText="创建"
        cancelText="取消"
        width={720}
      >
        <Form form={create_form} layout="vertical" onFinish={(values) => void handle_create(values)} initialValues={build_device_form_values(null)}>
          <Form.Item name="gym_id" label="场馆 ID" rules={[{ required: true, message: '请输入场馆 ID' }]}> 
            <AutoComplete options={known_gym_ids} placeholder="选择已有场馆，或直接输入新场馆 ID" filterOption />
          </Form.Item>
          <Form.Item name="device_type" label="设备类型" rules={[{ required: true, message: '请选择设备类型' }]}> 
            <Select options={device_type_options} />
          </Form.Item>
          <Form.Item name="device_id" label="设备 ID" rules={[{ required: true, message: '请输入设备 ID' }]}> 
            <AutoComplete options={create_device_id_options} placeholder="选择建议 ID，或直接输入新的设备 ID" filterOption />
          </Form.Item>
          <Form.Item
            name="gateway_id"
            label="所属网关 ID"
            rules={create_device_type === 'gateway' ? [] : [{ required: true, message: '非网关设备必须填写所属网关 ID' }]}
            extra={create_device_type === 'gateway' ? '网关设备会自动回填为自己的 device_id' : '例如 gw-001'}
          >
            <AutoComplete
              options={known_gateway_ids}
              placeholder="选择已有网关，或直接输入网关 ID"
              filterOption
              disabled={create_device_type === 'gateway'}
            />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称">
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="location" label="位置描述">
            <Input autoComplete="off" />
          </Form.Item>
          <Collapse
            className="inline_collapse"
            items={[
              {
                key: 'create-device-metadata',
                label: 'metadata（JSON）',
                children: (
                  <Form.Item name="metadata_json" noStyle rules={[{ required: true, message: '请输入 metadata JSON' }]}>
                    <Input.TextArea rows={8} spellCheck={false} />
                  </Form.Item>
                )
              }
            ]}
          />
        </Form>
      </Modal>

      <Modal
        title={edit_target ? `编辑设备 ${edit_target.device_id}` : '编辑设备'}
        open={Boolean(edit_target)}
        onCancel={() => {
          set_edit_target(null);
          edit_form.resetFields();
        }}
        onOk={() => void edit_form.submit()}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
        width={720}
      >
        <Form form={edit_form} layout="vertical" onFinish={(values) => void handle_edit(values)}>
          <Form.Item name="gym_id" label="场馆 ID">
            <Input disabled />
          </Form.Item>
          <Form.Item name="device_type" label="设备类型">
            <Select options={device_type_options} disabled />
          </Form.Item>
          <Form.Item name="device_id" label="设备 ID">
            <Input disabled />
          </Form.Item>
          <Form.Item
            name="gateway_id"
            label="所属网关 ID"
            rules={edit_device_type === 'gateway' ? [] : [{ required: true, message: '非网关设备必须填写所属网关 ID' }]}
            extra={edit_device_type === 'gateway' ? '网关设备固定映射到自身 device_id' : '例如 gw-001'}
          >
            <AutoComplete
              options={known_gateway_ids}
              placeholder="选择已有网关，或直接输入网关 ID"
              filterOption
              disabled={edit_device_type === 'gateway'}
            />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称">
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="location" label="位置描述">
            <Input autoComplete="off" />
          </Form.Item>
          <Collapse
            className="inline_collapse"
            items={[
              {
                key: 'edit-device-metadata',
                label: 'metadata（JSON）',
                children: (
                  <Form.Item name="metadata_json" noStyle rules={[{ required: true, message: '请输入 metadata JSON' }]}>
                    <Input.TextArea rows={8} spellCheck={false} />
                  </Form.Item>
                )
              }
            ]}
          />
        </Form>
      </Modal>

      <Modal
        title="新建手环绑定"
        open={binding_create_open}
        onCancel={() => {
          set_binding_create_open(false);
          binding_form.resetFields();
        }}
        onOk={() => void binding_form.submit()}
        confirmLoading={submitting}
        okText="绑定"
        cancelText="取消"
        width={640}
      >
        <Form form={binding_form} layout="vertical" onFinish={(values) => void handle_binding_create(values)}>
          <Form.Item name="username" label="学生账号" rules={[{ required: true, message: '请选择学生账号' }]}> 
            <Select
              showSearch
              optionFilterProp="label"
              options={available_students.map((item) => ({ value: item.username, label: `${item.username}${item.gym_ids.length > 0 ? ` · ${item.gym_ids.join('、')}` : ''}` }))}
            />
          </Form.Item>
          <Form.Item name="wristband_id" label="手环设备" rules={[{ required: true, message: '请选择手环设备' }]}> 
            <Select
              showSearch
              optionFilterProp="label"
              options={available_wristbands.map((item) => ({ value: item.device_id, label: `${item.device_id} · ${item.gym_id}${item.display_name ? ` · ${item.display_name}` : ''}` }))}
            />
          </Form.Item>
          <Form.Item name="note" label="绑定备注">
            <Input.TextArea rows={4} maxLength={500} placeholder="例如：新学员首次入场分配手环" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={unbind_target ? `解绑 ${unbind_target.wristband_id}` : '解绑手环'}
        open={Boolean(unbind_target)}
        onCancel={() => {
          set_unbind_target(null);
          set_unbind_note('');
        }}
        onOk={() => void handle_unbind()}
        confirmLoading={submitting}
        okText="确认解绑"
        cancelText="取消"
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <PageNotice
            tone="warning"
            title="解绑后该手环会回到可分配状态"
            description={unbind_target ? `学生 ${unbind_target.username} 与手环 ${unbind_target.wristband_id} 的当前激活绑定将结束。` : undefined}
          />
          <Input.TextArea
            value={unbind_note}
            rows={4}
            maxLength={500}
            placeholder="例如：课程结束、设备回收"
            onChange={(event) => set_unbind_note(event.target.value)}
          />
        </Space>
      </Modal>
    </section>
  );
}
