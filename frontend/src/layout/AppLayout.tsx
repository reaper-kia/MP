import { Drawer, Popover, Text, UnstyledButton, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
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
  const [menuOpened, menu] = useDisclosure(false);

  return (
    <div className={classes.shell}>
      <header className={classes.header}>
        <div className={classes.brand}>
          <UnstyledButton className={classes.roundButton} onClick={menu.open} aria-label="Открыть меню">
            <Icon name="menu" />
          </UnstyledButton>
          <UnstyledButton component={Link} to="/" className={classes.logo} aria-label="На главную">
            <Icon name="logo" size={20} />
          </UnstyledButton>
          <div>
            <p className={classes.brandName}>МедиаПульс</p>
            <p className={classes.brandSub}>Мониторинг публикаций</p>
          </div>
        </div>

        <div className={classes.actions}>
          <RegionPill />
          <ThemeToggle />
        </div>
      </header>

      <MenuDrawer opened={menuOpened} onClose={menu.close} pathname={pathname} />

      <main className={classes.main}>
        <Outlet />
      </main>
    </div>
  );
}

/** Регион фиксирован — Красноярский край; в поповере — по какому правилу публикация считается региональной. */
function RegionPill() {
  return (
    <Popover position="bottom-end" width={320} shadow="lg" radius="lg" withinPortal>
      <Popover.Target>
        <UnstyledButton className={classes.pill}>
          <Icon name="location" />
          <span className={classes.pillLabel}>Красноярский край</span>
          <Icon name="chevron" size={14} />
        </UnstyledButton>
      </Popover.Target>
      <Popover.Dropdown p="md">
        <Text fw={700} size="sm">
          География публикаций
        </Text>
        <Text size="xs" c="dimmed" mt={4}>
          Мониторинг настроен на Красноярский край.
        </Text>
        <Text size="sm" mt="sm" lh={1.55}>
          Публикация попадает в подборку, если она из регионального источника или в тексте упоминается край — город,
          район, населённый пункт.
        </Text>
        <Text size="xs" c="dimmed" mt="sm">
          Какие источники региональные — отмечается на странице «Источники».
        </Text>
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
      className={classes.roundButton}
      onClick={() => setColorScheme(dark ? "light" : "dark")}
      aria-label={dark ? "Включить светлую тему" : "Включить тёмную тему"}
      title={dark ? "Светлая тема" : "Тёмная тема"}
    >
      <Icon name={dark ? "sun" : "moon"} />
    </UnstyledButton>
  );
}

function MenuDrawer({ opened, onClose, pathname }: { opened: boolean; onClose: () => void; pathname: string }) {
  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size={320}
      withCloseButton={false}
      padding={24}
      overlayProps={{ backgroundOpacity: 0.3, blur: 3, color: "#171914" }}
      classNames={{ content: classes.drawer, body: classes.drawerBody }}
    >
      <div className={classes.drawerHead}>
        <div>
          <p className={classes.drawerTitle}>Меню</p>
          <p className={classes.drawerSub}>Разделы сервиса</p>
        </div>
        <UnstyledButton className={classes.closeButton} onClick={onClose} aria-label="Закрыть меню">
          <Icon name="close" />
        </UnstyledButton>
      </div>

      <nav className={classes.nav}>
        {NAV.map((item) => {
          const active = item.match(pathname);
          return (
            <UnstyledButton
              key={item.to}
              component={Link}
              to={item.to}
              onClick={onClose}
              className={classes.navItem}
              data-active={active || undefined}
            >
              <span className={classes.navIcon}>
                <Icon name={item.icon} size={20} />
              </span>
              <span>
                <span className={classes.navLabel}>{item.label}</span>
                <span className={classes.navDescription}>{item.description}</span>
              </span>
            </UnstyledButton>
          );
        })}
      </nav>

      <SystemStatus />
    </Drawer>
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
