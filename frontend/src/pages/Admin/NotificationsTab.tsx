import { useState, type FormEvent } from 'react';
import { adminApi, ApiError, useApi, type AdminNotification } from '../../api';
import { LoadError } from '../../components/app/LoadError';
import {
  Alert,
  Badge,
  Button,
  Card,
  Select,
  Stack,
  Table,
  TextArea,
  TextField,
  useToast,
  type Column,
} from '../../components/ui';
import { formatDateTime } from '../../lib/format';
import { useScrollToFormError } from '../../lib/useScrollToFormError';

const EVERYONE = 'all';

export function NotificationsTab() {
  const toast = useToast();
  const participants = useApi(() => adminApi.participants(), []);
  const list = useApi(() => adminApi.notifications(), []);
  const [target, setTarget] = useState(EVERYONE);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formRef] = useScrollToFormError(errors, formError);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!title.trim()) errs.title = '참가자에게 보일 제목을 적어 주세요.';
    if (!body.trim()) errs.body = '내용을 적어 주세요.';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    setFormError(null);
    try {
      const sent = await adminApi.createNotification({
        title: title.trim(),
        body: body.trim(),
        participant_id: target === EVERYONE ? null : Number(target),
      });
      toast.success('알림을 보냈습니다', sent.nickname ? `${sent.nickname}에게` : '전체 참가자에게');
      setTitle('');
      setBody('');
      void list.refetch();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : '알림을 보내지 못했습니다.');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (n: AdminNotification) => {
    if (!window.confirm(`'${n.title}' 알림을 지울까요? 참가자 화면에서도 사라집니다.`)) return;
    try {
      await adminApi.deleteNotification(n.id);
      toast.success('알림을 지웠습니다', n.title);
      void list.refetch();
    } catch (err) {
      toast.error('알림을 지우지 못했습니다', err instanceof ApiError ? err.message : undefined);
    }
  };

  const columns: Column<AdminNotification>[] = [
    { key: 'created', header: '보낸 시각', nowrap: true, render: (n) => formatDateTime(n.created_at) },
    {
      key: 'target',
      header: '받는 사람',
      nowrap: true,
      render: (n) =>
        n.participant_id == null ? <Badge tone="info">전체</Badge> : `#${n.participant_id} ${n.nickname ?? ''}`,
    },
    { key: 'title', header: '제목', render: (n) => n.title },
    { key: 'read', header: '읽음', numeric: true, nowrap: true, render: (n) => `${n.read_count} / ${n.recipients}` },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (n) => (
        <Button variant="ghost" size="sm" onClick={() => void remove(n)}>
          지우기
        </Button>
      ),
    },
  ];

  const options = [
    { value: EVERYONE, label: '전체 참가자' },
    ...(participants.data ?? []).map((p) => ({ value: String(p.id), label: `#${p.id} ${p.nickname}` })),
  ];

  return (
    <Stack gap={6}>
      <Card
        title="알림 보내기"
        description="참가자 메인 화면의 '알림'에 쌓입니다. 참가자마다 읽은·안 읽은 알림이 따로 표시되고, 펼치면 읽음으로 바뀝니다. 전체 알림은 나중에 가입한 참가자에게도 보입니다. 내용의 줄바꿈은 그대로 보입니다."
      >
        <form ref={formRef} onSubmit={submit} noValidate>
          <Stack gap={4}>
            {formError && (
              <Alert tone="danger" title="알림을 보내지 못했습니다">
                {formError}
              </Alert>
            )}
            <Select label="받는 사람" value={target} onChange={setTarget} options={options} />
            <TextField
              label="제목"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={120}
              placeholder="예: 매수 한도 오류 안내와 보상"
              error={errors.title}
              required
            />
            <TextArea
              label="내용"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={2000}
              rows={8}
              error={errors.body}
              required
            />
            <div>
              <Button type="submit" loading={saving}>
                보내기
              </Button>
            </div>
          </Stack>
        </form>
      </Card>
      <Card title="보낸 알림" description="읽음은 '읽은 사람 / 받는 사람'입니다. 전체 알림의 받는 사람은 지금 참가자 수입니다.">
        {list.error ? (
          <LoadError error={list.error} onRetry={list.refetch} what="보낸 알림" />
        ) : (
          <Table
            columns={columns}
            rows={list.data ?? []}
            rowKey={(n) => n.id}
            loading={list.loading}
            empty="아직 보낸 알림이 없습니다."
          />
        )}
      </Card>
    </Stack>
  );
}
