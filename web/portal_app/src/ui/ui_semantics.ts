export type NoticeTone = 'info' | 'success' | 'error' | 'warning';

export type StatusBadgeColor = 'green' | 'default' | 'gold' | 'blue' | 'cyan' | 'volcano' | 'purple';

export interface StatusBadgeSpec {
  label: string;
  color: StatusBadgeColor;
  hint?: string;
}

export const device_runtime_status_specs = {
  registered: {
    label: '待上报',
    color: 'gold',
    hint: '设备已注册，但还没有收到设备侧状态上报'
  },
  online: {
    label: '运行中',
    color: 'blue',
    hint: '设备最近一次状态为在线运行'
  },
  bound: {
    label: '已绑定',
    color: 'cyan',
    hint: '设备最近一次状态来自绑定链路'
  },
  active: {
    label: '训练中',
    color: 'green',
    hint: '设备最近一次状态为活跃训练中'
  },
  offline: {
    label: '设备离线',
    color: 'default',
    hint: '设备最近一次状态为离线'
  },
  disconnected: {
    label: '连接中断',
    color: 'volcano',
    hint: '设备最近一次状态为连接中断'
  },
  unknown: {
    label: '未知状态',
    color: 'purple',
    hint: '设备最近一次上报或系统推导出的业务状态'
  }
} satisfies Record<string, StatusBadgeSpec>;
