import { useEffect, useRef, useState } from 'react';
import { adminApi, ApiError, type AdminNotificationDetail, type NotificationReader } from '../../api';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  KeyValueList,
  Modal,
  Skeleton,
  Stack,
  Table,
  Text,
  TextArea,
  TextField,
  useToast,
  type Column,
} from '../../components/ui';
import { formatDateTime } from '../../lib/format';

const READER_COLUMNS: Column<NotificationReader>[] = [
  { key: 'who', header: '참가자', render: (r) => `#${r.participant_id} ${r.nickname}` },
  {
    key: 'read',
    header: '읽은 시각',
    nowrap: true,
    render: (r) => (r.read_at ? formatDateTime(r.read_at) : <Badge tone="neutral">안 읽음</Badge>),
  },
];

/** 보낸 알림 하나의 내용과 읽은 사람 목록. '수정'으로 제목·내용을 고친다. */
export function NotificationDetailModal({
  id,
  onClose,
  onChanged,
}: {
  id: number | null;
  onClose: () => void;
  /** 고친 뒤 목록을 새로 불러오게 알린다. */
  onChanged: () => void;
}) {
  const toast = useToast();
  const [detail, setDetail] = useState<AdminNotificationDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [resetReads, setResetReads] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // 지금 열려 있는 알림. 저장 응답이 오기 전에 창을 닫거나 다른 알림을 열었으면 그 응답으로 화면을 덮지 않는다.
  const currentId = useRef(id);
  currentId.current = id;

  useEffect(() => {
    setDetail(null);
    setLoadError(null);
    setEditing(false);
    setSaveError(null);
    if (id == null) return;
    let alive = true;
    adminApi.notification(id).then(
      (d) => alive && setDetail(d),
      (err) => alive && setLoadError(err instanceof ApiError ? err.message : '알림을 불러오지 못했습니다.'),
    );
    return () => {
      alive = false;
    };
  }, [id]);

  const startEdit = () => {
    if (!detail) return;
    setTitle(detail.title);
    setBody(detail.body);
    setResetReads(false);
    setSaveError(null);
    setEditing(true);
  };

  const save = async () => {
    if (!detail) return;
    if (!title.trim() || !body.trim()) {
      setSaveError('제목과 내용을 모두 적어 주세요.');
      return;
    }
    const savingId = detail.id;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await adminApi.updateNotification(savingId, {
        title: title.trim(),
        body: body.trim(),
        reset_reads: resetReads,
      });
      toast.success('알림을 고쳤습니다', resetReads ? '받는 사람 모두에게 다시 새 알림으로 보입니다.' : saved.title);
      onChanged();
      if (currentId.current !== savingId) return;
      setDetail(saved);
      setEditing(false);
    } catch (err) {
      if (currentId.current === savingId)
        setSaveError(err instanceof ApiError ? err.message : '알림을 고치지 못했습니다.');
    } finally {
      setSaving(false);
    }
  };

  const unreadCount = detail ? detail.readers.filter((r) => r.read_at == null).length : 0;

  return (
    <Modal
      open={id != null}
      onClose={onClose}
      size="lg"
      title={editing ? '알림 고치기' : (detail?.title ?? '알림')}
      description={
        detail
          ? `${detail.participant_id == null ? '전체 알림' : `#${detail.participant_id} ${detail.nickname ?? ''}에게`}, ${formatDateTime(detail.created_at)}에 보냄`
          : undefined
      }
      footer={
        editing ? (
          <>
            <Button variant="secondary" onClick={() => setEditing(false)} disabled={saving}>
              취소
            </Button>
            <Button onClick={() => void save()} loading={saving}>
              저장
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>
              닫기
            </Button>
            <Button onClick={startEdit} disabled={!detail}>
              수정
            </Button>
          </>
        )
      }
    >
      {loadError ? (
        <Alert tone="danger" title="알림을 불러오지 못했습니다">
          {loadError}
        </Alert>
      ) : !detail ? (
        <Skeleton lines={4} height="1.25rem" />
      ) : editing ? (
        <Stack gap={4}>
          {saveError && (
            <Alert tone="danger" title="알림을 고치지 못했습니다">
              {saveError}
            </Alert>
          )}
          <TextField label="제목" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required />
          <TextArea label="내용" value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} rows={8} required />
          <Checkbox
            label="읽은 사람에게도 다시 새 알림으로 표시"
            hint="내용이 크게 바뀌었을 때 켜세요. 끄면 읽음 상태는 그대로이고, 참가자 화면에 '수정됨'이 붙습니다."
            checked={resetReads}
            onChange={setResetReads}
          />
        </Stack>
      ) : (
        <Stack gap={5}>
          <KeyValueList
            items={[
              { label: '읽음', value: `${detail.read_count} / ${detail.recipients}명` },
              ...(detail.updated_at ? [{ label: '마지막 수정', value: formatDateTime(detail.updated_at) }] : []),
            ]}
          />
          <Text as="div" style={{ whiteSpace: 'pre-line' }}>
            {detail.body}
          </Text>
          <Stack gap={2}>
            <Text as="p" size="sm" tone="muted">
              받는 사람 {detail.readers.length}명 중 {detail.readers.length - unreadCount}명 읽음, {unreadCount}명 안 읽음
            </Text>
            <Table
              columns={READER_COLUMNS}
              rows={detail.readers}
              rowKey={(r) => r.participant_id}
              dense
              empty="받는 사람이 없습니다."
            />
          </Stack>
        </Stack>
      )}
    </Modal>
  );
}
