import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';

export interface TimeSeriesPoint {
  ts_ms: number;
  value: number;
}

export interface TimeSeriesDefinition {
  name: string;
  color: string;
  points: TimeSeriesPoint[];
}

interface TimeSeriesChartProps {
  title: string;
  subtitle?: string;
  unit?: string;
  series: TimeSeriesDefinition[];
  empty_message?: string;
  header_extra?: ReactNode;
  window_start_ms?: number;
  window_end_ms?: number;
}

const chart_padding = {
  top: 20,
  right: 16,
  bottom: 34,
  left: 46
};

const default_chart_width = 720;
const default_chart_height = 320;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function build_linear_ticks(start: number, end: number, segments: number): number[] {
  if (segments <= 0) {
    return [start, end];
  }
  const step = (end - start) / segments;
  return Array.from({ length: segments + 1 }, (_, index) => start + step * index);
}

function format_time_label(value: number, time_span_ms: number): string {
  const date = new Date(value);
  const pad = (part: number) => String(part).padStart(2, '0');
  if (time_span_ms > 24 * 60 * 60 * 1000) {
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function format_numeric_tick(value: number): string {
  if (Math.abs(value) >= 1000) {
    return value.toFixed(0);
  }
  if (Math.abs(value) >= 100) {
    return value.toFixed(1);
  }
  if (Math.abs(value) >= 10) {
    return value.toFixed(1);
  }
  return value.toFixed(2);
}

function build_line_path(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) {
    return '';
  }
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ');
}

function build_area_path(points: Array<{ x: number; y: number }>, baseline_y: number): string {
  if (points.length === 0) {
    return '';
  }
  const line_path = build_line_path(points);
  const first = points[0];
  const last = points[points.length - 1];
  return `${line_path} L ${last.x.toFixed(2)} ${baseline_y.toFixed(2)} L ${first.x.toFixed(2)} ${baseline_y.toFixed(2)} Z`;
}

function build_svg_id(base_id: string, suffix: string): string {
  return `${base_id}-${suffix}`.replace(/[^a-zA-Z0-9_-]/g, '_');
}

export function TimeSeriesChart({
  title,
  subtitle,
  unit,
  series,
  empty_message = '暂无可展示的数据',
  header_extra,
  window_start_ms,
  window_end_ms
}: TimeSeriesChartProps) {
  const chart_ref = useRef<HTMLDivElement | null>(null);
  const [chart_size, set_chart_size] = useState({ width: default_chart_width, height: default_chart_height });
  const clip_path_id = useId();

  useEffect(() => {
    if (!chart_ref.current) {
      return;
    }

    const update_size = () => {
      if (!chart_ref.current) {
        return;
      }
      const next_width = chart_ref.current.clientWidth || default_chart_width;
      const next_height = chart_ref.current.clientHeight || default_chart_height;
      set_chart_size((current) =>
        current.width === next_width && current.height === next_height
          ? current
          : {
              width: next_width,
              height: next_height
            }
      );
    };

    update_size();
    const observer =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => {
            update_size();
          })
        : null;
    observer?.observe(chart_ref.current);
    window.addEventListener('resize', update_size);

    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', update_size);
    };
  }, []);

  const chart_model = useMemo(() => {
    const width = Math.max(chart_size.width, 320);
    const height = Math.max(chart_size.height, 240);
    const plot_width = Math.max(width - chart_padding.left - chart_padding.right, 120);
    const plot_height = Math.max(height - chart_padding.top - chart_padding.bottom, 120);
    const all_points = series.flatMap((item) => item.points).filter((point) => Number.isFinite(point.ts_ms) && Number.isFinite(point.value));
    const latest_point_ts = all_points.length > 0 ? Math.max(...all_points.map((point) => point.ts_ms)) : undefined;
    const oldest_point_ts = all_points.length > 0 ? Math.min(...all_points.map((point) => point.ts_ms)) : undefined;
    const preferred_span_ms =
      window_start_ms !== undefined && window_end_ms !== undefined
        ? Math.max(window_end_ms - window_start_ms, 0)
        : latest_point_ts !== undefined && oldest_point_ts !== undefined
          ? Math.max(latest_point_ts - oldest_point_ts, 0)
          : 0;

    let effective_window_start = window_start_ms;
    let effective_window_end = window_end_ms;

    if (latest_point_ts !== undefined && oldest_point_ts !== undefined) {
      if (preferred_span_ms > 0) {
        effective_window_end = latest_point_ts;
        effective_window_start = Math.max(latest_point_ts - preferred_span_ms, oldest_point_ts);
      } else {
        effective_window_start = oldest_point_ts - 1000;
        effective_window_end = latest_point_ts + 1000;
      }
    } else if (effective_window_start === undefined || effective_window_end === undefined) {
      const now = Date.now();
      effective_window_end = now;
      effective_window_start = now - Math.max(preferred_span_ms, 60 * 1000);
    }

    if (effective_window_end <= effective_window_start) {
      effective_window_end = effective_window_start + 1000;
    }

    const visible_series = series
      .map((item) => ({
        ...item,
        points: item.points
          .slice()
          .sort((left, right) => left.ts_ms - right.ts_ms)
          .filter((point) => point.ts_ms >= effective_window_start && point.ts_ms <= effective_window_end)
      }))
      .filter((item) => item.points.length > 0);

    const visible_values = visible_series.flatMap((item) => item.points.map((point) => point.value));
    const min_value = visible_values.length > 0 ? Math.min(...visible_values) : 0;
    const max_value = visible_values.length > 0 ? Math.max(...visible_values) : 100;
    const y_span = Math.max(max_value - min_value, 1);
    const y_padding = y_span * 0.12;
    const y_min = min_value - y_padding;
    const y_max = max_value + y_padding;
    const y_safe_span = Math.max(y_max - y_min, 1);
    const x_span = Math.max(effective_window_end - effective_window_start, 1);

    const x_scale = (ts_ms: number) => chart_padding.left + ((ts_ms - effective_window_start) / x_span) * plot_width;
    const y_scale = (value: number) => chart_padding.top + (1 - (value - y_min) / y_safe_span) * plot_height;

    const x_ticks = build_linear_ticks(effective_window_start, effective_window_end, 5);
    const y_ticks = build_linear_ticks(y_min, y_max, 4);
    const baseline_y = chart_padding.top + plot_height;

    return {
      width,
      height,
      plot_width,
      plot_height,
      baseline_y,
      x_ticks,
      y_ticks,
      y_min,
      y_max,
      x_span,
      effective_window_start,
      effective_window_end,
      visible_series: visible_series.map((item) => ({
        ...item,
        plotted_points: item.points.map((point) => ({
          ...point,
          x: clamp(x_scale(point.ts_ms), chart_padding.left, chart_padding.left + plot_width),
          y: clamp(y_scale(point.value), chart_padding.top, chart_padding.top + plot_height)
        }))
      })),
      has_data: visible_series.length > 0
    };
  }, [chart_size.height, chart_size.width, series, window_end_ms, window_start_ms]);

  return (
    <div className="chart_panel_surface">
      <div className="panel_header compact_panel_header chart_panel_header">
        <div className="chart_header_content">
          <div className="eyebrow">时序图</div>
          <h3>{title}</h3>
          {subtitle ? <div className="panel_meta_text">{subtitle}</div> : null}
        </div>
        <div className="chart_header_side">
          <div className="chart_legend_list">
            {series.map((item) => (
              <span key={item.name} className="chart_legend_item">
                <span className="chart_legend_swatch" style={{ backgroundColor: item.color }} />
                <span>{item.name}</span>
              </span>
            ))}
          </div>
          {header_extra ? <div className="chart_header_extra">{header_extra}</div> : null}
        </div>
      </div>
      <div className="chart_shell wide_chart_shell" ref={chart_ref}>
        <svg className="svg_chart" viewBox={`0 0 ${chart_model.width} ${chart_model.height}`} preserveAspectRatio="none" role="img" aria-label={title}>
          <defs>
            {chart_model.visible_series.map((item) => (
              <linearGradient key={item.name} id={build_svg_id(clip_path_id, `${item.name}-fill`)} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={item.color} stopOpacity="0.24" />
                <stop offset="100%" stopColor={item.color} stopOpacity="0.02" />
              </linearGradient>
            ))}
            <clipPath id={clip_path_id}>
              <rect
                x={chart_padding.left}
                y={chart_padding.top}
                width={chart_model.plot_width}
                height={chart_model.plot_height}
                rx="16"
                ry="16"
              />
            </clipPath>
          </defs>

          <rect
            x={chart_padding.left}
            y={chart_padding.top}
            width={chart_model.plot_width}
            height={chart_model.plot_height}
            rx="16"
            ry="16"
            className="svg_chart_backdrop"
          />

          {chart_model.y_ticks.map((tick) => {
            const y = chart_padding.top + (1 - (tick - chart_model.y_min) / Math.max(chart_model.y_max - chart_model.y_min, 1)) * chart_model.plot_height;
            return (
              <g key={`y-${tick}`}>
                <line x1={chart_padding.left} y1={y} x2={chart_padding.left + chart_model.plot_width} y2={y} className="svg_chart_grid" />
                <text x={chart_padding.left - 10} y={y + 4} textAnchor="end" className="svg_chart_axis_text">
                  {format_numeric_tick(tick)}
                </text>
              </g>
            );
          })}

          {chart_model.x_ticks.map((tick) => {
            const x = chart_padding.left + ((tick - chart_model.effective_window_start) / Math.max(chart_model.x_span, 1)) * chart_model.plot_width;
            return (
              <g key={`x-${tick}`}>
                <line x1={x} y1={chart_padding.top} x2={x} y2={chart_padding.top + chart_model.plot_height} className="svg_chart_grid vertical" />
                <text x={x} y={chart_padding.top + chart_model.plot_height + 20} textAnchor="middle" className="svg_chart_axis_text">
                  {format_time_label(tick, chart_model.x_span)}
                </text>
              </g>
            );
          })}

          <g clipPath={`url(#${clip_path_id})`}>
            {chart_model.visible_series.map((item) => {
              const path_points = item.plotted_points.map((point) => ({ x: point.x, y: point.y }));
              const line_path = build_line_path(path_points);
              const area_path = build_area_path(path_points, chart_model.baseline_y);
              return (
                <g key={item.name}>
                  {area_path ? <path d={area_path} fill={`url(#${build_svg_id(clip_path_id, `${item.name}-fill`)})`} /> : null}
                  {line_path ? <path d={line_path} fill="none" stroke={item.color} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" /> : null}
                  {item.plotted_points.length > 0 ? (
                    <circle
                      cx={item.plotted_points[item.plotted_points.length - 1].x}
                      cy={item.plotted_points[item.plotted_points.length - 1].y}
                      r="4.5"
                      fill={item.color}
                      className="svg_chart_marker"
                    />
                  ) : null}
                </g>
              );
            })}
          </g>
        </svg>

        {!chart_model.has_data ? <div className="chart_empty_state">{empty_message}</div> : null}
      </div>
      <div className="chart_footer_meta">
        <span>{format_time_label(chart_model.effective_window_start, chart_model.x_span)}</span>
        <span>{unit ? `单位：${unit}` : '滚动窗口显示'}</span>
        <span>{format_time_label(chart_model.effective_window_end, chart_model.x_span)}</span>
      </div>
    </div>
  );
}
