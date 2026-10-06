import { act, render, screen } from '@testing-library/react';
import { useTurnstile, type Turnstile } from '../turnstile';

/** window.turnstile 대역: render한 위젯의 callback을 테스트가 직접 부른다. */
function fakeTurnstile() {
  const widgets: Array<{ action: string; callback?: (t: string) => void }> = [];
  const api = {
    render: vi.fn((_el: HTMLElement, opts: { action: string; callback?: (t: string) => void }) => {
      widgets.push(opts);
      return `w${widgets.length}`;
    }),
    reset: vi.fn(),
    remove: vi.fn(),
  };
  window.turnstile = api;
  return { api, widgets };
}

let hook: Turnstile;
function Harness({ siteKey }: { siteKey: string | null }) {
  hook = useTurnstile(siteKey, 'login');
  return <div data-testid="slot">{hook.widget}</div>;
}

afterEach(() => {
  delete window.turnstile;
});

describe('useTurnstile', () => {
  it('is a no-op without a site key', async () => {
    render(<Harness siteKey={null} />);
    expect(screen.getByTestId('slot')).toBeEmptyDOMElement();
    await expect(hook.take()).resolves.toBeUndefined();
  });

  it('renders the widget with the action and hands out each token once', async () => {
    const { api, widgets } = fakeTurnstile();
    render(<Harness siteKey="site" />);
    await act(async () => {});
    expect(api.render).toHaveBeenCalledTimes(1);
    expect(widgets[0]!.action).toBe('login');

    act(() => widgets[0]!.callback?.('tok-1'));
    await expect(hook.take()).resolves.toBe('tok-1');
    // 꺼내면 새 토큰을 받도록 reset하고, 새 토큰이 올 때까지 기다린다.
    expect(api.reset).toHaveBeenCalledWith('w1');
    const next = hook.take();
    act(() => widgets[0]!.callback?.('tok-2'));
    await expect(next).resolves.toBe('tok-2');
  });

  it('removes the widget on unmount', async () => {
    const { api } = fakeTurnstile();
    const { unmount } = render(<Harness siteKey="site" />);
    await act(async () => {});
    unmount();
    expect(api.remove).toHaveBeenCalledWith('w1');
  });
});
