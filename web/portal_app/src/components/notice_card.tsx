import type { NoticeTone } from '../ui/ui_semantics';

interface NoticeCardProps {
  tone: NoticeTone;
  title: string;
  description?: string | null;
  className?: string;
}

interface NoticeProps {
  tone: NoticeTone;
  title: string;
  description?: string | null;
}

export function NoticeCard({ tone, title, description, className }: NoticeCardProps) {
  const merged_class_name = className ? `notice_card ${tone} ${className}` : `notice_card ${tone}`;
  return (
    <div className={merged_class_name}>
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
    </div>
  );
}

export function PageNotice({ tone, title, description }: NoticeProps) {
  return <NoticeCard tone={tone} title={title} description={description} />;
}

export function InlineNotice({ tone, title, description }: NoticeProps) {
  return <NoticeCard tone={tone} title={title} description={description} className="inline_alert" />;
}
