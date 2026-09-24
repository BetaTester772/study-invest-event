import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  Button,
  FileDropzone,
  matchesAccept,
  Modal,
  NumberField,
  PriceChange,
  SegmentedControl,
  Table,
  Tabs,
  ToastProvider,
  useToast,
  clampInt,
} from '..';

describe('Button', () => {
  it('fires onClick when enabled', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>매수하기</Button>);
    await userEvent.click(screen.getByRole('button', { name: '매수하기' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled and busy while loading', async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        저장하기
      </Button>,
    );
    const btn = screen.getByRole('button', { name: /저장하기/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
    await userEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('respects disabled', () => {
    render(<Button disabled>보내기</Button>);
    expect(screen.getByRole('button', { name: '보내기' })).toBeDisabled();
  });
});

describe('PriceChange', () => {
  it('renders up with ▲ and up direction', () => {
    render(<PriceChange rate={0.12} data-testid="pc" />);
    const el = screen.getByTestId('pc');
    expect(el).toHaveTextContent('▲ 12.00%');
    expect(el).toHaveAttribute('data-direction', 'up');
    expect(el).toHaveAccessibleName('상승 12.00%');
  });

  it('renders down with ▼', () => {
    render(<PriceChange rate={-0.035} data-testid="pc" />);
    const el = screen.getByTestId('pc');
    expect(el).toHaveTextContent('▼ 3.50%');
    expect(el).toHaveAttribute('data-direction', 'down');
    expect(el).toHaveAccessibleName('하락 3.50%');
  });

  it('renders flat without an arrow, and null as a dash', () => {
    const { rerender } = render(<PriceChange rate={0} data-testid="pc" />);
    expect(screen.getByTestId('pc')).toHaveTextContent('0.00%');
    expect(screen.getByTestId('pc')).not.toHaveTextContent(/[▲▼]/);
    expect(screen.getByTestId('pc')).toHaveAttribute('data-direction', 'flat');
    rerender(<PriceChange rate={null} data-testid="pc" />);
    expect(screen.getByTestId('pc')).toHaveTextContent('—');
  });
});

describe('Table', () => {
  const columns = [
    { key: 'name', header: '종목' },
    { key: 'price', header: '가격', numeric: true, render: (r: { price: number }) => `${r.price}원` },
  ];

  it('shows the empty state when there are no rows', () => {
    render(<Table columns={columns} rows={[]} rowKey={(_, i) => i} empty="아직 주문이 없어요." />);
    expect(screen.getByText('아직 주문이 없어요.')).toBeInTheDocument();
    expect(screen.getByText('아직 주문이 없어요.').closest('td')).toHaveAttribute('colspan', '2');
  });

  it('renders rows, right-aligns numeric columns and highlights rows', () => {
    const rows = [
      { name: '삼수전자', price: 75000, me: false },
      { name: 'LB', price: 14000, me: true },
    ];
    render(<Table columns={columns} rows={rows} rowKey={(r) => r.name} isRowHighlighted={(r) => r.me} />);
    expect(screen.getByText('75000원').className).toMatch(/align-right/);
    expect(screen.getByText('LB').closest('tr')).toHaveAttribute('aria-current', 'true');
    expect(screen.getByText('삼수전자').closest('tr')).not.toHaveAttribute('aria-current');
  });
});

describe('Modal', () => {
  it('closes on Escape and restores focus to the opener', async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>열기</button>
          <Modal open={open} onClose={() => setOpen(false)} title="인증 사진">
            <button>승인하기</button>
          </Modal>
        </>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole('button', { name: '열기' });
    await userEvent.click(opener);
    const dialog = screen.getByRole('dialog', { name: '인증 사진' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('calls onClose from the close button', async () => {
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="제목" />);
    await userEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe('SegmentedControl', () => {
  function Harness({ onChange }: { onChange?: (v: string) => void }) {
    const [v, setV] = useState<'buy' | 'sell'>('buy');
    return (
      <SegmentedControl
        label="주문 종류"
        value={v}
        onChange={(next) => {
          setV(next);
          onChange?.(next);
        }}
        options={[
          { value: 'buy', label: '매수', tone: 'up' },
          { value: 'sell', label: '매도', tone: 'down' },
        ]}
      />
    );
  }

  it('selects on click and exposes radio semantics', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    expect(screen.getByRole('radiogroup', { name: '주문 종류' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '매수' })).toHaveAttribute('aria-checked', 'true');
    await userEvent.click(screen.getByRole('radio', { name: '매도' }));
    expect(onChange).toHaveBeenCalledWith('sell');
    expect(screen.getByRole('radio', { name: '매도' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radiogroup')).toHaveAttribute('data-tone', 'down');
  });

  it('moves selection with arrow keys', async () => {
    render(<Harness />);
    screen.getByRole('radio', { name: '매수' }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: '매도' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: '매도' })).toHaveFocus();
  });
});

describe('NumberField', () => {
  function Harness({ min = 1, max = 10, initial = 1 }: { min?: number; max?: number; initial?: number }) {
    const [v, setV] = useState(initial);
    return (
      <>
        <NumberField label="수량" value={v} onChange={setV} min={min} max={max} suffix="주" />
        <output data-testid="value">{v}</output>
      </>
    );
  }

  it('clamps typed values above max on blur', async () => {
    render(<Harness />);
    const input = screen.getByLabelText('수량');
    await userEvent.clear(input);
    await userEvent.type(input, '999');
    fireEvent.blur(input);
    expect(screen.getByTestId('value')).toHaveTextContent('10');
    expect(input).toHaveValue('10');
  });

  it('clamps empty / below-min input to min', async () => {
    render(<Harness initial={5} />);
    const input = screen.getByLabelText('수량');
    await userEvent.clear(input);
    fireEvent.blur(input);
    expect(screen.getByTestId('value')).toHaveTextContent('1');
  });

  it('steps with buttons and disables at bounds', async () => {
    render(<Harness min={1} max={2} />);
    const dec = screen.getByRole('button', { name: '수량 줄이기' });
    const inc = screen.getByRole('button', { name: '수량 늘리기' });
    expect(dec).toBeDisabled();
    await userEvent.click(inc);
    expect(screen.getByTestId('value')).toHaveTextContent('2');
    expect(inc).toBeDisabled();
  });

  it('steps with arrow keys and ignores non-digits', async () => {
    render(<Harness initial={3} />);
    const input = screen.getByLabelText('수량');
    input.focus();
    await userEvent.keyboard('{ArrowUp}');
    expect(screen.getByTestId('value')).toHaveTextContent('4');
    await userEvent.type(input, 'abc');
    expect(input).toHaveValue('4');
  });

  it('clampInt handles edge cases', () => {
    expect(clampInt(5.9, 1, 10)).toBe(5);
    expect(clampInt(Number.NaN, 1, 10)).toBe(1);
    expect(clampInt(3, 1, 0)).toBe(1);
  });
});

describe('Tabs', () => {
  it('switches panels by click and arrow keys', async () => {
    render(
      <Tabs
        label="관리"
        items={[
          { value: 'a', label: '인증 검수', content: <p>검수 패널</p> },
          { value: 'b', label: '참가자', content: <p>참가자 패널</p> },
        ]}
      />,
    );
    expect(screen.getByRole('tabpanel')).toHaveTextContent('검수 패널');
    await userEvent.click(screen.getByRole('tab', { name: '참가자' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('참가자 패널');
    await userEvent.keyboard('{ArrowLeft}');
    expect(screen.getByRole('tab', { name: '인증 검수' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('Toast', () => {
  it('shows and auto-dismisses a toast', async () => {
    vi.useFakeTimers();
    function Trigger() {
      const toast = useToast();
      return <button onClick={() => toast.success('체결됐어요', '삼수전자 3주')}>알림</button>;
    }
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: '알림' }));
    expect(screen.getByText('체결됐어요')).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText('체결됐어요')).not.toBeInTheDocument();
    vi.useRealTimers();
  });
});

describe('FileDropzone', () => {
  it('matchesAccept checks mime, wildcard and extension fallback', () => {
    const heic = new File(['x'], 'study.HEIC', { type: '' });
    const png = new File(['x'], 'a.png', { type: 'image/png' });
    const pdf = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    expect(matchesAccept(heic, 'image/jpeg,image/heic')).toBe(true);
    expect(matchesAccept(png, 'image/*')).toBe(true);
    expect(matchesAccept(pdf, 'image/jpeg,image/png')).toBe(false);
  });

  it('rejects files over maxSize with a fix-it message', async () => {
    const onChange = vi.fn();
    render(<FileDropzone label="인증 사진" value={null} onChange={onChange} accept="image/png" maxSize={10} />);
    const input = screen.getByLabelText('인증 사진') as HTMLInputElement;
    const big = new File(['01234567890123'], 'big.png', { type: 'image/png' });
    await userEvent.upload(input, big);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('사진이 너무 커요');
  });

  it('accepts a valid file', async () => {
    const onChange = vi.fn();
    render(<FileDropzone label="인증 사진" value={null} onChange={onChange} accept="image/png" maxSize={1024} />);
    const ok = new File(['abc'], 'ok.png', { type: 'image/png' });
    await userEvent.upload(screen.getByLabelText('인증 사진'), ok);
    expect(onChange).toHaveBeenCalledWith(ok);
  });
});
