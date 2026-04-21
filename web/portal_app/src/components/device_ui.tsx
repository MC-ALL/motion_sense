import { Tag } from 'antd';

import type { DeviceConfigPublishResult } from '../types/backend';
import { describe_device_connectivity, describe_device_runtime_status } from '../utils/device_status';
import { InlineNotice } from './notice_card';

function command_result_tone(result: DeviceConfigPublishResult) {
  if (result.status === 'pending') {
    return 'info' as const;
  }
  if (result.status === 'succeeded') {
    return 'success' as const;
  }
  return 'error' as const;
}

export function DeviceConnectivityTag({ online }: { online: boolean }) {
  const connectivity = describe_device_connectivity(online);
  return <Tag color={connectivity.color}>{connectivity.label}</Tag>;
}

export function DeviceRuntimeStatusTag({ status }: { status?: string | null }) {
  const runtime_status = describe_device_runtime_status(status);
  return <Tag color={runtime_status.color}>{runtime_status.label}</Tag>;
}

export function DeviceRuntimeStatusStack({ status }: { status?: string | null }) {
  const runtime_status = describe_device_runtime_status(status);
  return (
    <div className="device_status_stack">
      <Tag color={runtime_status.color}>{runtime_status.label}</Tag>
      {runtime_status.hint ? <span className="device_status_hint">{runtime_status.hint}</span> : null}
    </div>
  );
}

export function ReadonlyTag() {
  return <Tag color="default">只读</Tag>;
}

export function DeviceCommandResultNotice({
  result,
  include_topic = true
}: {
  result: DeviceConfigPublishResult;
  include_topic?: boolean;
}) {
  const description_parts = [`command_id=${result.command_id}`];
  if (include_topic) {
    description_parts.push(`topic=${result.topic}`);
  }
  return (
    <InlineNotice
      tone={command_result_tone(result)}
      title={`命令状态：${result.status}`}
      description={description_parts.join('，')}
    />
  );
}
