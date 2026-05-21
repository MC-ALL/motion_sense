export function normalize_equipment_binding_id(value: unknown, relayed_by?: unknown): string | null {
  if (is_valid_equipment_id(relayed_by) && is_unstable_equipment_id(value)) {
    return relayed_by;
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed === '' || trimmed === '255' || trimmed.toLowerCase() === 'none') {
      return null;
    }
    return trimmed;
  }

  if (typeof value === 'number') {
    if (value === 255) {
      return null;
    }
    return `eq-${String(value).padStart(3, '0')}`;
  }

  return null;
}

export function format_equipment_binding_id(value: unknown, relayed_by?: unknown): string {
  return normalize_equipment_binding_id(value, relayed_by) ?? '未绑定';
}

function is_valid_equipment_id(value: unknown): value is string {
  return typeof value === 'string' && value.startsWith('eq-') && value.length > 3;
}

function is_unstable_equipment_id(value: unknown): boolean {
  if (value === null || value === undefined) {
    return true;
  }
  if (typeof value === 'number') {
    return true;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed === '' || trimmed === '255' || trimmed.toLowerCase() === 'none' || /^\d+$/.test(trimmed);
  }
  return false;
}
