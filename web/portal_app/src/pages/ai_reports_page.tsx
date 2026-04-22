import { useEffect, useMemo, useState } from 'react';

import type { AxiosError } from 'axios';
import { Button, Descriptions, List, Select, Space, Spin, Tag } from 'antd';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import {
  fetch_ai_report_detail,
  fetch_ai_reports,
  retry_ai_report,
  fetch_user_wristband_bindings,
  fetch_users,
  fetch_workout_sessions
} from '../api/backend_client';
import { AuthRequiredState } from '../components/auth_required_state';
import { PageNotice } from '../components/notice_card';
import { use_auth_store } from '../store/auth_store';
import type { AiReportDetail, AiReportSummary, ReservedApiResponse } from '../types/backend';
import { page_error_fallbacks, page_notice_titles } from '../ui/message_catalog';
import { format_time } from '../utils/time';

type WindowKey = '7d' | '30d' | 'all';

const window_options: Array<{ label: string; value: WindowKey }> = [
  { label: '近 7 天', value: '7d' },
  { label: '近 30 天', value: '30d' },
  { label: '全部', value: 'all' }
];

const status_options = [
  { label: '全部状态', value: 'all' },
  { label: '排队中', value: 'queued' },
  { label: '生成中', value: 'generating' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' }
];

const active_report_statuses = new Set(['queued', 'generating']);

function build_start_time(window_key: WindowKey): string | undefined {
  if (window_key === 'all') {
    return undefined;
  }
  const now = Date.now();
  const offset_ms = window_key === '7d' ? 7 * 24 * 60 * 60 * 1000 : 30 * 24 * 60 * 60 * 1000;
  return new Date(now - offset_ms).toISOString();
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

function read_reserved_response(error: unknown): ReservedApiResponse | null {
  const response = (error as AxiosError<{ detail?: ReservedApiResponse }>).response;
  const detail = response?.data?.detail;
  if (response?.status === 501 && detail && typeof detail === 'object' && detail.status === 'reserved') {
    return detail;
  }
  return null;
}

function status_color(status: string): string {
  if (status === 'completed') {
    return 'green';
  }
  if (status === 'queued') {
    return 'blue';
  }
  if (status === 'generating') {
    return 'cyan';
  }
  if (status === 'failed') {
    return 'red';
  }
  return 'default';
}

function status_label(status: string): string {
  if (status === 'completed') {
    return '已完成';
  }
  if (status === 'queued') {
    return '排队中';
  }
  if (status === 'generating') {
    return '生成中';
  }
  if (status === 'failed') {
    return '失败';
  }
  return status;
}

function status_notice_tone(status: string): 'info' | 'success' | 'error' {
  if (status === 'completed') {
    return 'success';
  }
  if (status === 'failed') {
    return 'error';
  }
  return 'info';
}

function status_notice_description(report: AiReportDetail): string {
  if (report.status === 'queued') {
    return '报告已入队，后台会自动开始生成内容。';
  }
  if (report.status === 'generating') {
    return '报告正在生成，页面会自动刷新当前状态。';
  }
  if (report.status === 'failed') {
    return report.error_message || '报告生成失败，请检查配置或稍后重试。';
  }
  return '报告已生成完成，可继续查看摘要、观察结论和训练建议。';
}

export function AiReportsPage() {
  const navigate = useNavigate();
  const { report_id } = useParams<{ report_id?: string }>();
  const [search_params, set_search_params] = useSearchParams();
  const session = use_auth_store((state) => state.session);
  const [loading, set_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [reserved_response, set_reserved_response] = useState<ReservedApiResponse | null>(null);
  const [reports, set_reports] = useState<AiReportSummary[]>([]);
  const [report_detail, set_report_detail] = useState<AiReportDetail | null>(null);
  const [candidate_usernames, set_candidate_usernames] = useState<string[]>([]);
  const [refresh_tick, set_refresh_tick] = useState(0);
  const [retrying, set_retrying] = useState(false);

  const can_switch_user = session?.user.role === 'admin' || session?.user.role === 'teacher';
  const selected_window = (search_params.get('window') as WindowKey | null) ?? '30d';
  const selected_status = search_params.get('status') ?? 'all';
  const selected_username = can_switch_user
    ? search_params.get('username') ?? ''
    : session?.user.username ?? '';

  useEffect(() => {
    if (!session || !can_switch_user) {
      set_candidate_usernames(session?.user.username ? [session.user.username] : []);
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
        if (current_session.user.username) {
          usernames.add(current_session.user.username);
        }
        if (mounted) {
          set_candidate_usernames(Array.from(usernames).sort((left, right) => left.localeCompare(right)));
        }
      } catch {
        if (mounted) {
          set_candidate_usernames(current_session.user.username ? [current_session.user.username] : []);
        }
      }
    }
    void load_candidates();
    return () => {
      mounted = false;
    };
  }, [can_switch_user, session]);

  useEffect(() => {
    if (!session) {
      set_loading(false);
      set_reports([]);
      set_report_detail(null);
      set_error(null);
      set_reserved_response(null);
      return;
    }

    let mounted = true;
    async function load_page() {
      set_loading(true);
      setErrorState();
      try {
        if (report_id) {
          const detail = await fetch_ai_report_detail(report_id);
          if (!mounted) {
            return;
          }
          set_report_detail(detail);
          set_reports([]);
          return;
        }

        const list = await fetch_ai_reports({
          user_id: selected_username || undefined,
          status: selected_status === 'all' ? undefined : selected_status,
          start: build_start_time(selected_window),
          end: new Date().toISOString()
        });
        if (!mounted) {
          return;
        }
        set_reports(list);
        set_report_detail(null);
      } catch (load_error) {
        if (!mounted) {
          return;
        }
        const reserved = read_reserved_response(load_error);
        if (reserved) {
          set_reserved_response(reserved);
          set_error(null);
          set_reports([]);
          set_report_detail(null);
          return;
        }
        set_error(describe_error(load_error, page_error_fallbacks.ai_reports_load_failed));
      } finally {
        if (mounted) {
          set_loading(false);
        }
      }
    }

    void load_page();
    return () => {
      mounted = false;
    };
  }, [refresh_tick, report_id, search_params, selected_status, selected_username, selected_window, session]);

  useEffect(() => {
    if (!session || reserved_response) {
      return;
    }

    const should_poll_detail = Boolean(report_detail && active_report_statuses.has(report_detail.status));
    const should_poll_list = !report_id && reports.some((item) => active_report_statuses.has(item.status));
    if (!should_poll_detail && !should_poll_list) {
      return;
    }

    const timer = window.setTimeout(() => {
      set_refresh_tick((value) => value + 1);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [report_detail, report_id, reports, reserved_response, session]);

  function setErrorState() {
    set_error(null);
    set_reserved_response(null);
  }

  function update_filters(next: {
    username?: string;
    window?: WindowKey;
    status?: string;
  }) {
    const params = new URLSearchParams(search_params);
    const next_username = next.username ?? selected_username;
    const next_window = next.window ?? selected_window;
    const next_status = next.status ?? selected_status;

    if (can_switch_user && next_username) {
      params.set('username', next_username);
    } else {
      params.delete('username');
    }

    params.set('window', next_window);

    if (next_status === 'all') {
      params.delete('status');
    } else {
      params.set('status', next_status);
    }
    set_search_params(params);
  }

  async function handle_retry_report() {
    if (!report_detail || retrying) {
      return;
    }
    set_retrying(true);
    setErrorState();
    try {
      const next_report = await retry_ai_report(report_detail.report_id);
      navigate(`/ai-reports/${next_report.report_id}`);
      set_refresh_tick((value) => value + 1);
    } catch (retry_error) {
      set_error(describe_error(retry_error, page_error_fallbacks.ai_reports_retry_failed));
    } finally {
      set_retrying(false);
    }
  }

  const list_scope_text = useMemo(() => {
    const current_window = window_options.find((item) => item.value === selected_window);
    return [
      can_switch_user ? `学生 ${selected_username || '全部可见学生'}` : `学生 ${session?.user.username ?? '--'}`,
      current_window?.label ?? '近 30 天',
      status_options.find((item) => item.value === selected_status)?.label ?? '全部状态'
    ].join(' · ');
  }, [can_switch_user, selected_status, selected_username, selected_window, session?.user.username]);

  if (!session) {
    return (
      <AuthRequiredState
        eyebrow="06 网页端 / AI 报告"
        title="登录后可查看 AI 报告"
        description="AI 报告页会沿用当前后台账号的角色边界，仅展示本人或当前账号有权限查看的学生报告。"
      />
    );
  }

  return (
    <section className="page_shell">
      <section className="hero_banner compact_hero_banner">
        <div>
          <div className="eyebrow">06 网页端 / AI 报告</div>
          <h1>{report_id ? `AI 报告详情：${report_id}` : 'AI 报告历史'}</h1>
          <p>{report_id ? '查看单份训练分析报告的元信息、摘要区块与后续建议落位。' : '集中查看训练分析报告历史，后续用于老师筛选学生与回看阶段性训练结论。'}</p>
        </div>
        <Space wrap>
          <Button onClick={() => navigate('/training-archive')}>返回训练档案</Button>
          {!report_id ? (
            <Button onClick={() => update_filters({ username: session.user.username })}>查看我的报告</Button>
          ) : (
            <>
              {report_detail && (report_detail.status === 'failed' || report_detail.status === 'completed') ? (
                <Button type="primary" loading={retrying} onClick={() => void handle_retry_report()}>
                  {report_detail.status === 'failed' ? '重新生成' : '再次生成'}
                </Button>
              ) : null}
              <Button onClick={() => navigate('/ai-reports')}>返回列表</Button>
            </>
          )}
        </Space>
      </section>

      {!report_id ? (
        <div className="panel_surface archive_filter_panel">
          <Space wrap align="end">
            {can_switch_user ? (
              <Select
                showSearch
                allowClear
                optionFilterProp="label"
                placeholder="选择学生账号"
                value={selected_username || undefined}
                style={{ minWidth: 260 }}
                options={candidate_usernames.map((username) => ({
                  value: username,
                  label: username === session.user.username ? `${username} · 我的账号` : username
                }))}
                onChange={(value) => update_filters({ username: value ?? '' })}
              />
            ) : null}
            <Select
              style={{ minWidth: 160 }}
              value={selected_status}
              options={status_options}
              onChange={(value) => update_filters({ status: value })}
            />
            <Space.Compact>
              {window_options.map((item) => (
                <Button
                  key={item.value}
                  type={selected_window === item.value ? 'primary' : 'default'}
                  onClick={() => update_filters({ window: item.value })}
                >
                  {item.label}
                </Button>
              ))}
            </Space.Compact>
          </Space>
        </div>
      ) : null}

      {error ? <PageNotice tone="error" title={page_notice_titles.ai_reports_error} description={error} /> : null}
      {loading ? <div className="panel_surface loading_surface"><Spin size="large" /></div> : null}

      {!loading && reserved_response ? (
        <div className="content_grid">
          <div className="left_column">
            <div className="panel_surface">
              <div className="panel_header compact_panel_header">
                <div>
                  <div className="eyebrow">当前状态</div>
                  <h3>{report_id ? '详情接口已预留' : '列表接口已预留'}</h3>
                </div>
              </div>
              <PageNotice
                tone="info"
                title={page_notice_titles.ai_reports_reserved}
                description={reserved_response.detail}
              />
            </div>
          </div>
          <div className="right_column">
            <div className="panel_surface">
              <div className="panel_header compact_panel_header">
                <div>
                  <div className="eyebrow">预期视图</div>
                  <h3>{report_id ? '详情页落位结构' : '列表页落位结构'}</h3>
                </div>
              </div>
              {!report_id ? (
                <div className="archive_notice_stack">
                  <div className="archive_ai_summary">
                    <strong>当前筛选范围</strong>
                    <span>{list_scope_text}</span>
                  </div>
                  <PageNotice
                    tone="info"
                    title="列表页后续会展示什么"
                    description="后端接入后，这里会展示报告状态、学生、时间范围、生成时间和摘要标题，并支持跳转详情页。"
                  />
                </div>
              ) : (
                <div className="archive_notice_stack">
                  <div className="archive_ai_summary">
                    <strong>当前报告 ID</strong>
                    <span>{report_id}</span>
                  </div>
                  <PageNotice
                    tone="info"
                    title="详情页后续会展示什么"
                    description="后端接入后，这里会落位报告头部、训练总结、亮点与风险、建议动作，以及引用的训练会话证据。"
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {!loading && !reserved_response && !report_id ? (
        <div className="panel_surface">
          <div className="panel_header compact_panel_header">
            <div>
              <div className="eyebrow">报告列表</div>
              <h3>历史报告</h3>
            </div>
          </div>
          {reports.length === 0 ? (
            <PageNotice
              tone="info"
              title="当前筛选范围内还没有 AI 报告"
              description="可以先回到训练档案页发起分析，后续这里将用于统一回看历史报告。"
            />
          ) : (
            <List
              itemLayout="vertical"
              dataSource={reports}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button key={`${item.report_id}-detail`} type="link" onClick={() => navigate(`/ai-reports/${item.report_id}`)}>
                      查看详情
                    </Button>
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <strong>{item.summary_title || item.report_id}</strong>
                        <Tag color={status_color(item.status)}>{status_label(item.status)}</Tag>
                        <Tag>{item.user_id}</Tag>
                      </Space>
                    }
                    description={`分析窗口 ${format_time(item.start)} - ${format_time(item.end)}`}
                  />
                </List.Item>
              )}
            />
          )}
        </div>
      ) : null}

      {!loading && !reserved_response && report_id && report_detail ? (
        <div className="content_grid">
          <div className="left_column">
            <div className="panel_surface">
              <div className="panel_header compact_panel_header">
                <div>
                  <div className="eyebrow">报告概览</div>
                  <h3>基础信息</h3>
                </div>
              </div>
              <Descriptions column={1} bordered size="middle" labelStyle={{ width: 160 }}>
                <Descriptions.Item label="报告 ID">{report_detail.report_id}</Descriptions.Item>
                <Descriptions.Item label="学生">{report_detail.user_id}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color={status_color(report_detail.status)}>{status_label(report_detail.status)}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="分析窗口">{`${format_time(report_detail.start)} - ${format_time(report_detail.end)}`}</Descriptions.Item>
                <Descriptions.Item label="创建时间">{format_time(report_detail.created_at)}</Descriptions.Item>
                <Descriptions.Item label="完成时间">{report_detail.finished_at ? format_time(report_detail.finished_at) : '--'}</Descriptions.Item>
              </Descriptions>
            </div>
          </div>
          <div className="right_column">
            <div className="panel_surface">
              <div className="panel_header compact_panel_header">
                <div>
                  <div className="eyebrow">结构化内容</div>
                  <h3>摘要与建议</h3>
                </div>
              </div>
              <div className="archive_notice_stack">
                <PageNotice
                  tone={status_notice_tone(report_detail.status)}
                  title={`当前状态：${status_label(report_detail.status)}`}
                  description={status_notice_description(report_detail)}
                />
                <div className="archive_ai_summary">
                  <strong>摘要</strong>
                  <span>{report_detail.summary || '当前报告还没有可展示的摘要内容。'}</span>
                </div>
                <Descriptions column={1} bordered size="small" labelStyle={{ width: 160 }}>
                  <Descriptions.Item label="证据会话">
                    {report_detail.evidence_session_ids.length > 0 ? report_detail.evidence_session_ids.join('，') : '--'}
                  </Descriptions.Item>
                  <Descriptions.Item label="错误原因">{report_detail.error_message || '--'}</Descriptions.Item>
                </Descriptions>
                <div className="archive_ai_summary">
                  <strong>观察结论</strong>
                  {report_detail.insights.length > 0 ? (
                    <List
                      size="small"
                      dataSource={report_detail.insights}
                      renderItem={(item) => <List.Item>{item}</List.Item>}
                    />
                  ) : (
                    <span>当前还没有结构化观察结论。</span>
                  )}
                </div>
                <div className="archive_ai_summary">
                  <strong>后续建议</strong>
                  {report_detail.recommendations.length > 0 ? (
                    <List
                      size="small"
                      dataSource={report_detail.recommendations}
                      renderItem={(item) => <List.Item>{item}</List.Item>}
                    />
                  ) : (
                    <span>当前还没有结构化建议。</span>
                  )}
                </div>
                {report_detail.raw_markdown ? (
                  <div className="archive_ai_summary">
                    <strong>原始报告</strong>
                    <pre className="archive_ai_raw_markdown">{report_detail.raw_markdown}</pre>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
