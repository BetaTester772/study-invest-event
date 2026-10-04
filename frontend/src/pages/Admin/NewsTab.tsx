import { useState, type FormEvent } from 'react';
import { adminApi, ApiError, publicApi, useApi, type AdminNewsItem, type NewsKind } from '../../api';
import { NEWS_KIND_LABEL, NewsBadge } from '../../components/app/badges';
import { LoadError } from '../../components/app/LoadError';
import {
  Alert,
  Badge,
  Button,
  Card,
  Grid,
  NumberField,
  SegmentedControl,
  Select,
  Stack,
  Table,
  TextArea,
  TextField,
  useToast,
  type Column,
} from '../../components/ui';
import { formatDateTime, formatDay } from '../../lib/format';
import { useScrollToFormError } from '../../lib/useScrollToFormError';

export function NewsTab() {
  const toast = useToast();
  const instruments = useApi(() => publicApi.instruments(), []);
  const list = useApi(() => adminApi.news(), []);
  const [day, setDay] = useState('');
  const [code, setCode] = useState('');
  const [kind, setKind] = useState<NewsKind>('good');
  const [percent, setPercent] = useState(15);
  const [headline, setHeadline] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [body, setBody] = useState('');
  const [byline, setByline] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formRef] = useScrollToFormError(errors, formError);

  const stocks = (instruments.data ?? []).filter((i) => i.kind === 'stock');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!day) errs.day = '발표할 운영일을 고르세요.';
    if (!code) errs.code = '종목을 고르세요.';
    if (!(percent >= 1 && percent <= 100)) errs.percent = '1~100 사이로 입력하세요.';
    if (!headline.trim()) errs.headline = '참가자에게 보일 제목을 적어 주세요.';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    setFormError(null);
    try {
      const saved = await adminApi.setNews(day, code, {
        kind,
        rate: percent / 100,
        headline: headline.trim(),
        subtitle: subtitle.trim() || null,
        body: body.trim() || null,
        byline: byline.trim() || null,
      });
      toast.success('뉴스를 저장했어요', `${saved.name}, ${formatDay(saved.day)} ${NEWS_KIND_LABEL[saved.kind]}`);
      setHeadline('');
      setSubtitle('');
      setBody('');
      void list.refetch();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : '뉴스를 저장하지 못했어요.');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item: AdminNewsItem) => {
    try {
      await adminApi.deleteNews(item.day, item.code);
      toast.success('뉴스를 지웠어요', item.headline);
      void list.refetch();
    } catch (err) {
      toast.error('뉴스를 지우지 못했어요', err instanceof ApiError ? err.message : undefined);
    }
  };

  const columns: Column<AdminNewsItem>[] = [
    { key: 'day', header: '발표일', nowrap: true, render: (n) => formatDay(n.day, { weekday: false }) },
    { key: 'name', header: '종목', nowrap: true, render: (n) => n.name },
    { key: 'kind', header: '효과', render: (n) => <NewsBadge kind={n.kind} rate={n.rate} /> },
    { key: 'headline', header: '제목', render: (n) => n.headline },
    {
      key: 'source',
      header: '출처',
      hideOnMobile: true,
      render: (n) => (n.source === 'manual' ? '관리자' : '무작위'),
    },
    {
      key: 'state',
      header: '상태',
      render: (n) =>
        n.applied ? <Badge tone="neutral">반영 완료</Badge> : <Badge tone="info">대기</Badge>,
    },
    { key: 'created', header: '작성 시각', hideOnMobile: true, nowrap: true, render: (n) => formatDateTime(n.created_at) },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (n) =>
        n.applied ? null : (
          <Button variant="ghost" size="sm" onClick={() => void remove(n)}>
            지우기
          </Button>
        ),
    },
  ];

  return (
    <Stack gap={6}>
      <Card
        title="호재·악재 쓰기"
        description="전날 18:00 정산 전까지 쓸 수 있어요. 그 정산에서 그 종목 변동률에 곱해져 발표일 시작가에 반영되고, 09:00 공시와 함께 참가자에게 보여요. 같은 날·같은 종목에 이미 뉴스가 있으면 덮어써요. 첫 운영일은 앞선 정산이 없어 쓸 수 없어요."
      >
        <form ref={formRef} onSubmit={submit} noValidate>
          <Stack gap={4}>
            {formError && (
              <Alert tone="danger" title="뉴스를 저장하지 못했어요">
                {formError}
              </Alert>
            )}
            <Grid min="12rem" gap={4}>
              <TextField
                label="발표 운영일"
                type="date"
                value={day}
                onChange={(e) => setDay(e.target.value)}
                error={errors.day}
                required
              />
              <Select
                label="종목"
                value={code}
                onChange={setCode}
                placeholder="주식 종목 고르기"
                options={stocks.map((i) => ({ value: i.code, label: `${i.name} (${i.code})` }))}
                error={errors.code}
                required
              />
            </Grid>
            <Grid min="12rem" gap={4}>
              <SegmentedControl<NewsKind>
                label="종류"
                value={kind}
                onChange={setKind}
                options={[
                  { value: 'good', label: '호재', tone: 'up' },
                  { value: 'bad', label: '악재', tone: 'down' },
                ]}
                fullWidth
              />
              <NumberField
                label="효과 크기"
                value={percent}
                onChange={setPercent}
                min={1}
                max={100}
                step={1}
                suffix="%"
                hint={
                  kind === 'good'
                    ? `전날 정산 변동률에 ×(1 + ${percent}%)`
                    : `전날 정산 변동률에 ×(1 − ${percent}%)`
                }
                error={errors.percent}
                required
              />
            </Grid>
            <TextField
              label="제목"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              maxLength={120}
              placeholder="예: 삼수전자, 세 번째 도전 끝에 차세대 칩 양산 성공"
              error={errors.headline}
              required
            />
            <Grid min="12rem" gap={4}>
              <TextField
                label="부제 (선택)"
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                maxLength={120}
                placeholder="한 줄 요약"
              />
              <TextField
                label="매체명 (선택)"
                value={byline}
                onChange={(e) => setByline(e.target.value)}
                maxLength={40}
                placeholder="예: 병더리움경제TV, 명륜뉴스, 율전일보"
              />
            </Grid>
            <TextArea
              label="본문 (선택)"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={600}
              hint="2~3문장. 비우면 참가자에게 제목만 보여요. 변동률 숫자는 쓰지 마세요(크기는 위에서 정한 값이 배지로 보여요)."
              placeholder="기사체로 적어 주세요. 예: 삼수전자가 차세대 반도체 양산 라인의 수율 안정화에 성공했다고 밝혔다."
            />
            <Stack direction="row" justify="end">
              <Button type="submit" loading={saving}>
                뉴스 저장하기
              </Button>
            </Stack>
          </Stack>
        </form>
      </Card>
      <Card title="뉴스 목록" description="미래 날짜의 뉴스도 보여요. 참가자에게는 그날 09:00 공시 뒤에만 보여요." padding="none">
        {list.error ? (
          <LoadError error={list.error} onRetry={list.refetch} what="뉴스 목록" />
        ) : (
          <Table
            caption="호재·악재 목록"
            columns={columns}
            rows={list.data ?? []}
            rowKey={(n) => n.id}
            loading={list.loading}
            empty="아직 뉴스가 없어요. 무작위 뉴스는 전날 18:00 정산 때 생기고 그 자리에서 반영돼요."
          />
        )}
      </Card>
    </Stack>
  );
}
