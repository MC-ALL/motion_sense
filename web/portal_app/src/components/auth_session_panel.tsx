import { useEffect, useState } from 'react';

import { Alert, Button, Form, Input, Modal, Space, Tag } from 'antd';

import { use_auth_store } from '../store/auth_store';

export function AuthSessionPanel() {
  const [open, set_open] = useState(false);
  const [form] = Form.useForm<{ username: string; password: string }>();

  const session = use_auth_store((state) => state.session);
  const loading = use_auth_store((state) => state.loading);
  const error = use_auth_store((state) => state.error);
  const login = use_auth_store((state) => state.login);
  const logout = use_auth_store((state) => state.logout);
  const hydrate = use_auth_store((state) => state.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  async function handle_submit() {
    const values = await form.validateFields();
    await login(values.username, values.password);
    if (!use_auth_store.getState().error) {
      set_open(false);
      form.resetFields();
    }
  }

  return (
    <div className="auth_panel">
      <div>
        <div className="eyebrow">后台认证</div>
        <strong>{session ? session.user.username : '匿名访问'}</strong>
      </div>
      <Space wrap>
        <Tag color={session ? 'green' : 'default'}>{session ? session.user.role : 'anonymous'}</Tag>
        {session ? (
          <Button size="small" onClick={() => void logout()} loading={loading}>
            退出
          </Button>
        ) : (
          <Button size="small" type="primary" onClick={() => set_open(true)}>
            登录后台
          </Button>
        )}
      </Space>

      <Modal
        title="登录后台"
        open={open}
        onCancel={() => set_open(false)}
        onOk={() => void handle_submit()}
        confirmLoading={loading}
        okText="登录"
        cancelText="取消"
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {error ? <Alert type="error" message={error} showIcon /> : null}
          <Form form={form} layout="vertical">
            <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input autoComplete="username" />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password autoComplete="current-password" />
            </Form.Item>
          </Form>
        </Space>
      </Modal>
    </div>
  );
}
