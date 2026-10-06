import { useEffect, useState, type FormEvent } from 'react';
import { adminApi, ApiError, useApi, type Params } from '../../api';
import { LoadError } from '../../components/app/LoadError';
import { Alert, Button, Card, Grid, Skeleton, Stack, TextField, useToast } from '../../components/ui';
import { useScrollToFormError } from '../../lib/useScrollToFormError';

type Kind = 'float' | 'int' | 'nullableInt' | 'time';

const FIELDS: { key: keyof Params; label: string; hint: string; kind: Kind; group: string }[] = [
  { key: 'coin_p_up', label: '코인 상승 확률', hint: '0~1. 기본 0.30 (상승일 30%)', kind: 'float', group: 'coin' },
  {
    key: 'coin_up_exp',
    label: '코인 상승폭 지수',
    hint: '기본 2. 낮추면 큰 상승이 잦아집니다.',
    kind: 'float',
    group: 'coin',
  },
  {
    key: 'coin_down_exp',
    label: '코인 하락폭 지수',
    hint: '기본 2. 높이면 소폭 하락에 몰립니다.',
    kind: 'float',
    group: 'coin',
  },
  { key: 'coin_cap', label: '코인 일일 상한', hint: '소수. 0.8 = +80%', kind: 'float', group: 'coin' },
  { key: 'coin_floor', label: '코인 일일 하한', hint: '소수. -0.4 = -40%', kind: 'float', group: 'coin' },
  {
    key: 'coin_price_cap',
    label: '코인 가격 상한(원)',
    hint: '비우면 상한 없음. 권장 5000000',
    kind: 'nullableInt',
    group: 'coin',
  },
  {
    key: 'coin_calm_rounds',
    label: '초반 안정기 회차',
    hint: '1회차부터 이 회차까지 좁은 변동폭. 0이면 끔. 기본 3',
    kind: 'int',
    group: 'coin',
  },
  {
    key: 'coin_calm_cap',
    label: '안정기 일일 상한',
    hint: '소수. 0.3 = +30%',
    kind: 'float',
    group: 'coin',
  },
  {
    key: 'coin_calm_floor',
    label: '안정기 일일 하한',
    hint: '소수. -0.1 = -10%',
    kind: 'float',
    group: 'coin',
  },
  {
    key: 'stock_sensitivity',
    label: '주식 감도 계수',
    hint: '소수. 0.3 = 쏠림 1배당 ±30%',
    kind: 'float',
    group: 'stock',
  },
  { key: 'stock_min_price', label: '주식 최저가(원)', hint: '기본 1000', kind: 'int', group: 'stock' },
  {
    key: 'virtual_liquidity',
    label: '가상 유동성 L(원)',
    hint: '종목마다 매수금액에 더합니다. 예: 5000000',
    kind: 'int',
    group: 'stock',
  },
  {
    key: 'stock_noise_scale',
    label: '매수지분 잡음 세기 τ',
    hint: '0~2. 0이면 매수만으로 결정. 기본 0.1 (주문이 없어도 종목당 약 ±5%)',
    kind: 'float',
    group: 'stock',
  },
  {
    key: 'news_probability',
    label: '무작위 뉴스 확률',
    hint: '0~1. 정산 때 다음 운영일에 뉴스 1건이 생길 확률. 0이면 관리자가 쓴 뉴스만. 기본 0.5',
    kind: 'float',
    group: 'news',
  },
  {
    key: 'news_rate_min',
    label: '뉴스 효과 하한',
    hint: '소수. 0.1 = ±10%',
    kind: 'float',
    group: 'news',
  },
  {
    key: 'news_rate_max',
    label: '뉴스 효과 상한',
    hint: '소수. 0.2 = ±20%',
    kind: 'float',
    group: 'news',
  },
  {
    key: 'daily_buy_limit_ratio',
    label: '1일 1종목 매수 상한',
    hint: '소수. 0.4 = 총자산의 40%',
    kind: 'float',
    group: 'trade',
  },
  {
    key: 'reward_cash',
    label: '인증 보상(원)',
    hint: '승인 1건당 지급하는 현금. 기본 250000 (시드의 1/4)',
    kind: 'int',
    group: 'trade',
  },
  { key: 'certification_cutoff', label: '인증 마감 시각', hint: 'HH:MM, 예: 23:59', kind: 'time', group: 'trade' },
];

const GROUPS: { id: string; title: string; description: string }[] = [
  {
    id: 'coin',
    title: '병더리움 가격',
    description:
      '매일 18:00 정산에서 코인 변동률을 뽑는 분포입니다. 초반 안정기 회차는 평소보다 좁은 안정기 상·하한을 씁니다.',
  },
  {
    id: 'stock',
    title: '주식 가격',
    description:
      '종목별 매수 쏠림을 변동률로 바꾸는 방식입니다. 잡음 세기는 매수지분에 작은 무작위 배수를 곱해 주문이 없어도 가격이 조금씩 움직이게 합니다.',
  },
  {
    id: 'news',
    title: '호재·악재',
    description:
      '18:00 정산 때 다음 운영일 뉴스를 무작위로 뽑아 그 정산에서 바로 반영합니다. 참가자는 반영된 시작가와 함께 다음 날 09:00에 확인합니다. 호재·악재는 반반, 종목은 주식 4종목 중 균등이고, 효과 크기는 하한~상한 사이에서 1% 단위로 뽑습니다. 직접 쓰는 뉴스는 호재·악재 탭에서 작성하세요.',
  },
  { id: 'trade', title: '거래와 인증', description: '주문 한도, 인증 보상과 마감입니다.' },
];

type Draft = Record<keyof Params, string>;

function toDraft(p: Params): Draft {
  const d = {} as Draft;
  for (const f of FIELDS) d[f.key] = p[f.key] == null ? '' : String(p[f.key]);
  return d;
}

function parseDraft(d: Draft): { params?: Params; errors: Partial<Record<keyof Params, string>> } {
  const errors: Partial<Record<keyof Params, string>> = {};
  const out: Record<string, unknown> = {};
  for (const f of FIELDS) {
    const raw = d[f.key].trim();
    if (f.kind === 'time') {
      if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(raw)) errors[f.key] = 'HH:MM 형식으로 입력하세요. 예: 23:59';
      out[f.key] = raw;
    } else if (f.kind === 'nullableInt' && raw === '') {
      out[f.key] = null;
    } else {
      const n = Number(raw);
      if (raw === '' || !Number.isFinite(n)) errors[f.key] = '숫자를 입력하세요.';
      else if (f.kind !== 'float' && !Number.isInteger(n)) errors[f.key] = '정수로 입력하세요.';
      out[f.key] = n;
    }
  }
  return Object.keys(errors).length ? { errors } : { params: out as unknown as Params, errors };
}

export function ParamsTab() {
  const toast = useToast();
  const params = useApi(() => adminApi.params(), []);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [errors, setErrors] = useState<Partial<Record<keyof Params, string>>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [formRef] = useScrollToFormError(errors, saveError);

  useEffect(() => {
    if (params.data) setDraft(toDraft(params.data));
  }, [params.data]);

  if (params.error) return <LoadError error={params.error} onRetry={params.refetch} what="파라미터" />;
  if (!draft) return <Skeleton lines={6} height="2.5rem" />;

  const dirty = params.data ? JSON.stringify(toDraft(params.data)) !== JSON.stringify(draft) : false;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    const { params: parsed, errors: errs } = parseDraft(draft);
    setErrors(errs);
    if (!parsed) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await adminApi.updateParams(parsed);
      params.setData(saved);
      toast.success('파라미터를 저장했습니다', '다음 정산부터 적용됩니다.');
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : '저장하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form ref={formRef} onSubmit={save} noValidate>
      <Stack gap={5}>
        {saveError && (
          <Alert tone="danger" title="파라미터를 저장하지 못했습니다">
            {saveError}
          </Alert>
        )}
        {GROUPS.map((g) => (
          <Card key={g.id} title={g.title} description={g.description}>
            <Grid min="15rem" gap={4}>
              {FIELDS.filter((f) => f.group === g.id).map((f) => (
                <TextField
                  key={f.key}
                  label={f.label}
                  hint={f.hint}
                  inputMode={f.kind === 'time' ? 'text' : 'decimal'}
                  value={draft[f.key]}
                  error={errors[f.key]}
                  onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                />
              ))}
            </Grid>
          </Card>
        ))}
        <Stack direction="row" gap={2} justify="end" wrap>
          <Button
            variant="ghost"
            disabled={!dirty || saving}
            onClick={() => {
              if (params.data) setDraft(toDraft(params.data));
              setErrors({});
            }}
          >
            되돌리기
          </Button>
          <Button type="submit" loading={saving} disabled={!dirty}>
            파라미터 저장하기
          </Button>
        </Stack>
      </Stack>
    </form>
  );
}
