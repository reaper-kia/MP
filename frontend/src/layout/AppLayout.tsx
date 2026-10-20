import { Popover, Text, UnstyledButton, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router";

import { Icon, type IconName } from "../components/Icon";
import { usePlatforms } from "../features/search/useCatalog";
import classes from "./AppLayout.module.css";

interface NavItem {
  to: string;
  label: string;
  description: string;
  icon: IconName;
  match: (p: string) => boolean;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Главная", description: "На первую страницу", icon: "logo", match: (p) => p === "/" },
  {
    to: "/search",
    label: "Новый поиск",
    description: "Найти публикации",
    icon: "search",
    match: (p) => p === "/search" || p.startsWith("/search/"),
  },
  { to: "/history", label: "История", description: "Прошлые подборки", icon: "history", match: (p) => p.startsWith("/history") },
  { to: "/sources", label: "Источники", description: "Управление площадками", icon: "sources", match: (p) => p.startsWith("/sources") },
];

export function AppLayout() {
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  // переход по ссылке — шторка закрывается; Esc — тоже
  useEffect(() => setMenuOpen(false), [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className={classes.shell}>
      <header className={classes.header}>
        <div className={classes.brand}>
          <button
            type="button"
            className={`${classes.roundButton} ${classes.menuToggle} mp-press`}
            data-open={menuOpen || undefined}
            onClick={() => setMenuOpen((x) => !x)}
            aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
            aria-expanded={menuOpen}
            aria-controls="app-menu"
          >
            <span className={classes.menuLines} aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </button>
          <BrandLogo />
        </div>

        <div className={classes.actions}>
          <RegionPill />
          <ThemeToggle />
        </div>
      </header>

      <MenuDrawer open={menuOpen} onClose={() => setMenuOpen(false)} pathname={pathname} />

      <main className={classes.main}>
        <Outlet />
      </main>

      <ScrollTopButton />
    </div>
  );
}

/** Знак «М»-кардиограмма; под курсором раскрывается в «МедиаПульс». */
export function BrandLogo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className={`${classes.logo} mp-press`} aria-label="МедиаПульс — на главную">
      <span className={classes.logoSymbol}>
        <svg
          viewBox="0 0 36 28"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M2 15h3l3-5 3 5 3 7 3-7 5-10 4 10h8" />
          <circle className={classes.logoDot} cx="34" cy="15" r="1.5" fill="currentColor" stroke="none" />
        </svg>
      </span>
      <span className={classes.logoWord}>
        едиа
        <span className={classes.logoDivider} aria-hidden="true" />
        <span className={classes.logoPulse}>Пульс</span>
      </span>
    </Link>
  );
}

/** Регион фиксирован — Красноярский край; в поповере — по какому правилу публикация считается региональной. */
function RegionPill() {
  const [opened, setOpened] = useState(false);
  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="bottom-end"
      width={320}
      shadow="xl"
      radius="lg"
      withinPortal
      transitionProps={{ transition: "pop-top-right", duration: 200 }}
    >
      <Popover.Target>
        <UnstyledButton className={`${classes.pill} mp-press`} onClick={() => setOpened((x) => !x)} aria-expanded={opened}>
          <Icon name="location" />
          <span className={classes.pillLabel}>Красноярский край</span>
          <Icon name="chevron" size={14} className={`${classes.pillChevron} ${opened ? classes.flip : ""}`} />
        </UnstyledButton>
      </Popover.Target>
      <Popover.Dropdown p="md" className={classes.popover}>
        <div className={classes.popoverHead}>
          <div>
            <Text fw={700} size="sm">
              География публикаций
            </Text>
            <Text size="xs" c="dimmed" mt={4}>
              Мониторинг настроен на Красноярский край
            </Text>
          </div>
          <UnstyledButton className={classes.popoverClose} onClick={() => setOpened(false)} aria-label="Закрыть">
            <Icon name="close" />
          </UnstyledButton>
        </div>
        <p className={classes.popoverLabel}>Регион</p>
        <div className={classes.popoverValue}>
          <Icon name="location" size={14} />
          Красноярский край
        </div>
        <Text size="sm" mt="md" lh={1.55}>
          Публикация попадает в подборку, если она из регионального источника или в тексте упоминается край — город,
          район, населённый пункт.
        </Text>
        <div className={classes.popoverFoot}>
          <Text size="xs" c="dimmed">
            Региональные источники отмечаются на странице «Источники».
          </Text>
          <Link to="/sources" className={classes.popoverLink} onClick={() => setOpened(false)}>
            Источники
          </Link>
        </div>
      </Popover.Dropdown>
    </Popover>
  );
}

function ThemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("light", { getInitialValueInEffect: false });
  const dark = scheme === "dark";
  return (
    <UnstyledButton
      className={`${classes.roundButton} mp-press`}
      onClick={() => setColorScheme(dark ? "light" : "dark")}
      aria-label={dark ? "Включить светлую тему" : "Включить тёмную тему"}
      title={dark ? "Светлая тема" : "Тёмная тема"}
    >
      {/* key — иконка заново «влетает» при смене темы */}
      <span key={scheme} className="mp-icon-swap" style={{ display: "flex" }}>
        <Icon name={dark ? "sun" : "moon"} />
      </span>
    </UnstyledButton>
  );
}

/** Шторка слева под шапкой, как в макете: фон затемняется, пункты въезжают по очереди. */
function MenuDrawer({ open, onClose, pathname }: { open: boolean; onClose: () => void; pathname: string }) {
  return (
    <>
      <button
        type="button"
        className={classes.backdrop}
        data-open={open || undefined}
        aria-label="Закрыть меню"
        tabIndex={open ? 0 : -1}
        onClick={onClose}
      />
      <aside id="app-menu" className={classes.drawer} data-open={open || undefined} aria-hidden={!open} inert={!open}>
        <div className={classes.drawerHead}>
          <p className={classes.drawerTitle}>Меню</p>
          <p className={classes.drawerSub}>Разделы сервиса</p>
        </div>

        <nav className={classes.nav}>
          {NAV.map((item) => {
            const active = item.match(pathname);
            return (
              <Link key={item.to} to={item.to} onClick={onClose} className={classes.navItem} data-active={active || undefined}>
                <span className={classes.navIcon}>
                  <Icon name={item.icon} size={20} />
                </span>
                <span>
                  <span className={classes.navLabel}>{item.label}</span>
                  <span className={classes.navDescription}>{item.description}</span>
                </span>
              </Link>
            );
          })}
        </nav>

        <SystemStatus />
      </aside>
    </>
  );
}

/** Состояние площадок из GET /platforms — вместо «Все системы работают» из макета показываем реальное. */
function SystemStatus() {
  const platforms = usePlatforms();
  const list = platforms.data ?? [];
  const down = list.filter((p) => p.status !== "ok");
  let color = "#34d399";
  let text = "Все площадки работают";
  if (platforms.isPending) {
    color = "#979b8d";
    text = "Проверяем площадки…";
  } else if (platforms.isError) {
    color = "#f87171";
    text = "Нет связи с сервером";
  } else if (list.length > 0 && down.length === list.length) {
    color = "#f87171";
    text = "Площадки не подключены";
  } else if (down.length > 0) {
    color = "#fbbf24";
    text = `Ограничено: ${down.map((p) => p.title).join(", ")}`;
  }
  return (
    <div className={classes.status}>
      <span className="mp-dot" style={{ background: color }} />
      {text}
    </div>
  );
}

function ScrollTopButton() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const update = () => setVisible(window.scrollY > 320);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);
  if (!visible) return null;
  return (
    <button
      type="button"
      className="mp-scroll-top"
      aria-label="Наверх"
      title="Наверх"
      onClick={() =>
        window.scrollTo({
          top: 0,
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        })
      }
    >
      <Icon name="arrow" size={20} className={classes.up} />
    </button>
  );
}
