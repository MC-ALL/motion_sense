import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Button, Card, Form, Input, Space, Tag } from 'antd';

import { InlineNotice } from '../components/notice_card';
import { get_runtime_config } from '../config/runtime_config';
import { use_auth_store } from '../store/auth_store';
import { describe_user_scope } from '../utils/user_scope';

type LoginFormValues = {
  username: string;
  password: string;
};

function normalize_redirect_target(raw: unknown): string {
  if (typeof raw !== 'string' || raw.length === 0) {
    return '/dashboard';
  }
  if (!raw.startsWith('/')) {
    return '/dashboard';
  }
  if (raw.startsWith('/login')) {
    return '/dashboard';
  }
  return raw;
}

export function LoginPage() {
  const runtime_config = get_runtime_config();
  const navigate = useNavigate();
  const location = useLocation();
  const [form] = Form.useForm<LoginFormValues>();

  const session = use_auth_store((state) => state.session);
  const loading = use_auth_store((state) => state.loading);
  const error = use_auth_store((state) => state.error);
  const login = use_auth_store((state) => state.login);
  const hydrate = use_auth_store((state) => state.hydrate);

  const redirect_target = normalize_redirect_target((location.state as { from?: string } | null)?.from);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (session) {
      navigate(redirect_target, { replace: true });
    }
  }, [navigate, redirect_target, session]);

  async function handle_submit(values: LoginFormValues) {
    await login(values.username, values.password);
    if (use_auth_store.getState().session) {
      navigate(redirect_target, { replace: true });
    }
  }

  return (
    <main className="login_page_shell">
      <section className="login_hero">
        <div className="brand_block login_brand_block">
          <div className="brand_mark">MS</div>
          <div>
            <div className="eyebrow">粤动智感</div>
            <strong>{runtime_config.app_name}</strong>
          </div>
        </div>
        <div className="login_hero_copy">
          <div className="eyebrow">独立登录页</div>
          <h1>先登录，再进入页面</h1>
          <p>统一使用后台认证进入业务与运维页面。</p>
        </div>
        <Space wrap>
          <Tag color="gold">admin</Tag>
          <Tag color="blue">teacher</Tag>
          <Tag color="green">student</Tag>
        </Space>
      </section>

      <Card className="login_card" bordered={false}>
        <div className="eyebrow">后台认证</div>
        <h2>登录后台账号</h2>
        <p className="login_hint">登录成功后将跳转到：<code>{redirect_target}</code></p>

        {error ? <InlineNotice tone="error" title={error} /> : null}

        <Form form={form} layout="vertical" onFinish={(values) => void handle_submit(values)}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input autoComplete="username" size="large" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password autoComplete="current-password" size="large" />
          </Form.Item>
          <Space className="login_actions">
            <Button type="primary" htmlType="submit" loading={loading} size="large">
              登录
            </Button>
            <Button size="large" onClick={() => navigate('/dashboard')}>
              返回首页
            </Button>
          </Space>
        </Form>

        {session ? (
          <InlineNotice
            tone="success"
            title={`当前已登录：${session.user.username}`}
            description={`角色：${session.user.role}；数据范围：${describe_user_scope(session.user)}`}
          />
        ) : null}
      </Card>
    </main>
  );
}
