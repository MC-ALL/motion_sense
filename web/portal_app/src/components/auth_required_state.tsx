import { Button, Alert } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';

type AuthRequiredStateProps = {
  eyebrow: string;
  title: string;
  description: string;
};

export function AuthRequiredState({ eyebrow, title, description }: AuthRequiredStateProps) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <Button
          type="primary"
          onClick={() =>
            navigate('/login', {
              state: {
                from: `${location.pathname}${location.search}${location.hash}`
              }
            })
          }
        >
          前往登录页
        </Button>
      </section>
      <Alert
        type="warning"
        message="请先登录后台账号"
        description="左侧栏提供“登录后台”入口；登录成功后会自动恢复当前页面的数据请求。"
        showIcon
      />
    </section>
  );
}
