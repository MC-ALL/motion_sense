import { useEffect, useMemo, useState } from 'react';

import { Button, Collapse, Descriptions, Input, List, Space, Spin, Statistic, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';

import { fetch_user_training_profile } from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { NoticeCard } from '../components/notice_card';
import { use_auth_store } from '../store/auth_store';
import type { UserTrainingProfileResponse, WorkoutSessionSummary } from '../types/backend';
import type { NoticeTone } from '../ui/ui_semantics';
import { page_error_fallbacks, page_notice_titles } from '../ui/message_catalog';
import { format_time } from '../utils/time';
import { describe_user_scope } from '../utils/user_scope';

type WindowKey = '7d' | '30d' | 'all';

const window_options: Array<{ label: string; value: WindowKey }> = [
  { label: '近 7 天', value: '7d' },
  { label: '近 30 天', value: '30d' },
  { label: '全部', value: 'all' }
];

function build_start_time(window_key: WindowKey): string | undefined {
  if (window_key === 'all') {
    return undefined;
  }
  const now = Date.now();
  const offset_ms = window_key === '7d' ? 7 * 24 * 60 * 60 * 1000 : 30 * 24 * 60 * 60 * 1000;
  return new Date(now - offset_ms).toISOString();
}

function format_duration(duration_s?: number | null): string {
  if (!duration_s || duration_s <= 0) {
    return '--';
  }
  const hours = Math.floor(duration_s / 3600);
  const minutes = Math.floor((duration_s % 3600) / 60);
  if (hours > 0) {
    return `${hours} 小时 ${minutes} 分`;
  }
  return `${minutes} 分钟`;
}

function session_status_color(status: WorkoutSessionSummary['status']): string {
  if (status === 'completed') {
    return 'green';
  }
  if (status === 'open') {
    return 'blue';
  }
  return 'default';
}

function render_notice(tone: NoticeTone, title: string, description?: string | null) {
  return <NoticeCard tone={tone} title={title} description={description} />;
}

export function TrainingArchivePage() {
  const navigate = useNavigate();
  const { username: route_username } = useParams<{ username?: string }>();
  const session = use_auth_store((state) => state.session);
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [profile, set_profile] = useState<UserTrainingProfileResponse | null>(null);
  const [window_key, set_window_key] = useState<WindowKey>('30d');
  const [search_username, set_search_username] = useState(route_username ?? '');

  const target_username = route_username ?? session?.user.username ?? null;
  const can_switch_user = session?.user.role === 'admin' || session?.user.role === 'teacher';
  const can_manage_binding = session?.user.role === 'admin' && profile?.user.role === 'student';

  async function request_profile(username: string): Promise<UserTrainingProfileResponse> {
    return fetch_user_training_profile(username, {
      start: build_start_time(window_key),
      binding_limit: 10,
      session_limit: 20
    });
  }

  useEffect(() => {
    set_search_username(route_username ?? '');
  }, [route_username]);

  useEffect(() => {
    if (!session || !target_username) {
      set_loading(false);
      set_profile(null);
      set_error(null);
      return;
    }

    const current_username = target_username;
    let mounted = true;
    async function load_profile() {
      set_loading(true);
      set_error(null);
      try {
        const response = await request_profile(current_username);
        if (!mounted) {
          return;
        }
        set_profile(response);
      } catch (load_error) {
        if (mounted) {
          set_profile(null);
          set_error(load_error instanceof Error ? load_error.message : page_error_fallbacks.training_archive_load_failed);
        }
      } finally {
        if (mounted) {
          set_loading(false);
        }
      }
    }
    void load_profile();
    return () => {
      mounted = false;
    };
  }, [session, target_username, window_key]);

  const summary_cards = useMemo(() => {
    if (!profile) {
      return null;
    }
    return (
      <div className="metric_grid metric_grid_five">
        <div className="panel_surface metric_card"><Statistic title="训练次数" value={profile.summary.total_sessions} /></div>
        <div className="panel_surface metric_card"><Statistic title="总时长" value={format_duration(profile.summary.total_duration_s)} /></div>
        <div className="panel_surface metric_card"><Statistic title="总动作数" value={profile.summary.total_rep_count} /></div>
        <div className="panel_surface metric_card"><Statistic title="总能耗(Wh)" value={profile.summary.total_energy_wh} precision={1} /></div>
        <div className="panel_surface metric_card"><Statistic title="平均心率" value={profile.summary.avg_heart_rate ?? '--'} precision={1} /></div>
      </div>
    );
  }, [profile]);

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / 训练档案"
        title="登录后可查看训练档案"
        description="训练档案会按当前登录角色和账号范围返回学生绑定、训练会话与阶段汇总。"
      />
    );
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / 训练档案</div>
          <h1>{target_username ? `训练档案：${target_username}` : '训练档案'}</h1>
          <p>按学生账号汇总手环绑定与训练会话，为教师复盘、学生自查和后续 AI 报告提供统一入口。</p>
        </div>
        <Space wrap>
          <Button onClick={() => navigate('/profile')}>返回个人中心</Button>
          {can_switch_user && target_username !== session.user.username ? (
            <Button onClick={() => navigate('/training-archive')}>查看我的档案</Button>
          ) : null}
        </Space>
      </section>

      <div className="panel_surface archive_filter_panel">
        <Space wrap align="end">
          {can_switch_user ? (
            <>
              <Input
                value={search_username}
                onChange={(event) => set_search_username(event.target.value)}
                placeholder="输入学生用户名"
                style={{ width: 220 }}
                onPressEnter={() => {
                  const next_username = search_username.trim();
                  navigate(next_username ? `/training-archive/${next_username}` : '/training-archive');
                }}
              />
              <Button
                type="primary"
                onClick={() => {
                  const next_username = search_username.trim();
                  navigate(next_username ? `/training-archive/${next_username}` : '/training-archive');
                }}
              >
                加载档案
              </Button>
            </>
          ) : null}
          <Space.Compact>
            {window_options.map((item) => (
              <Button
                key={item.value}
                type={window_key === item.value ? 'primary' : 'default'}
                onClick={() => set_window_key(item.value)}
              >
                {item.label}
              </Button>
            ))}
          </Space.Compact>
        </Space>
      </div>

      {error ? render_notice('error', page_notice_titles.training_archive_error, error) : null}
      {loading ? <div className="panel_surface loading_surface"><Spin size="large" /></div> : null}

      {!loading && profile ? (
        <>
          {summary_cards}

          <div className="content_grid">
            <div className="left_column">
              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">账号与归属</div>
                    <h3>当前档案对象</h3>
                  </div>
                </div>
                <Descriptions column={1} bordered size="middle" labelStyle={{ width: 160 }}>
                  <Descriptions.Item label="用户名">{profile.user.username}</Descriptions.Item>
                  <Descriptions.Item label="角色">
                    <Tag color={profile.user.role === 'admin' ? 'gold' : profile.user.role === 'teacher' ? 'blue' : 'green'}>
                      {profile.user.role}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="数据范围">{describe_user_scope(profile.user)}</Descriptions.Item>
                  <Descriptions.Item label="最近训练结束">{profile.summary.last_session_at ? format_time(profile.summary.last_session_at) : '--'}</Descriptions.Item>
                  <Descriptions.Item label="覆盖器材">
                    <Space size={[4, 4]} wrap>
                      {profile.summary.equipment_ids.length > 0 ? profile.summary.equipment_ids.map((item) => <Tag key={item}>{item}</Tag>) : <span>暂无</span>}
                    </Space>
                  </Descriptions.Item>
                </Descriptions>
              </div>

              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">手环绑定</div>
                    <h3>当前绑定状态</h3>
                  </div>
                </div>
                {profile.active_binding ? (
                  <Descriptions column={1} bordered size="middle" labelStyle={{ width: 160 }}>
                    <Descriptions.Item label="手环">{profile.active_binding.wristband_id}</Descriptions.Item>
                    <Descriptions.Item label="场馆">{profile.active_binding.gym_id}</Descriptions.Item>
                    <Descriptions.Item label="绑定时间">{format_time(profile.active_binding.bound_at)}</Descriptions.Item>
                    <Descriptions.Item label="来源">{profile.active_binding.source}</Descriptions.Item>
                    <Descriptions.Item label="备注">{profile.active_binding.note || '--'}</Descriptions.Item>
                  </Descriptions>
                ) : render_notice('info', '当前没有激活中的手环绑定')}
              </div>

              {can_manage_binding ? (
                <div className="panel_surface">
                  <div className="panel_header compact_panel_header">
                    <div>
                      <div className="eyebrow">管理员入口</div>
                      <h3>前往设备管理维护绑定</h3>
                    </div>
                  </div>
                  <div className="archive_notice_stack">
                    {render_notice(
                      'info',
                      '绑定维护已迁移',
                      '学生与手环的绑定/解绑操作已统一迁移到“设备管理 -> 手环绑定”。训练档案页现在只展示当前绑定结果与绑定历史，不再直接写入绑定关系。'
                    )}
                    {render_notice(
                      'warning',
                      '操作规则',
                      '一个学生和一个手环在同一时刻都只能存在一条激活绑定。需要更换对象时，请先在设备管理页解绑当前记录，再建立新绑定。'
                    )}
                  </div>
                  <div className="archive_admin_actions">
                    <Button
                      type="primary"
                      onClick={() =>
                        navigate(
                          `/device-registry?tab=wristband-bindings&username=${encodeURIComponent(profile.user.username)}`
                        )
                      }
                    >
                      打开设备管理
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="right_column">
              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">训练会话</div>
                    <h3>最近训练记录</h3>
                  </div>
                </div>
                {profile.recent_sessions.length === 0 ? (
                  render_notice('info', '当前查询窗口内还没有训练会话')
                ) : (
                  <List
                    itemLayout="vertical"
                    dataSource={profile.recent_sessions}
                    renderItem={(item) => (
                      <List.Item className="archive_session_item">
                        <List.Item.Meta
                          title={
                            <Space wrap>
                              <strong>{format_time(item.started_at)}</strong>
                              <Tag color={session_status_color(item.status)}>{item.status}</Tag>
                              <Tag>{item.wristband_id}</Tag>
                            </Space>
                          }
                          description={
                            <Space size={[6, 6]} wrap>
                              <span>时长 {format_duration(item.duration_s)}</span>
                              <span>动作 {item.metrics.total_rep_count ?? 0}</span>
                              <span>能耗 {item.metrics.total_energy_wh ?? 0} Wh</span>
                              <span>平均心率 {item.metrics.avg_heart_rate ?? '--'}</span>
                            </Space>
                          }
                        />
                        <div className="archive_session_tags">
                          {item.equipment_ids.map((equipment_id) => (
                            <Tag key={equipment_id}>{equipment_id}</Tag>
                          ))}
                        </div>
                        <Collapse
                          size="small"
                          items={[
                            {
                              key: `${item.session_id}-segments`,
                              label: '查看器材分段',
                              children: (
                                <List
                                  dataSource={item.segments}
                                  renderItem={(segment) => (
                                    <List.Item>
                                      <List.Item.Meta
                                        title={`${segment.equipment_id} · ${format_duration(segment.duration_s)}`}
                                        description={`开始 ${format_time(segment.started_at)} / 动作 ${segment.rep_count ?? 0} / 能耗 ${segment.energy_wh ?? 0} Wh`}
                                      />
                                    </List.Item>
                                  )}
                                />
                              )
                            }
                          ]}
                        />
                        {item.notes ? <div className="panel_meta_text archive_note">备注：{item.notes}</div> : null}
                      </List.Item>
                    )}
                  />
                )}
              </div>

              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">绑定历史</div>
                    <h3>最近绑定变更</h3>
                  </div>
                </div>
                {profile.recent_bindings.length === 0 ? (
                  render_notice('info', '当前没有学生-手环绑定历史')
                ) : (
                  <List
                    dataSource={profile.recent_bindings}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <Space wrap>
                              <strong>{item.wristband_id}</strong>
                              <Tag color={item.is_active ? 'green' : 'default'}>{item.is_active ? 'active' : 'inactive'}</Tag>
                              <Tag>{item.gym_id}</Tag>
                            </Space>
                          }
                          description={`绑定 ${format_time(item.bound_at)}${item.unbound_at ? ` / 解绑 ${format_time(item.unbound_at)}` : ''}`}
                        />
                      </List.Item>
                    )}
                  />
                )}
              </div>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
