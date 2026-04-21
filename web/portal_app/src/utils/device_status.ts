import type { StatusBadgeSpec } from '../ui/ui_semantics';
import { device_runtime_status_specs } from '../ui/ui_semantics';

function normalize_runtime_status(status?: string | null): string {
  return (status ?? '').trim().toLowerCase();
}

export function describe_device_connectivity(online: boolean): StatusBadgeSpec {
  if (online) {
    return { label: '已连通', color: 'green' };
  }
  return { label: '未连通', color: 'default' };
}

export function describe_device_runtime_status(status?: string | null): StatusBadgeSpec {
  const normalized = normalize_runtime_status(status);
  if (normalized in device_runtime_status_specs) {
    return device_runtime_status_specs[normalized as keyof typeof device_runtime_status_specs];
  }
  return {
    ...device_runtime_status_specs.unknown,
    label: status && status.trim() ? status : device_runtime_status_specs.unknown.label
  };
}

export function is_device_runtime_active(status?: string | null, fallback_status?: string | null): boolean {
  const primary = normalize_runtime_status(status);
  const fallback = normalize_runtime_status(fallback_status);
  return primary === 'active' || fallback === 'active';
}
