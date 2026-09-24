import { Link, Route, Routes, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import {
  AppShell,
  Button,
  Container,
  EmptyState,
  LinkButton,
  Stack,
  Text,
  ToastProvider,
  type NavItem,
} from './components/ui';
import { AdminPage } from './pages/Admin/AdminPage';
import { LoginPage } from './pages/Auth/LoginPage';
import { RegisterPage } from './pages/Auth/RegisterPage';
import { CertificationPage } from './pages/Certification/CertificationPage';
import { InstrumentPage } from './pages/Instrument/InstrumentPage';
import { MarketPage } from './pages/Market/MarketPage';
import { PortfolioPage } from './pages/Portfolio/PortfolioPage';
import { RankingPage } from './pages/Ranking/RankingPage';
import { StyleGuidePage } from './pages/StyleGuide/StyleGuidePage';

const NAV: NavItem[] = [
  { to: '/', label: '시장', end: true, alsoActiveOn: ['/instruments/'] },
  { to: '/portfolio', label: '내 자산' },
  { to: '/certification', label: '공부 인증' },
  { to: '/ranking', label: '랭킹' },
];

function AccountActions() {
  const { status, participant, logout } = useAuth();
  const navigate = useNavigate();
  if (status === 'authenticated') {
    return (
      <Stack direction="row" gap={2} align="center">
        <Text as="span" size="sm" weight="semibold">
          {participant?.nickname}
        </Text>
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            await logout();
            navigate('/');
          }}
        >
          로그아웃
        </Button>
      </Stack>
    );
  }
  if (status === 'loading') return null;
  return (
    <Stack direction="row" gap={2}>
      <LinkButton to="/login" size="sm" variant="ghost">
        로그인
      </LinkButton>
      <LinkButton to="/register" size="sm">
        참가 신청
      </LinkButton>
    </Stack>
  );
}

function NotFound() {
  return (
    <Container padTop>
      <EmptyState
        title="없는 페이지예요"
        description="주소가 바뀌었거나 잘못 입력됐어요. 시세판에서 다시 시작하세요."
        action={<LinkButton to="/">시세판으로 가기</LinkButton>}
      />
    </Container>
  );
}

function Shell() {
  return (
    <AppShell
      brand="공부장려 모의투자"
      nav={NAV}
      actions={<AccountActions />}
      footer={
        <Stack direction="row" justify="between" gap={3} wrap>
          <span>공부장려 모의투자 이벤트. 실제 돈이 오가지 않는 게임이에요.</span>
          <Stack direction="row" gap={4}>
            <Link to="/admin">관리자</Link>
            <Link to="/ui">컴포넌트 목록</Link>
          </Stack>
        </Stack>
      }
    >
      <Routes>
        <Route path="/" element={<MarketPage />} />
        <Route path="/instruments/:code" element={<InstrumentPage />} />
        <Route
          path="/portfolio"
          element={
            <RequireAuth>
              <PortfolioPage />
            </RequireAuth>
          }
        />
        <Route
          path="/certification"
          element={
            <RequireAuth>
              <CertificationPage />
            </RequireAuth>
          }
        />
        <Route path="/ranking" element={<RankingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/ui" element={<StyleGuidePage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppShell>
  );
}

export function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </ToastProvider>
  );
}
