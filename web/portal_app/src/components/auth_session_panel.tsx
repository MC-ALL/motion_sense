import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Button, Space, Tag } from 'antd';

import { use_auth_store } from '../store/auth_store';
import { describe_user_scope } from '../utils/user_scope';

export function AuthSessionPanel() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = use_auth_store((state) => state.session);
  const loading = use_auth_store((state) => state.loading);
  const logout = use_auth_store((state) => state.logout);
  const hydrate = use_auth_store((state) => state.hydrate);
  const scope_description = describe_user_scope(session?.user);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const redirect_state = {
    from: `${location.pathname}${location.search}${location.hash}`
  };

  return (
    <div className="auth_panel">
      <button
        type="button"
        className="auth_identity_button"
        onClick={() =>
          navigate(session ? '/profile' : '/login', {
            state: redirect_state
          })
        }
      >
        <div className="eyebrow">后台认证</div>
        <strong>{session ? session.user.username : '匿名访问'}</strong>
        <div className="scope_hint">数据范围：{scope_description}</div>
      </button>
      <Space wrap>
        <Tag color={session ? 'green' : 'default'}>{session ? session.user.role : 'anonymous'}</Tag>
        {session?.user.role === 'admin' ? <Tag color="gold">全部范围</Tag> : null}
        {session?.user.gym_ids.map((gym_id) => (
          <Tag key={`gym-${gym_id}`}>gym:{gym_id}</Tag>
        ))}
        {session?.user.device_ids.map((device_id) => (
          <Tag key={`device-${device_id}`}>device:{device_id}</Tag>
        ))}
      </Space>
      <Space wrap>
        {session ? (
          <>
            <Button size="small" onClick={() => navigate('/profile')}>
              个人中心
            </Button>
            <Button size="small" onClick={() => void logout()} loading={loading}>
              退出
            </Button>
          </>
        ) : (
          <Button
            size="small"
            type="primary"
            onClick={() =>
              navigate('/login', {
                state: redirect_state
              })
            }
          >
            登录后台
          </Button>
        )}
      </Space>
    </div>
  );
}
