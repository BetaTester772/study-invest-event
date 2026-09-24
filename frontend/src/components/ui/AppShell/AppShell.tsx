import { useEffect, useId, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { cx } from '../../../lib/cx';
import { Container } from '../Container/Container';
import { Icon } from '../Icon/Icon';
import styles from './AppShell.module.css';

export interface NavItem {
  to: string;
  label: string;
  /** Match only the exact path (for "/"). */
  end?: boolean;
}

export interface AppShellProps {
  brand: ReactNode;
  nav: NavItem[];
  /** Right side of the bar: account info, sign-in buttons. */
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}

/** Top-nav application frame. Below 640px the nav collapses into a menu button. */
export function AppShell({ brand, nav, actions, footer, children }: AppShellProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const location = useLocation();

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  return (
    <div className={styles.shell}>
      <a href="#main" className={styles.skip}>
        본문으로 건너뛰기
      </a>
      <header className={styles.bar}>
        <Container size="xl" className={styles.barInner}>
          <Link to="/" className={styles.brand}>
            {brand}
          </Link>
          <nav aria-label="주 메뉴" className={styles.desktopNav}>
            <ul className={styles.navList}>
              {nav.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) => cx(styles.navLink, isActive && styles.active)}
                  >
                    <span className={styles.navLabel}>{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className={styles.actions}>{actions}</div>
          <button
            type="button"
            className={styles.menuButton}
            aria-expanded={menuOpen}
            aria-controls={menuId}
            aria-label={menuOpen ? '메뉴 닫기' : '메뉴 열기'}
            onClick={() => setMenuOpen((o) => !o)}
          >
            <Icon name={menuOpen ? 'close' : 'menu'} size={22} />
          </button>
        </Container>
        <div id={menuId} className={cx(styles.mobilePanel, menuOpen && styles.mobilePanelOpen)} hidden={!menuOpen}>
          <nav aria-label="주 메뉴">
            <ul className={styles.mobileList}>
              {nav.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) => cx(styles.mobileLink, isActive && styles.active)}
                  >
                    <span className={styles.navLabel}>{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          {actions && <div className={styles.mobileActions}>{actions}</div>}
        </div>
      </header>
      <main id="main" className={styles.main} tabIndex={-1}>
        {children}
      </main>
      {footer && (
        <footer className={styles.footer}>
          <Container size="xl">{footer}</Container>
        </footer>
      )}
    </div>
  );
}
