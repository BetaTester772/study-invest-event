import { useState } from 'react';
import { adminApi, useApi, type AuditEntry } from '../../api';
import { LoadError } from '../../components/app/LoadError';
import { Button, Card, CodeBlock, Modal, Select, Stack, Table, Text, type Column } from '../../components/ui';
import { formatDateTime } from '../../lib/format';

export function AuditTab() {
  const [limit, setLimit] = useState('200');
  const audit = useApi(() => adminApi.audit(Number(limit)), [limit]);
  const [open, setOpen] = useState<AuditEntry | null>(null);

  const columns: Column<AuditEntry>[] = [
    { key: 'at', header: '시각', nowrap: true, render: (a) => formatDateTime(a.at) },
    { key: 'actor', header: '주체', render: (a) => a.actor },
    { key: 'action', header: '동작', render: (a) => a.action },
    {
      key: 'detail',
      header: '내용',
      hideOnMobile: true,
      render: (a) => {
        const text = JSON.stringify(a.detail);
        return (
          <Text as="span" size="xs" tone="muted">
            {text.length > 90 ? `${text.slice(0, 90)}…` : text}
          </Text>
        );
      },
    },
    {
      key: 'more',
      header: <span className="sr-only">자세히</span>,
      align: 'right',
      render: (a) => (
        <Button size="sm" variant="ghost" onClick={() => setOpen(a)}>
          자세히
        </Button>
      ),
    },
  ];

  return (
    <Stack gap={4}>
      <Stack direction="row" justify="between" align="end" wrap gap={3}>
        <Select
          label="표시 개수"
          value={limit}
          onChange={setLimit}
          options={[
            { value: '50', label: '최근 50건' },
            { value: '200', label: '최근 200건' },
            { value: '500', label: '최근 500건' },
          ]}
        />
        <Button variant="ghost" onClick={() => audit.refetch()}>
          새로 고침
        </Button>
      </Stack>
      <Card padding={audit.error ? 'md' : 'none'}>
        {audit.error ? (
          <LoadError error={audit.error} onRetry={audit.refetch} what="감사 로그" />
        ) : (
          <Table
            caption="감사 로그"
            columns={columns}
            rows={audit.data ?? []}
            rowKey={(a) => a.id}
            loading={audit.loading}
            dense
            empty="아직 기록이 없어요."
          />
        )}
      </Card>
      <Modal
        open={open != null}
        onClose={() => setOpen(null)}
        title={open ? `${open.action}` : ''}
        description={open ? `${formatDateTime(open.at)}, ${open.actor}` : undefined}
      >
        {open && <CodeBlock value={open.detail} maxHeight="60vh" />}
      </Modal>
    </Stack>
  );
}
