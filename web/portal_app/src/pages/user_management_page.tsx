import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

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
import { QuestionCircleOutlined } from '@ant-design/icons';

import {
  create_user,
  delete_user,
  fetch_users,
  update_user
} from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { use_auth_store } from '../store/auth_store';
import type { UserCreateRequest, UserRole, UserSummary, UserUpdateRequest } from '../types/backend';
import { format_time } from '../utils/time';

const role_options: Array<{ label: string; value: UserRole }> = [
  { label: '管理员', value: 'admin' },
  { label: '教师', value: 'teacher' },
  { label: '学生', value: 'student' }
];

type UserFormValues = {
  username: string;
  password?: string;
  role: UserRole;
  gym_ids: string;
  device_ids: string;
};

function parse_scope_input(value?: string): string[] {
  if (!value) {
    return [];
  }

  return value
    .split(/[\s,，]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function format_scope_input(items?: string[]): string {
  return (items ?? []).join('\n');
}

function render_scope_tags(items: string[], empty_text: string) {
  if (items.length === 0) {
    return <span>{empty_text}</span>;
  }

  return (
    <Space size={[4, 4]} wrap>
      {items.map((item) => (
        <Tag key={item}>{item}</Tag>
      ))}
    </Space>
  );
}

export function UserManagementPage() {
  const navigate = useNavigate();
  const session = use_auth_store((state) => state.session);

  const [loading, set_loading] = useState(true);
  const [submitting, set_submitting] = useState(false);
  const [error, set_error] = useState<string | null>(null);
  const [users, set_users] = useState<UserSummary[]>([]);
  const [create_open, set_create_open] = useState(false);
  const [edit_target, set_edit_target] = useState<UserSummary | null>(null);
  const [create_form] = Form.useForm<UserFormValues>();
  const [edit_form] = Form.useForm<UserFormValues>();

  async function load_users() {
    set_loading(true);
    set_error(null);
    try {
      const response = await fetch_users();
      set_users(response);
    } catch (load_error) {
      set_error(load_error instanceof Error ? load_error.message : '用户列表加载失败');
    } finally {
      set_loading(false);
    }
  }

  useEffect(() => {
    if (session?.user.role === 'admin') {
      void load_users();
      return;
    }
    set_loading(false);
    set_users([]);
  }, [session?.user.role]);

  const columns = useMemo<TableProps<UserSummary>['columns']>(
    () => [
      {
        title: '用户名',
        dataIndex: 'username',
        key: 'username'
      },
      {
        title: '角色',
        dataIndex: 'role',
        key: 'role',
        render: (role: UserRole) => <Tag color={role === 'admin' ? 'gold' : role === 'teacher' ? 'blue' : 'green'}>{role}</Tag>
      },
      {
        title: '场馆归属',
        dataIndex: 'gym_ids',
        key: 'gym_ids',
        render: (gym_ids: string[]) => render_scope_tags(gym_ids, '仅设备归属生效')
      },
      {
        title: '设备归属',
        dataIndex: 'device_ids',
        key: 'device_ids',
        render: (device_ids: string[]) => render_scope_tags(device_ids, '未绑定具体设备')
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        render: (value?: string | null) => (value ? format_time(value) : '--')
      },
      {
        title: '更新时间',
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
                edit_form.setFieldsValue({
                  username: record.username,
                  role: record.role,
                  password: '',
                  gym_ids: format_scope_input(record.gym_ids),
                  device_ids: format_scope_input(record.device_ids)
                });
                set_edit_target(record);
              }}
            >
              编辑
            </Button>
            <Button size="small" onClick={() => navigate(`/training-archive/${record.username}`)}>
              训练档案
            </Button>
            <Popconfirm
              title={`确认删除用户 ${record.username}？`}
              description="删除后该账号将无法继续登录后台。"
              okText="删除"
              cancelText="取消"
              onConfirm={() => void handle_delete(record.username)}
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

  async function handle_create(values: UserFormValues) {
    set_submitting(true);
    set_error(null);
    try {
      const payload: UserCreateRequest = {
        username: values.username,
        password: values.password ?? '',
        role: values.role,
        gym_ids: parse_scope_input(values.gym_ids),
        device_ids: parse_scope_input(values.device_ids)
      };
      await create_user(payload);
      set_create_open(false);
      create_form.resetFields();
      await load_users();
    } catch (submit_error) {
      set_error(submit_error instanceof Error ? submit_error.message : '创建用户失败');
    } finally {
      set_submitting(false);
    }
  }

  async function handle_edit(values: UserFormValues) {
    if (!edit_target) {
      return;
    }
    set_submitting(true);
    set_error(null);
    try {
      const payload: UserUpdateRequest = {
        role: values.role,
        gym_ids: parse_scope_input(values.gym_ids),
        device_ids: parse_scope_input(values.device_ids)
      };
      if (values.password) {
        payload.password = values.password;
      }
      await update_user(edit_target.username, payload);
      set_edit_target(null);
      edit_form.resetFields();
      await load_users();
    } catch (submit_error) {
      set_error(submit_error instanceof Error ? submit_error.message : '更新用户失败');
    } finally {
      set_submitting(false);
    }
  }

  async function handle_delete(username: string) {
    set_submitting(true);
    set_error(null);
    try {
      await delete_user(username);
      await load_users();
    } catch (submit_error) {
      set_error(submit_error instanceof Error ? submit_error.message : '删除用户失败');
    } finally {
      set_submitting(false);
    }
  }

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 用户管理"
        title="登录后可管理后台账号"
        description="当前页面仅允许后台管理员访问，未登录时不会发起用户管理接口调用。"
      />
    );
  }

  if (session.user.role !== 'admin') {
    return (
      <section className="page_shell">
        <section className="hero_banner compact_hero_banner">
          <div>
            <div className="eyebrow">06 网页端 / 用户管理</div>
            <h1>当前账号没有用户管理权限</h1>
            <p>当前仅 <code>admin</code> 角色允许访问 <code>/api/v1/users</code>。</p>
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
          <div className="eyebrow">06 网页端 / 用户管理</div>
          <h1>账号都在这里</h1>
          <p>统一管理后台账号与角色范围。</p>
        </div>
      </section>

      {error ? <Alert type="error" message="用户管理异常" description={error} showIcon /> : null}

      <div className="panel_surface full_width_panel">
        <div className="panel_header compact_panel_header">
          <div>
            <div className="eyebrow">账号清单</div>
            <h3>当前用户</h3>
          </div>
          <Space wrap>
            <Button onClick={() => void load_users()} loading={loading || submitting}>
              刷新列表
            </Button>
            <Button type="primary" onClick={() => set_create_open(true)}>
              新建用户
            </Button>
            <Popover
              title="角色说明"
              content={
                <Space direction="vertical" size="small" style={{ maxWidth: 320 }}>
                  <span>
                    <code>admin</code> 不受场馆与设备归属限制，可访问全部现有后台接口，并管理 <code>/api/v1/users</code>。
                  </span>
                  <span>
                    <code>teacher</code> 可访问 <code>gym_ids</code> 归属场馆下的业务数据，也可访问 <code>device_ids</code> 明确绑定的设备。
                  </span>
                  <span>
                    <code>student</code> 仅可访问 <code>device_ids</code> 明确绑定的设备数据；<code>gym_ids</code> 不会自动放开全馆数据。
                  </span>
                  <span>
                    部署生成的 <code>bootstrap admin</code> 不能在这里改密、降权或删除。
                  </span>
                </Space>
              }
            >
              <Button type="text" icon={<QuestionCircleOutlined />} className="panel_hint_button">
                角色说明
              </Button>
            </Popover>
          </Space>
        </div>
        {loading ? (
          <div className="loading_surface"><Spin size="large" /></div>
        ) : (
          <Table<UserSummary>
            rowKey="username"
            dataSource={users}
            columns={columns}
            pagination={false}
            scroll={{ x: 1100 }}
          />
        )}
      </div>

      <Modal
        title="新建用户"
        open={create_open}
        onCancel={() => {
          set_create_open(false);
          create_form.resetFields();
        }}
        onOk={() => void create_form.submit()}
        confirmLoading={submitting}
        okText="创建"
        cancelText="取消"
      >
        <Form form={create_form} layout="vertical" onFinish={(values) => void handle_create(values)}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入初始密码' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="teacher" rules={[{ required: true, message: '请选择角色' }]}> 
            <Select options={role_options} />
          </Form.Item>
          <Collapse
            className="inline_collapse"
            items={[
              {
                key: 'create-user-scope',
                label: '归属范围配置',
                children: (
                  <>
                    <Form.Item
                      name="gym_ids"
                      label="场馆归属"
                      tooltip="每行一个 gym_id，也支持逗号或空格分隔"
                      initialValue=""
                    >
                      <Input.TextArea rows={4} placeholder={'gym-gz-01\ngym-sz-02'} />
                    </Form.Item>
                    <Form.Item
                      name="device_ids"
                      label="设备归属"
                      tooltip="每行一个 device_id，也支持逗号或空格分隔"
                      initialValue=""
                    >
                      <Input.TextArea rows={4} placeholder={'wb-001\neq-001\nenv-zone-a'} />
                    </Form.Item>
                  </>
                )
              }
            ]}
          />
        </Form>
      </Modal>

      <Modal
        title={edit_target ? `编辑用户 ${edit_target.username}` : '编辑用户'}
        open={Boolean(edit_target)}
        onCancel={() => {
          set_edit_target(null);
          edit_form.resetFields();
        }}
        onOk={() => void edit_form.submit()}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
      >
        <Form form={edit_form} layout="vertical" onFinish={(values) => void handle_edit(values)}>
          <Form.Item name="username" label="用户名">
            <Input disabled />
          </Form.Item>
          <Form.Item name="password" label="新密码">
            <Input.Password autoComplete="new-password" placeholder="留空则不修改" />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true, message: '请选择角色' }]}> 
            <Select options={role_options} />
          </Form.Item>
          <Collapse
            className="inline_collapse"
            items={[
              {
                key: 'edit-user-scope',
                label: '归属范围配置',
                children: (
                  <>
                    <Form.Item
                      name="gym_ids"
                      label="场馆归属"
                      tooltip="每行一个 gym_id，也支持逗号或空格分隔"
                    >
                      <Input.TextArea rows={4} placeholder={'gym-gz-01\ngym-sz-02'} />
                    </Form.Item>
                    <Form.Item
                      name="device_ids"
                      label="设备归属"
                      tooltip="每行一个 device_id，也支持逗号或空格分隔"
                    >
                      <Input.TextArea rows={4} placeholder={'wb-001\neq-001\nenv-zone-a'} />
                    </Form.Item>
                  </>
                )
              }
            ]}
          />
        </Form>
      </Modal>
    </section>
  );
}
