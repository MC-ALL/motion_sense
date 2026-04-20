import { useEffect, useMemo, useState } from 'react';

import { Alert, Button, Collapse, Descriptions, Input, List, Select, Space, Spin, Statistic, Tag } from 'antd';
import type { AxiosError } from 'axios';
import { useNavigate, useParams } from 'react-router-dom';

import {
  create_user_wristband_binding,
  end_user_wristband_binding,
  fetch_devices,
  fetch_user_training_profile
} from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { use_auth_store } from '../store/auth_store';
import type { DeviceSummary, UserTrainingProfileResponse, WorkoutSessionSummary } from '../types/backend';
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

function describe_error(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const detail = (error as AxiosError<{ detail?: string }>).response?.data?.detail;
    if (typeof detail === 'string' && detail) {
      return detail;
    }
  }
  return error instanceof Error ? error.message : fallback;
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
  const [wristband_loading, set_wristband_loading] = useState(false);
  const [wristband_error, set_wristband_error] = useState<string | null>(null);
  const [wristband_devices, set_wristband_devices] = useState<DeviceSummary[]>([]);
  const [selected_wristband_id, set_selected_wristband_id] = useState('');
  const [bind_note, set_bind_note] = useState('');
  const [unbind_note, set_unbind_note] = useState('');
  const [binding_submitting, set_binding_submitting] = useState(false);
  const [binding_error, set_binding_error] = useState<string | null>(null);
  const [binding_feedback, set_binding_feedback] = useState<string | null>(null);

  const target_username = route_username ?? session?.user.username ?? null;
  const can_switch_user = session?.user.role === 'admin' || session?.user.role === 'teacher';
  const can_manage_binding = session?.user.role === 'admin' && profile?.user.role === 'student';
  const selected_wristband = useMemo(
    () => wristband_devices.find((item) => item.device_id === selected_wristband_id) ?? null,
    [selected_wristband_id, wristband_devices]
  );

  async function request_profile(username: string): Promise<UserTrainingProfileResponse> {
    return fetch_user_training_profile(username, {
      start: build_start_time(window_key),
      binding_limit: 10,
      session_limit: 20
    });
  }

  async function reload_profile() {
    if (!target_username) {
      return;
    }
    const response = await request_profile(target_username);
    set_profile(response);
  }

  useEffect(() => {
    set_search_username(route_username ?? '');
  }, [route_username]);

  useEffect(() => {
    set_binding_error(null);
    set_binding_feedback(null);
    set_bind_note('');
    set_unbind_note('');
  }, [target_username]);

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
          set_error(load_error instanceof Error ? load_error.message : '训练档案加载失败');
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

  useEffect(() => {
    if (session?.user.role !== 'admin') {
      set_wristband_loading(false);
      set_wristband_error(null);
      set_wristband_devices([]);
      return;
    }

    let mounted = true;
    async function load_wristbands() {
      set_wristband_loading(true);
      set_wristband_error(null);
      try {
        const devices = await fetch_devices({ type: 'wristband' });
        if (!mounted) {
          return;
        }
        set_wristband_devices(devices);
      } catch (load_error) {
        if (mounted) {
          set_wristband_devices([]);
          set_wristband_error(describe_error(load_error, '手环设备列表加载失败'));
        }
      } finally {
        if (mounted) {
          set_wristband_loading(false);
        }
      }
    }
    void load_wristbands();
    return () => {
      mounted = false;
    };
  }, [session?.user.role]);

  useEffect(() => {
    if (wristband_devices.length === 0) {
      if (selected_wristband_id) {
        set_selected_wristband_id('');
      }
      return;
    }
    if (wristband_devices.some((item) => item.device_id === selected_wristband_id)) {
      return;
    }
    const active_wristband_id = profile?.active_binding?.wristband_id;
    if (active_wristband_id && wristband_devices.some((item) => item.device_id === active_wristband_id)) {
      set_selected_wristband_id(active_wristband_id);
      return;
    }
    set_selected_wristband_id(wristband_devices[0].device_id);
  }, [profile?.active_binding?.wristband_id, selected_wristband_id, wristband_devices]);

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

  async function handle_bind() {
    if (!profile || !selected_wristband) {
      return;
    }
    set_binding_submitting(true);
    set_binding_error(null);
    set_binding_feedback(null);
    try {
      await create_user_wristband_binding({
        username: profile.user.username,
        wristband_id: selected_wristband.device_id,
        gym_id: selected_wristband.gym_id,
        source: 'manual',
        note: bind_note.trim() || null
      });
      set_bind_note('');
      set_binding_feedback(`已将 ${selected_wristband.device_id} 绑定到 ${profile.user.username}`);
      await reload_profile();
    } catch (submit_error) {
      set_binding_error(describe_error(submit_error, '绑定手环失败'));
    } finally {
      set_binding_submitting(false);
    }
  }

  async function handle_unbind() {
    if (!profile?.active_binding) {
      return;
    }
    set_binding_submitting(true);
    set_binding_error(null);
    set_binding_feedback(null);
    try {
      const result = await end_user_wristband_binding(profile.active_binding.id, {
        note: unbind_note.trim() || null
      });
      set_unbind_note('');
      set_binding_feedback(`已解绑 ${result.wristband_id}`);
      await reload_profile();
    } catch (submit_error) {
      set_binding_error(describe_error(submit_error, '解绑手环失败'));
    } finally {
      set_binding_submitting(false);
    }
  }

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

      {error ? <Alert type="error" showIcon message="训练档案加载失败" description={error} /> : null}
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
                ) : (
                  <Alert type="info" showIcon message="当前没有激活中的手环绑定" />
                )}
              </div>

              {can_manage_binding ? (
                <div className="panel_surface">
                  <div className="panel_header compact_panel_header">
                    <div>
                      <div className="eyebrow">管理员维护</div>
                      <h3>学生手环绑定维护</h3>
                    </div>
                  </div>
                  <p className="panel_meta_text archive_hint_text">
                    当前直接调用后台学生-手环绑定接口。提交成功后，本页会立即刷新训练档案聚合结果。
                  </p>
                  {wristband_error ? <Alert type="error" showIcon message="手环列表加载失败" description={wristband_error} /> : null}
                  {binding_error ? <Alert type="error" showIcon message="绑定维护失败" description={binding_error} /> : null}
                  {binding_feedback ? <Alert type="success" showIcon message={binding_feedback} /> : null}
                  {wristband_devices.length === 0 ? (
                    <Alert type="info" showIcon message="当前没有可选手环设备，请先在设备注册页补齐 wristband 设备。" />
                  ) : (
                    <>
                      <div className="archive_admin_grid">
                        <div>
                          <div className="panel_meta_text">待绑定手环</div>
                          <Select
                            className="archive_admin_select"
                            showSearch
                            value={selected_wristband_id || undefined}
                            placeholder="选择手环设备"
                            loading={wristband_loading}
                            optionFilterProp="label"
                            onChange={(value) => set_selected_wristband_id(value)}
                            options={wristband_devices.map((item) => ({
                              value: item.device_id,
                              label: `${item.device_id} · ${item.gym_id}${item.display_name ? ` · ${item.display_name}` : ''}`
                            }))}
                          />
                          {selected_wristband ? (
                            <div className="panel_meta_text archive_hint_text">
                              所属场馆：{selected_wristband.gym_id}
                              {selected_wristband.location ? ` · 位置：${selected_wristband.location}` : ''}
                            </div>
                          ) : null}
                        </div>
                        <div>
                          <div className="panel_meta_text">绑定备注</div>
                          <Input
                            value={bind_note}
                            maxLength={500}
                            placeholder="例如：新学员入场手动绑定"
                            onChange={(event) => set_bind_note(event.target.value)}
                          />
                        </div>
                      </div>
                      <div className="archive_admin_actions">
                        <Button
                          type="primary"
                          loading={binding_submitting}
                          disabled={!selected_wristband || Boolean(profile.active_binding)}
                          onClick={() => void handle_bind()}
                        >
                          {profile.active_binding ? '请先解绑当前手环' : '绑定选中手环'}
                        </Button>
                      </div>
                    </>
                  )}
                  {profile.active_binding ? (
                    <>
                      <div className="archive_admin_grid">
                        <div>
                          <div className="panel_meta_text">解绑备注</div>
                          <Input
                            value={unbind_note}
                            maxLength={500}
                            placeholder="例如：课程结束、设备回收"
                            onChange={(event) => set_unbind_note(event.target.value)}
                          />
                        </div>
                      </div>
                      <div className="archive_admin_actions">
                        <Button danger loading={binding_submitting} onClick={() => void handle_unbind()}>
                          解绑当前手环
                        </Button>
                      </div>
                    </>
                  ) : null}
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
                  <Alert type="info" showIcon message="当前查询窗口内还没有训练会话" />
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
                  <Alert type="info" showIcon message="当前没有学生-手环绑定历史" />
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
