import { Button, Descriptions, Space, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';

import { AuthRequiredState } from '../components/auth_required_state';
import { use_auth_store } from '../store/auth_store';
import { describe_user_scope } from '../utils/user_scope';

export function ProfilePage() {
  const navigate = useNavigate();
  const session = use_auth_store((state) => state.session);
  const logout = use_auth_store((state) => state.logout);
  const loading = use_auth_store((state) => state.loading);

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 个人中心"
        title="登录后可查看当前账号信息"
        description="个人中心展示当前 JWT 会话对应的账号、角色与数据范围，未登录时会跳转到登录流程。"
      />
    );
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 个人中心</div>
          <h1>先看当前账号</h1>
          <p>统一查看角色范围与常用入口。</p>
        </div>
        <Space wrap>
          <Button onClick={() => navigate('/dashboard')}>返回仪表盘</Button>
          <Button type="primary" danger loading={loading} onClick={() => void logout()}>
            退出登录
          </Button>
        </Space>
      </section>

      <div className="panel_surface profile_notice_panel">
        <div className="eyebrow">当前状态</div>
        <h3>当前个人中心为 P1 信息页</h3>
        <p>目前不直接提供改密、修改个人资料等自助能力，避免绕过后台现有角色边界。</p>
      </div>

      <div className="panel_surface">
        <Descriptions column={1} bordered size="middle" labelStyle={{ width: 160 }}>
          <Descriptions.Item label="用户名">{session.user.username}</Descriptions.Item>
          <Descriptions.Item label="角色">
            <Tag color={session.user.role === 'admin' ? 'gold' : session.user.role === 'teacher' ? 'blue' : 'green'}>
              {session.user.role}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="数据范围">{describe_user_scope(session.user)}</Descriptions.Item>
          <Descriptions.Item label="场馆归属">
            <Space wrap>
              {session.user.gym_ids.length > 0 ? session.user.gym_ids.map((gym_id) => <Tag key={gym_id}>{gym_id}</Tag>) : <span>未限制</span>}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="设备归属">
            <Space wrap>
              {session.user.device_ids.length > 0 ? session.user.device_ids.map((device_id) => <Tag key={device_id}>{device_id}</Tag>) : <span>未限制</span>}
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </div>

      <div className="panel_surface quick_link_panel">
        <div className="panel_header compact_panel_header">
          <div>
            <div className="eyebrow">快捷入口</div>
            <h3>常用页面</h3>
          </div>
        </div>
        <Space wrap>
          <Button onClick={() => navigate('/equipment')}>器材管理</Button>
          <Button onClick={() => navigate('/wristband')}>手环管理</Button>
          <Button onClick={() => navigate('/env-quality')}>环境质量</Button>
          <Button onClick={() => navigate('/training-archive')}>训练档案</Button>
          <Button onClick={() => navigate('/ai-reports')}>AI 报告</Button>
          {session.user.role !== 'student' ? <Button onClick={() => navigate('/alerts')}>告警管理</Button> : null}
          {session.user.role === 'admin' ? <Button onClick={() => navigate('/health-center')}>系统健康中心</Button> : null}
        </Space>
      </div>
    </section>
  );
}
