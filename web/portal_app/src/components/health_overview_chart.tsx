import { useEffect, useRef } from 'react';

import { PieChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { init, use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

import type { ModuleHealthSummary } from '../types/ops';

use([PieChart, TooltipComponent, CanvasRenderer]);

export function HealthOverviewChart({ summaries }: { summaries: ModuleHealthSummary[] }) {
  const chart_ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!chart_ref.current) {
      return;
    }

    const chart = init(chart_ref.current);
    const healthy = summaries.filter((item) => item.health_status === 'healthy').length;
    const degraded = summaries.filter((item) => item.health_status === 'degraded').length;
    const offline = summaries.filter((item) => item.health_status === 'offline').length;

    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: ['58%', '82%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderColor: '#f3efe6',
            borderWidth: 6
          },
          label: {
            color: '#2c3f3a',
            formatter: '{b}\n{c}'
          },
          data: [
            { value: healthy, name: '健康', itemStyle: { color: '#2d8f5b' } },
            { value: degraded, name: '降级', itemStyle: { color: '#d97706' } },
            { value: offline, name: '离线', itemStyle: { color: '#c2410c' } }
          ]
        }
      ]
    });

    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chart.dispose();
    };
  }, [summaries]);

  return <div className="chart_shell" ref={chart_ref} />;
}
