import type { AuthUser } from '../types/backend';

type ScopeUser = Pick<AuthUser, 'role' | 'gym_ids' | 'device_ids'>;

function join_items(items: string[]): string {
  return items.length > 0 ? items.join('、') : '未配置';
}

export function describe_user_scope(user?: ScopeUser | null): string {
  if (!user) {
    return '未登录';
  }

  if (user.role === 'admin') {
    return '全部场馆与设备';
  }

  if (user.role === 'teacher') {
    return `场馆：${join_items(user.gym_ids)}；设备：${join_items(user.device_ids)}`;
  }

  return `设备：${join_items(user.device_ids)}`;
}
