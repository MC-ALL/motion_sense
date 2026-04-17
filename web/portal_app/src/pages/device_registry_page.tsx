import { useEffect, useMemo, useState } from 'react';

import {
  Alert,
  Button,
  Collapse,
  Form,
  Input,
  Modal,
  Popover,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  type TableProps
} from 'antd';
import type { AxiosError } from 'axios';
import { QuestionCircleOutlined } from '@ant-design/icons';

import {
  create_device_registration,
  delete_device_registration,
  fetch_devices,
  update_device_registration
} from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { use_auth_store } from '../store/auth_store';
import type {
  DeviceRegistrationRequest,
  DeviceRegistrationUpdateRequest,
  DeviceRegistryType,
  DeviceSummary
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

type DeviceFormValues = {
  gym_id: string;
  device_type: DeviceRegistryType;
  device_id: string;
  gateway_id?: string;
  display_name?: string;
  location?: string;
  metadata_json: string;
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

export function DeviceRegistryPage() {
  const session = use_auth_store((state) => state.session);

  const [loading, set_loading] = useState(true);
  const [submitting, set_submitting] = useState(false);
  const [error, set_error] = useState<string | null>(null);
  const [devices, set_devices] = useState<DeviceSummary[]>([]);
  const [type_filter, set_type_filter] = useState<'all' | DeviceRegistryType>('all');
  const [create_open, set_create_open] = useState(false);
  const [edit_target, set_edit_target] = useState<DeviceSummary | null>(null);
  const [create_form] = Form.useForm<DeviceFormValues>();
  const [edit_form] = Form.useForm<DeviceFormValues>();
  const create_device_type = Form.useWatch('device_type', create_form) as DeviceRegistryType | undefined;
  const edit_device_type = Form.useWatch('device_type', edit_form) as DeviceRegistryType | undefined;

  async function load_devices() {
    set_loading(true);
    set_error(null);
    try {
      const response = await fetch_devices();
      set_devices(response);
    } catch (load_error) {
      set_error(describe_error(load_error, '设备注册列表加载失败'));
    } finally {
      set_loading(false);
    }
  }

  useEffect(() => {
    if (session?.user.role === 'admin') {
      void load_devices();
      return;
    }
    set_loading(false);
    set_devices([]);
  }, [session?.user.role]);

  const filtered_devices = useMemo(() => {
    if (type_filter === 'all') {
      return devices;
    }
    return devices.filter((item) => item.device_type === type_filter);
  }, [devices, type_filter]);

  const columns = useMemo<TableProps<DeviceSummary>['columns']>(
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
        title: '状态',
        key: 'status',
        render: (_, record) => (
          <Space wrap>
            <Tag color={record.online ? 'green' : 'default'}>{record.online ? 'online' : 'offline'}</Tag>
            <Tag>{record.status}</Tag>
          </Space>
        )
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

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 设备注册"
        title="登录后可管理设备注册表"
        description="设备注册页只在登录后访问后台设备管理接口；当前未登录，因此不会发起注册表查询。"
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
      set_error(describe_error(submit_error, '创建设备失败'));
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
      set_error(describe_error(submit_error, '更新设备失败'));
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
      set_error(describe_error(submit_error, '删除设备失败'));
    } finally {
      set_submitting(false);
    }
  }

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 设备注册"
        title="登录后可管理设备注册信息"
        description="当前页面仅允许后台管理员访问，未登录时不会发起设备注册接口调用。"
      />
    );
  }

  if (session.user.role !== 'admin') {
    return (
      <section className="page_shell">
        <section className="hero_banner compact_hero_banner">
          <div>
            <div className="eyebrow">06 网页端 / 设备注册</div>
            <h1>当前账号没有设备注册权限</h1>
            <p>当前仅 <code>admin</code> 角色允许写入 <code>/api/v1/devices</code>。</p>
          </div>
        </section>
        <Alert type="error" message="需要管理员权限" description={`当前角色：${session.user.role}`} showIcon />
      </section>
    );
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 设备注册</div>
          <h1>设备都在这里</h1>
          <p>统一管理设备注册与元数据维护。</p>
        </div>
      </section>

      {error ? <Alert type="error" message="设备注册异常" description={error} showIcon /> : null}

      <div className="panel_surface full_width_panel">
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
            <Button onClick={() => void load_devices()} loading={loading || submitting}>
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
                <Space direction="vertical" size="small" style={{ maxWidth: 320 }}>
                  <span>
                    非网关设备必须绑定所属网关；网关设备默认使用自己的 <code>device_id</code> 作为 <code>gateway_id</code>。
                  </span>
                  <span>
                    <code>metadata</code> 采用 JSON 对象编辑，提交前会做语法校验。
                  </span>
                  <span>
                    列表同时展示注册元数据和最新在线状态；未上报过的设备会显示为 <code>registered / offline</code>。
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
            columns={columns}
            pagination={{ pageSize: 10 }}
            scroll={{ x: 1240 }}
          />
        )}
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
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="device_type" label="设备类型" rules={[{ required: true, message: '请选择设备类型' }]}> 
            <Select options={device_type_options} />
          </Form.Item>
          <Form.Item name="device_id" label="设备 ID" rules={[{ required: true, message: '请输入设备 ID' }]}> 
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="gateway_id"
            label="所属网关 ID"
            rules={create_device_type === 'gateway' ? [] : [{ required: true, message: '非网关设备必须填写所属网关 ID' }]}
            extra={create_device_type === 'gateway' ? '网关设备会自动回填为自己的 device_id' : '例如 gw-001'}
          >
            <Input autoComplete="off" disabled={create_device_type === 'gateway'} />
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
            <Input autoComplete="off" disabled={edit_device_type === 'gateway'} />
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
    </section>
  );
}
