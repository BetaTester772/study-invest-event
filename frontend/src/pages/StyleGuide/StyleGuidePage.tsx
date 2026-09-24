import { useEffect, useState, type ReactNode } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  CodeBlock,
  Container,
  DayStrip,
  EmptyState,
  FileDropzone,
  Grid,
  Highlight,
  KeyValueList,
  LineChart,
  LinkButton,
  Modal,
  Money,
  NumberField,
  PageHeader,
  Percent,
  PriceChange,
  SegmentedControl,
  Select,
  Skeleton,
  Spinner,
  Stack,
  Stat,
  StatGroup,
  Table,
  Tabs,
  Text,
  TextArea,
  TextField,
  useToast,
  type Column,
} from '../../components/ui';
import { formatDayShort } from '../../lib/format';
import styles from './StyleGuidePage.module.css';

const SWATCHES = [
  ['잉크', '--color-ink'],
  ['공책', '--color-bg'],
  ['종이', '--color-surface'],
  ['형광펜', '--color-highlight'],
  ['연필', '--color-text-muted'],
  ['상승', '--color-up'],
  ['하락', '--color-down'],
  ['보합', '--color-flat'],
  ['승인', '--color-success'],
  ['주의', '--color-warning'],
  ['오류', '--color-danger'],
  ['안내', '--color-info'],
] as const;

const SAMPLE_DAYS = Array.from({ length: 11 }, (_, i) => `2026-10-${String(6 + i).padStart(2, '0')}`);
/** 날짜와 값을 짝지어 차트 점으로 만든다. 짧은 쪽 길이에 맞춘다. */
const zipPoints = (ys: number[]) =>
  SAMPLE_DAYS.slice(0, ys.length).map((x, i) => ({ x, y: ys[i] ?? 0 }));
const SAMPLE_POINTS = zipPoints([75000, 71200, 73900, 80100, 78400, 82000, 79300, 85600]);
const SAMPLE_DOWN = zipPoints([250000, 212000, 198500, 460000, 301000, 244000]);

interface RankRow {
  rank: number;
  nickname: string;
  total: number;
  rate: number;
  me?: boolean;
}
const RANK_ROWS: RankRow[] = [
  { rank: 1, nickname: '새벽도서관', total: 1482300, rate: 0.4823 },
  { rank: 2, nickname: '토익900', total: 1120000, rate: 0.12, me: true },
  { rank: 2, nickname: '밤샘코딩', total: 1120000, rate: 0.12 },
  { rank: 4, nickname: '수학귀신', total: 903500, rate: -0.0965 },
];
const RANK_COLUMNS: Column<RankRow>[] = [
  { key: 'rank', header: '순위', nowrap: true, numeric: true, width: '4rem' },
  { key: 'nickname', header: '닉네임' },
  { key: 'total', header: '총자산', numeric: true, render: (r) => <Money value={r.total} /> },
  { key: 'rate', header: '수익률', numeric: true, render: (r) => <PriceChange rate={r.rate} /> },
];

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Card title={title} description={description} as="section">
      {children}
    </Card>
  );
}

type Theme = 'system' | 'light' | 'dark';

export function StyleGuidePage() {
  const toast = useToast();
  const [theme, setTheme] = useState<Theme>('system');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [range, setRange] = useState<'1w' | 'all'>('all');
  const [qty, setQty] = useState(3);
  const [code, setCode] = useState('SAMSU');
  const [agree, setAgree] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    return () => root.removeAttribute('data-theme');
  }, [theme]);

  return (
    <Container>
      <PageHeader
        title="컴포넌트 목록"
        description="모든 화면은 이 부품들로만 만듭니다. 색·간격·서체는 tokens.css에서만 바꿉니다."
        actions={
          <SegmentedControl
            label="테마"
            value={theme}
            onChange={setTheme}
            options={[
              { value: 'system', label: '시스템' },
              { value: 'light', label: '밝게' },
              { value: 'dark', label: '어둡게' },
            ]}
          />
        }
      />
      <Stack gap={6}>
        <Section
          title="색"
          description="형광펜은 '지금·오늘·선택됨'에만, 빨강·파랑은 가격 방향과 매수·매도에만 씁니다."
        >
          <div className={styles.swatches}>
            {SWATCHES.map(([name, token]) => (
              <div key={token} className={styles.swatch}>
                <span className={styles.chip} style={{ background: `var(${token})` }} />
                <span className={styles.swatchName}>{name}</span>
                <code className={styles.swatchToken}>{token}</code>
              </div>
            ))}
          </div>
        </Section>

        <Section title="글자">
          <Stack gap={3}>
            <Text display size="3xl">
              도현체는 제목과 큰 가격에 씁니다
            </Text>
            <Text>
              본문은 IBM Plex Sans KR입니다. 오늘 공부를 인증하면 <Highlight>다음 운영일 09:00</Highlight>에 병더리움을
              받아요.
            </Text>
            <Text tone="muted" size="sm">
              보조 설명은 연필색으로 작게 씁니다.
            </Text>
          </Stack>
        </Section>

        <Section title="숫자 표시" description="Money, Percent, PriceChange — 금액은 정수 원, 비율은 소수로 받습니다.">
          <Stack direction="row" gap={6} wrap align="baseline">
            <Money value={1234500} display="xl" />
            <Money value={48200} sign colorize />
            <Money value={-12000} sign colorize />
            <Percent value={0.1234} sign colorize />
            <PriceChange rate={0.12} />
            <PriceChange rate={-0.035} />
            <PriceChange rate={0} />
            <PriceChange rate={0.3} pill />
            <PriceChange rate={-0.5} pill />
            <PriceChange rate={null} pill />
          </Stack>
        </Section>

        <Section title="버튼">
          <Stack gap={4}>
            <Stack direction="row" gap={2} wrap>
              <Button>기본 동작</Button>
              <Button variant="secondary">보조 동작</Button>
              <Button variant="ghost">덜 중요한 동작</Button>
              <Button variant="danger">반려하기</Button>
              <Button variant="buy">3주 매수하기</Button>
              <Button variant="sell">3주 매도하기</Button>
            </Stack>
            <Stack direction="row" gap={2} wrap align="center">
              <Button size="sm">작게</Button>
              <Button size="md">보통</Button>
              <Button size="lg">크게</Button>
              <Button disabled>누를 수 없음</Button>
              <Button
                loading={loading}
                onClick={() => {
                  setLoading(true);
                  window.setTimeout(() => setLoading(false), 1500);
                }}
              >
                저장하기
              </Button>
              <LinkButton to="/" variant="secondary">
                시세판 보기
              </LinkButton>
            </Stack>
            <Button fullWidth variant="buy" size="lg">
              전체 너비 버튼
            </Button>
          </Stack>
        </Section>

        <Section title="입력">
          <Grid min="15rem" gap={5}>
            <TextField label="닉네임" placeholder="2~20자" hint="랭킹에 이 이름이 보여요." />
            <TextField label="비밀번호" type="password" error="8자 이상 입력하세요." defaultValue="1234" />
            <NumberField
              label="수량"
              value={qty}
              onChange={setQty}
              min={1}
              max={12}
              suffix="주"
              hint="1~12주까지 살 수 있어요."
              trailing={
                <Button variant="secondary" onClick={() => setQty(12)}>
                  최대
                </Button>
              }
            />
            <Select
              label="종목"
              value={code}
              onChange={setCode}
              options={[
                { value: 'SAMSU', label: '삼수전자' },
                { value: 'SKLOW', label: 'SK로우닉스' },
                { value: 'BYUNG', label: '병더리움' },
              ]}
            />
            <TextArea label="반려 사유" placeholder="참가자에게 보여줄 사유를 적어 주세요." />
            <Checkbox
              label="가격 상한 적용"
              hint="코인 표시 상한(5,000,000원)을 씁니다."
              checked={agree}
              onChange={setAgree}
            />
          </Grid>
        </Section>

        <Section title="선택 컨트롤">
          <Stack gap={4}>
            <SegmentedControl
              label="주문 종류"
              value={side}
              onChange={setSide}
              size="lg"
              fullWidth
              options={[
                { value: 'buy', label: '매수', tone: 'up' },
                { value: 'sell', label: '매도', tone: 'down' },
              ]}
            />
            <SegmentedControl
              label="기간"
              value={range}
              onChange={setRange}
              options={[
                { value: '1w', label: '최근 7일' },
                { value: 'all', label: '전체' },
              ]}
            />
            <Tabs
              label="예시 탭"
              items={[
                { value: 'a', label: '인증 검수', count: 4, content: <Text>검수를 기다리는 인증 4건</Text> },
                { value: 'b', label: '참가자', content: <Text>참가자 목록</Text> },
                { value: 'c', label: '파라미터', content: <Text>파라미터 설정</Text> },
              ]}
            />
          </Stack>
        </Section>

        <Section title="배지">
          <Stack direction="row" gap={2} wrap>
            <Badge>보통</Badge>
            <Badge tone="success" dot>
              승인
            </Badge>
            <Badge tone="warning" dot>
              검수 대기
            </Badge>
            <Badge tone="danger" dot>
              반려
            </Badge>
            <Badge tone="info">코인</Badge>
            <Badge tone="up">매수</Badge>
            <Badge tone="down">매도</Badge>
            <Badge tone="highlight">나</Badge>
          </Stack>
        </Section>

        <Section title="이벤트 시간표" description="지난 날은 잉크, 오늘은 형광펜, 인증한 날에는 도장이 찍힙니다.">
          <DayStrip days={SAMPLE_DAYS} today="2026-10-09" stamped={['2026-10-06', '2026-10-07', '2026-10-09']} />
        </Section>

        <Section title="요약 수치">
          <StatGroup>
            <Stat
              emphasis
              label="총자산"
              value={<Money value={1120000} />}
              sub={<Percent value={0.12} sign colorize />}
            />
            <Stat label="현금" value={<Money value={312000} />} />
            <Stat label="평가손익" value={<Money value={120000} sign colorize />} />
            <Stat label="수익률" value={<Percent value={0.12} sign colorize />} />
          </StatGroup>
        </Section>

        <Section title="목록">
          <KeyValueList
            items={[
              { label: '주문 가능 현금', value: <Money value={812000} /> },
              { label: '보유 수량', value: '4주' },
              { label: '오늘 남은 매수 한도', value: <Money value={448000} /> },
              { label: '예상 금액', value: <Money value={225000} />, strong: true },
            ]}
          />
        </Section>

        <Section title="표">
          <Stack gap={4}>
            <Card padding="none">
              <Table
                caption="랭킹 예시"
                columns={RANK_COLUMNS}
                rows={RANK_ROWS}
                rowKey={(r) => r.nickname}
                isRowHighlighted={(r) => Boolean(r.me)}
              />
            </Card>
            <Card padding="none">
              <Table
                caption="빈 표"
                columns={RANK_COLUMNS}
                rows={[]}
                rowKey={(r) => r.nickname}
                empty="아직 순위가 없어요."
              />
            </Card>
            <Card padding="none">
              <Table caption="불러오는 표" columns={RANK_COLUMNS} rows={[]} rowKey={(r) => r.nickname} loading />
            </Card>
          </Stack>
        </Section>

        <Section title="차트" description="마지막 값이 처음보다 높으면 빨강, 낮으면 파랑. 눈금은 모눈종이.">
          <Grid min="18rem" gap={5}>
            <LineChart label="상승 예시" points={SAMPLE_POINTS} formatX={formatDayShort} />
            <LineChart label="하락 예시" points={SAMPLE_DOWN} formatX={formatDayShort} />
            <LineChart label="빈 차트" points={[]} height={160} />
          </Grid>
        </Section>

        <Section title="알림">
          <Stack gap={3}>
            <Alert title="장이 닫혀 있어요">09:00에 다시 열려요. 그때 주문할 수 있어요.</Alert>
            <Alert tone="success" title="인증 사진을 올렸어요">
              검수가 끝나면 결과를 여기서 볼 수 있어요.
            </Alert>
            <Alert tone="warning" title="같은 사진으로 보여요">
              인증 #12와 이미지가 같아요.
            </Alert>
            <Alert
              tone="danger"
              title="주문하지 못했어요"
              action={
                <Button size="sm" variant="secondary">
                  다시 시도
                </Button>
              }
            >
              현금이 부족해요. 수량을 줄여 주세요.
            </Alert>
            <Stack direction="row" gap={2} wrap>
              <Button
                variant="secondary"
                onClick={() => toast.success('체결됐어요', '삼수전자 3주를 225,000원에 샀어요.')}
              >
                성공 토스트
              </Button>
              <Button
                variant="secondary"
                onClick={() => toast.error('주문하지 못했어요', '오늘 이 종목 매수 한도를 넘었어요.')}
              >
                오류 토스트
              </Button>
              <Button variant="secondary" onClick={() => toast.show({ title: '매도 체결', tone: 'down' })}>
                매도 토스트
              </Button>
            </Stack>
          </Stack>
        </Section>

        <Section title="대화상자">
          <Button variant="secondary" onClick={() => setModalOpen(true)}>
            대화상자 열기
          </Button>
          <Modal
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            title="인증을 반려할까요?"
            description="반려 사유는 참가자에게 그대로 보여요."
            footer={
              <>
                <Button variant="ghost" onClick={() => setModalOpen(false)}>
                  취소
                </Button>
                <Button variant="danger" onClick={() => setModalOpen(false)}>
                  반려하기
                </Button>
              </>
            }
          >
            <TextArea label="반려 사유" data-autofocus />
          </Modal>
        </Section>

        <Section title="업로드">
          <FileDropzone
            label="인증 사진"
            value={file}
            onChange={setFile}
            accept="image/jpeg,image/png,image/webp,image/heic"
            maxSize={10 * 1024 * 1024}
            hint="JPG, PNG, WEBP, HEIC 한 장"
          />
        </Section>

        <Section title="불러오기와 빈 상태">
          <Grid min="16rem" gap={5}>
            <Stack gap={3}>
              <Stack direction="row" gap={4} align="center">
                <Spinner size="sm" />
                <Spinner />
                <Spinner size="lg" />
              </Stack>
              <Skeleton lines={3} />
              <Skeleton width="8rem" height="2rem" />
            </Stack>
            <EmptyState
              title="아직 주문이 없어요"
              description="시세판에서 종목을 골라 첫 주문을 넣어 보세요."
              action={<LinkButton to="/">시세판 보기</LinkButton>}
            />
          </Grid>
        </Section>

        <Section title="원문 보기">
          <CodeBlock value={{ action: 'settle', day: '2026-10-08', detail: { round: 3 } }} />
        </Section>
      </Stack>
    </Container>
  );
}
