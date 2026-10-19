import { AppShell, Container, Group, Text, UnstyledButton } from "@mantine/core";
import { Link, Outlet, useLocation } from "react-router";

import classes from "./AppLayout.module.css";

const NAV = [
  { to: "/", label: "Поиск", match: (p: string) => p === "/" || p.startsWith("/search/") },
  { to: "/sources", label: "Источники", match: (p: string) => p.startsWith("/sources") },
  { to: "/history", label: "История", match: (p: string) => p.startsWith("/history") },
];

export function AppLayout() {
  const { pathname } = useLocation();

  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Container size="xl" h="100%">
          <Group h="100%" gap="lg">
            <Text fw={700}>Медиамониторинг</Text>
            <Group gap={4} component="nav">
              {NAV.map((item) => (
                <UnstyledButton
                  key={item.to}
                  component={Link}
                  to={item.to}
                  className={item.match(pathname) ? `${classes.link} ${classes.active}` : classes.link}
                >
                  {item.label}
                </UnstyledButton>
              ))}
            </Group>
          </Group>
        </Container>
      </AppShell.Header>
      <AppShell.Main>
        <Container size="xl">
          <Outlet />
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
