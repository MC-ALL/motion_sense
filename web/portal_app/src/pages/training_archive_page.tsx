import { useEffect, useMemo, useState } from 'react';

import type { AxiosError } from 'axios';
import { Button, Collapse, Descriptions, List, Select, Space, Spin, Statistic, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';

import {
  analyze_ai_report,
  aggregate_workout_sessions,
  fetch_user_training_profile,
  fetch_user_wristband_bindings,
  fetch_users,
  fetch_workout_sessions
} from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { PageNotice } from '../components/notice_card';
import { use_auth_store } from '../store/auth_store';
import type {
  ReservedApiResponse,
  UserTrainingProfileResponse,
  WorkoutSessionAggregateResult,
  WorkoutSessionSegment,
  WorkoutSessionSummary
} from '../types/backend';
import { page_error_fallbacks, page_notice_titles } from '../ui/message_catalog';
import { format_time } from '../utils/time';
import { describe_user_scope } from '../utils/user_scope';

type WindowKey = '7d' | '30d' | 'all';
type AiLaunchState = 'idle' | 'submitting' | 'reserved' | 'failed';

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
  const seconds = duration_s % 60;
  if (hours > 0) {
    return `${hours} 小时 ${minutes} 分`;
  }
  if (minutes > 0) {
    return `${minutes} 分 ${seconds} 秒`;
  }
  return `${seconds} 秒`;
}

function describe_error(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const detail = (error as AxiosError<{ detail?: string | ReservedApiResponse }>).response?.data?.detail;
    if (typeof detail === 'string' && detail) {
      return detail;
    }
    if (detail && typeof detail === 'object' && typeof detail.detail === 'string' && detail.detail) {
      return detail.detail;
    }
  }
  return error instanceof Error ? error.message : fallback;
}

function pick_ai_start_time(profile: UserTrainingProfileResponse, window_key: WindowKey): string {
  const window_start = build_start_time(window_key);
  if (window_start) {
    return window_start;
  }
  if (profile.query_start) {
    return profile.query_start;
  }
  if (profile.recent_sessions.length > 0) {
    return profile.recent_sessions
      .map((item) => item.started_at)
      .slice()
      .sort((left, right) => left.localeCompare(right))[0];
  }
  if (profile.active_binding?.bound_at) {
    return profile.active_binding.bound_at;
  }
  return new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
}

function build_ai_scope_text(profile: UserTrainingProfileResponse, window_key: WindowKey): string {
  const current_window = window_options.find((item) => item.value === window_key);
  const time_label = current_window?.label ?? '当前窗口';
  return [
    `${time_label}`,
    `${profile.summary.total_sessions} 次训练`,
    `${format_duration(profile.summary.total_duration_s)}`,
    `${profile.summary.equipment_ids.length} 台器材`
  ].join(' · ');
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

function session_status_label(status: WorkoutSessionSummary['status']): string {
  if (status === 'completed') {
    return '已完成';
  }
  if (status === 'open') {
    return '进行中';
  }
  return '已取消';
}

function session_source_label(source: WorkoutSessionSummary['source']): string {
  if (source === 'aggregated') {
    return '自动汇聚';
  }
  if (source === 'imported') {
    return '导入';
  }
  return '手工';
}

function binding_state_label(is_active: boolean): string {
  return is_active ? '生效中' : '已结束';
}

function render_session_metrics(session: WorkoutSessionSummary) {
  return (
    <div className="archive_session_metric_row">
      <span>时长 {format_duration(session.duration_s)}</span>
      <span>动作 {session.metrics.total_rep_count ?? 0}</span>
      <span>步数 {session.metrics.total_steps ?? 0}</span>
      <span>能耗 {session.metrics.total_energy_wh ?? 0} Wh</span>
      <span>平均心率 {session.metrics.avg_heart_rate ?? '--'}</span>
      <span>峰值心率 {session.metrics.max_heart_rate ?? '--'}</span>
    </div>
  );
}

function render_segment_summary(segment: WorkoutSessionSegment) {
  return (
    <div className="archive_segment_card">
      <div className="archive_segment_header">
        <strong>{segment.equipment_id}</strong>
        <span>{format_duration(segment.duration_s)}</span>
      </div>
      <div className="archive_segment_meta">
        <span>开始 {format_time(segment.started_at)}</span>
        <span>结束 {segment.ended_at ? format_time(segment.ended_at) : '--'}</span>
        <span>动作 {segment.rep_count ?? 0}</span>
        <span>能耗 {segment.energy_wh ?? 0} Wh</span>
      </div>
    </div>
  );
}

function build_aggregate_result_message(result: WorkoutSessionAggregateResult): string {
  return [
    `扫描绑定 ${result.processed_bindings} 条`,
    `新建会话 ${result.created_sessions} 条`,
    `更新会话 ${result.updated_sessions} 条`,
    `返回结果 ${result.sessions.length} 条`
  ].join('，');
}

export function TrainingArchivePage() {
  const navigate = useNavigate();
  const { username: route_username } = useParams<{ username?: string }>();
  const session = use_auth_store((state) => state.session);
  const [loading, set_loading] = useState(true);
  const [syncing_sessions, set_syncing_sessions] = useState(false);
  const [error, set_error] = useState<string | null>(null);
  const [aggregate_summary, set_aggregate_summary] = useState<string | null>(null);
  const [profile, set_profile] = useState<UserTrainingProfileResponse | null>(null);
  const [window_key, set_window_key] = useState<WindowKey>('30d');
  const [candidate_usernames, set_candidate_usernames] = useState<string[]>([]);
  const [ai_launch_state, set_ai_launch_state] = useState<AiLaunchState>('idle');
  const [ai_feedback, set_ai_feedback] = useState<string | null>(null);

  const target_username = route_username ?? session?.user.username ?? null;
  const can_switch_user = session?.user.role === 'admin' || session?.user.role === 'teacher';
  const can_manage_binding = session?.user.role === 'admin' && profile?.user.role === 'student';
  const can_aggregate_sessions = session?.user.role === 'admin' && profile?.user.role === 'student';
  const ai_supported_target = profile?.user.role === 'student';
  const has_training_data = (profile?.recent_sessions.length ?? 0) > 0;
  const can_request_ai = Boolean(profile && ai_supported_target && has_training_data);

  async function request_profile(username: string): Promise<UserTrainingProfileResponse> {
    return fetch_user_training_profile(username, {
      start: build_start_time(window_key),
      binding_limit: 10,
      session_limit: 20
    });
  }

  useEffect(() => {
    if (!session || !can_switch_user) {
      set_candidate_usernames([]);
      return;
    }

    const current_session = session;
    let mounted = true;
    async function load_candidates() {
      try {
        const usernames = new Set<string>();
        if (current_session.user.role === 'admin') {
          const users = await fetch_users();
          for (const item of users) {
            if (item.role === 'student') {
              usernames.add(item.username);
            }
          }
        } else {
          const [bindings, sessions] = await Promise.all([
            fetch_user_wristband_bindings({ limit: 1000 }),
            fetch_workout_sessions({ limit: 1000 })
          ]);
          for (const item of bindings) {
            usernames.add(item.username);
          }
          for (const item of sessions) {
            usernames.add(item.username);
          }
        }
        if (route_username) {
          usernames.add(route_username);
        }
        if (current_session.user.username) {
          usernames.add(current_session.user.username);
        }
        if (mounted) {
          set_candidate_usernames(Array.from(usernames).sort((left, right) => left.localeCompare(right)));
        }
      } catch {
        if (mounted) {
          set_candidate_usernames(route_username ? [route_username] : []);
        }
      }
    }
    void load_candidates();
    return () => {
      mounted = false;
    };
  }, [can_switch_user, route_username, session]);

  useEffect(() => {
    if (!session || !target_username) {
      set_loading(false);
      set_profile(null);
      set_error(null);
      set_aggregate_summary(null);
      set_ai_launch_state('idle');
      set_ai_feedback(null);
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

  useEffect(() => {
    set_ai_launch_state('idle');
    set_ai_feedback(null);
  }, [target_username, window_key]);

  async function reload_profile(username: string) {
    const response = await request_profile(username);
    set_profile(response);
  }

  async function handle_aggregate_sessions() {
    if (!profile) {
      return;
    }
    set_syncing_sessions(true);
    set_error(null);
    try {
      const result = await aggregate_workout_sessions({
        username: profile.user.username,
        start: build_start_time(window_key),
        end: new Date().toISOString()
      });
      set_aggregate_summary(build_aggregate_result_message(result));
      await reload_profile(profile.user.username);
    } catch (aggregate_error) {
      set_error(
        aggregate_error instanceof Error ? aggregate_error.message : page_error_fallbacks.training_archive_aggregate_failed
      );
    } finally {
      set_syncing_sessions(false);
    }
  }

  async function handle_ai_analyze() {
    if (!profile || !can_request_ai) {
      return;
    }

    set_ai_launch_state('submitting');
    set_ai_feedback(null);
    try {
      const result = await analyze_ai_report({
        user_id: profile.user.username,
        start: pick_ai_start_time(profile, window_key),
        end: profile.query_end ?? new Date().toISOString()
      });
      set_ai_launch_state('reserved');
      set_ai_feedback(result.detail);
    } catch (submit_error) {
      const response_detail = (submit_error as AxiosError<{ detail?: ReservedApiResponse }>).response?.data?.detail;
      if (
        (submit_error as AxiosError).response?.status === 501 &&
        response_detail &&
        typeof response_detail === 'object' &&
        response_detail.status === 'reserved'
      ) {
        set_ai_launch_state('reserved');
        set_ai_feedback(response_detail.detail);
        return;
      }
      set_ai_launch_state('failed');
      set_ai_feedback(describe_error(submit_error, page_error_fallbacks.training_archive_ai_failed));
    }
  }

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
              <Select
                showSearch
                allowClear
                optionFilterProp="label"
                placeholder="选择学生账号"
                value={route_username ?? undefined}
                style={{ minWidth: 260 }}
                options={candidate_usernames.map((username) => ({
                  value: username,
                  label: username === session.user.username ? `${username} · 我的账号` : username
                }))}
                onChange={(value) => {
                  navigate(value ? `/training-archive/${value}` : '/training-archive');
                }}
              />
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

      {error ? <PageNotice tone="error" title={page_notice_titles.training_archive_error} description={error} /> : null}
      {aggregate_summary ? (
        <PageNotice
          tone="success"
          title={page_notice_titles.training_archive_aggregate_result}
          description={aggregate_summary}
        />
      ) : null}
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
                ) : <PageNotice tone="info" title="当前没有激活中的手环绑定" />}
              </div>

              {can_manage_binding ? (
                <div className="panel_surface">
                  <div className="panel_header compact_panel_header">
                    <div>
                      <div className="eyebrow">管理员入口</div>
                      <h3>绑定维护与训练会话同步</h3>
                    </div>
                  </div>
                  <div className="archive_notice_stack">
                    <PageNotice
                      tone="info"
                      title="绑定维护已迁移"
                      description="学生与手环的绑定/解绑操作已统一迁移到“设备管理 -> 手环绑定”。训练档案页现在只展示当前绑定结果与绑定历史，不再直接写入绑定关系。"
                    />
                    <PageNotice
                      tone="warning"
                      title="训练会话同步说明"
                      description="后台会在器材解绑事件到达时自动汇聚训练会话；如果你导入了历史数据或怀疑会话未回填，可以在这里手动重新同步当前查询窗口。"
                    />
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
                    {can_aggregate_sessions ? (
                      <Button loading={syncing_sessions} onClick={() => void handle_aggregate_sessions()}>
                        同步训练会话
                      </Button>
                    ) : null}
                  </div>
                </div>
              ) : null}

              <div className="panel_surface">
                <div className="panel_header compact_panel_header">
                  <div>
                    <div className="eyebrow">AI 分析</div>
                    <h3>训练总结入口</h3>
                  </div>
                </div>
                <div className="archive_ai_panel">
                  <div className="archive_ai_summary">
                    <strong>当前分析范围</strong>
                    <span>{build_ai_scope_text(profile, window_key)}</span>
                  </div>
                  <div className="archive_ai_summary">
                    <strong>当前对象</strong>
                    <span>{profile.user.username} {profile.active_binding ? `· 手环 ${profile.active_binding.wristband_id}` : '· 当前无激活手环'}</span>
                  </div>
                  <div className="archive_admin_actions">
                    <Button type="primary" loading={ai_launch_state === 'submitting'} disabled={!can_request_ai} onClick={() => void handle_ai_analyze()}>
                      生成 AI 报告
                    </Button>
                  </div>
                  {!ai_supported_target ? (
                    <PageNotice
                      tone="warning"
                      title="当前仅支持学生训练档案"
                      description="AI 报告将围绕学生训练会话、绑定状态与器材分段生成；管理员和教师账号自身暂不纳入分析对象。"
                    />
                  ) : null}
                  {ai_supported_target && !has_training_data ? (
                    <PageNotice
                      tone="info"
                      title="当前窗口内暂无可分析训练数据"
                      description="请先切换到存在训练会话的时间窗口，或先执行“同步训练会话”补齐历史汇聚结果。"
                    />
                  ) : null}
                  {can_request_ai && ai_launch_state === 'idle' ? (
                    <PageNotice
                      tone="info"
                      title={page_notice_titles.training_archive_ai_ready}
                      description="本阶段前端已接入 AI 触发入口；当前版本会优先校验鉴权、请求参数与预留态返回，为后续真实模型接入保留稳定页面位置。"
                    />
                  ) : null}
                  {ai_launch_state === 'reserved' ? (
                    <PageNotice
                      tone="info"
                      title={page_notice_titles.training_archive_ai_reserved}
                      description={ai_feedback ?? '后台 AI 接口已预留，当前版本尚未接入模型推理与报告落库。'}
                    />
                  ) : null}
                  {ai_launch_state === 'failed' ? (
                    <PageNotice
                      tone="error"
                      title="AI 分析请求失败"
                      description={ai_feedback ?? page_error_fallbacks.training_archive_ai_failed}
                    />
                  ) : null}
                </div>
              </div>
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
                  <PageNotice tone="info" title="当前查询窗口内还没有训练会话" />
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
                              <Tag color={session_status_color(item.status)}>{session_status_label(item.status)}</Tag>
                              <Tag color={item.source === 'aggregated' ? 'cyan' : 'default'}>{session_source_label(item.source)}</Tag>
                              <Tag>{item.wristband_id}</Tag>
                            </Space>
                          }
                          description={render_session_metrics(item)}
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
                              key: `${item.session_id}-summary`,
                              label: '查看会话详情',
                              children: (
                                <div className="archive_session_detail_stack">
                                  <Descriptions column={1} bordered size="small" labelStyle={{ width: 160 }}>
                                    <Descriptions.Item label="开始时间">{format_time(item.started_at)}</Descriptions.Item>
                                    <Descriptions.Item label="结束时间">{item.ended_at ? format_time(item.ended_at) : '--'}</Descriptions.Item>
                                    <Descriptions.Item label="总时长">{format_duration(item.duration_s)}</Descriptions.Item>
                                    <Descriptions.Item label="手环">{item.wristband_id}</Descriptions.Item>
                                    <Descriptions.Item label="器材数">{item.equipment_ids.length}</Descriptions.Item>
                                    <Descriptions.Item label="备注">{item.notes || '--'}</Descriptions.Item>
                                  </Descriptions>
                                  <div className="archive_session_segment_stack">
                                    {item.segments.length > 0 ? item.segments.map((segment) => <div key={`${item.session_id}-${segment.equipment_id}-${segment.started_at}`}>{render_segment_summary(segment)}</div>) : <PageNotice tone="info" title="当前会话还没有器材分段" />}
                                  </div>
                                </div>
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
                  <PageNotice tone="info" title="当前没有学生-手环绑定历史" />
                ) : (
                  <List
                    dataSource={profile.recent_bindings}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <Space wrap>
                              <strong>{item.wristband_id}</strong>
                              <Tag color={item.is_active ? 'green' : 'default'}>{binding_state_label(item.is_active)}</Tag>
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
