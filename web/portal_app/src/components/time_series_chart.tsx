import { useEffect, useRef } from 'react';

import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { init, use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

export interface TimeSeriesPoint {
  label: string;
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
}

export function TimeSeriesChart({
  title,
  subtitle,
  unit,
  series,
  empty_message = '暂无可展示的数据'
}: TimeSeriesChartProps) {
  const chart_ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!chart_ref.current) {
      return;
    }

    const chart = init(chart_ref.current);
    const labels = Array.from(new Set(series.flatMap((item) => item.points.map((point) => point.label))));

    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: number) => `${value}${unit ? ` ${unit}` : ''}`
      },
      legend: {
        top: 0,
        textStyle: { color: '#4a645f' }
      },
      grid: {
        left: 32,
        right: 16,
        top: 48,
        bottom: 28
      },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: false,
        axisLabel: { color: '#708682' },
        axisLine: { lineStyle: { color: 'rgba(18, 91, 86, 0.18)' } }
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#708682' },
        splitLine: { lineStyle: { color: 'rgba(18, 91, 86, 0.08)' } }
      },
      series: series.map((item) => ({
        name: item.name,
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: labels.map((label) => item.points.find((point) => point.label === label)?.value ?? null),
        lineStyle: { width: 3, color: item.color },
        itemStyle: { color: item.color },
        areaStyle: {
          color: `${item.color}22`
        }
      })),
      graphic:
        labels.length === 0
          ? {
              type: 'text',
              left: 'center',
              top: 'middle',
              style: {
                text: empty_message,
                fill: '#708682',
                fontSize: 14
              }
            }
          : undefined
    });

    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chart.dispose();
    };
  }, [empty_message, series, unit]);

  return (
    <div className="chart_panel_surface">
      <div className="panel_header compact_panel_header">
        <div>
          <div className="eyebrow">时序图</div>
          <h3>{title}</h3>
        </div>
        {subtitle ? <span className="panel_meta_text">{subtitle}</span> : null}
      </div>
      <div className="chart_shell wide_chart_shell" ref={chart_ref} />
    </div>
  );
}
