import {
  Anchor,
  Badge,
  Button,
  Checkbox,
  Drawer,
  Group,
  Loader,
  Pill,
  ScrollArea,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api, unwrap, type S } from "../../api/client";
import { PLATFORM_TITLE } from "../../lib/platforms";

const VISIBLE_CHIPS = 8;

interface Props {
  value: string[];
  onChange: (ids: string[]) => void;
  platforms: S["Platform"][]; // выбранные в форме площадки
  catalog: S["Source"][];
  error?: string;
}

/** Чипы выбранных источников + Drawer «Изменить список». */
export function SourcePicker({ value, onChange, platforms, catalog, error }: Props) {
  const [opened, { open, close }] = useDisclosure(false);
  const byId = new Map(catalog.map((s) => [s.id, s]));
  const chosen = value.map((id) => byId.get(id)).filter((s): s is S["Source"] => !!s);

  return (
    <Stack gap={6}>
      <Group gap={6}>
        {chosen.length === 0 && (
          <Text size="sm" c={error ? "red" : "dimmed"}>
            Источники не выбраны
          </Text>
        )}
        {chosen.slice(0, VISIBLE_CHIPS).map((s) => (
          <Pill key={s.id} withRemoveButton onRemove={() => onChange(value.filter((id) => id !== s.id))}>
            {PLATFORM_TITLE[s.platform]} · {s.name}
          </Pill>
        ))}
        {chosen.length > VISIBLE_CHIPS && (
          <Badge variant="light" color="gray" onClick={open} style={{ cursor: "pointer" }}>
            +{chosen.length - VISIBLE_CHIPS}
          </Badge>
        )}
        <Button variant="subtle" size="compact-sm" onClick={open}>
          Изменить список
        </Button>
      </Group>
      {error && (
        <Text size="xs" c="red">
          {error}
        </Text>
      )}
      <SourceDrawer opened={opened} onClose={close} value={value} onChange={onChange} platforms={platforms} catalog={catalog} />
    </Stack>
  );
}

function SourceDrawer({
  opened,
  onClose,
  value,
  onChange,
  platforms,
  catalog,
}: Omit<Props, "error"> & { opened: boolean; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [debouncedQ] = useDebouncedValue(q, 300);
  const [platform, setPlatform] = useState<"all" | S["Platform"]>("all");
  const filterPlatforms = platform === "all" ? platforms : [platform];

  const list = useQuery({
    queryKey: ["sources", "picker", debouncedQ, filterPlatforms],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/sources", {
          params: { query: { q: debouncedQ || undefined, platform: filterPlatforms, limit: 200, offset: 0 } },
        }),
      ),
    enabled: opened && filterPlatforms.length > 0,
    placeholderData: (prev) => prev,
  });

  const selected = new Set(value);
  const toggle = (id: string, on: boolean) => onChange(on ? [...value, id] : value.filter((x) => x !== id));
  const selectAll = () => {
    const ids = catalog.filter((s) => filterPlatforms.includes(s.platform)).map((s) => s.id);
    onChange([...new Set([...value, ...ids])]);
  };
  const items = list.data?.items ?? [];

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="md" title="Источники для поиска">
      <Stack gap="sm">
        <TextInput placeholder="Найти по названию или ссылке" value={q} onChange={(e) => setQ(e.currentTarget.value)} />
        <SegmentedControl
          size="xs"
          value={platform}
          onChange={(v) => setPlatform(v as typeof platform)}
          data={[{ value: "all", label: "Все" }, ...platforms.map((p) => ({ value: p, label: PLATFORM_TITLE[p] }))]}
        />
        <Group justify="space-between">
          <Group gap="xs">
            <Button size="compact-sm" variant="light" onClick={selectAll}>
              {platform === "all" ? "Выбрать все" : `Выбрать все ${PLATFORM_TITLE[platform]}`}
            </Button>
            <Button size="compact-sm" variant="subtle" color="gray" onClick={() => onChange([])}>
              Снять все
            </Button>
          </Group>
          <Text size="sm" c="dimmed">
            Выбрано: {value.length}
          </Text>
        </Group>

        <ScrollArea.Autosize mah="calc(100vh - 260px)">
          <Stack gap={8}>
            {list.isPending && <Loader size="sm" />}
            {list.isSuccess && items.length === 0 && (
              <Text size="sm" c="dimmed">
                Ничего не нашлось. Источники добавляются на странице «Источники».
              </Text>
            )}
            {items.map((s) => (
              <Checkbox
                key={s.id}
                checked={selected.has(s.id)}
                onChange={(e) => toggle(s.id, e.currentTarget.checked)}
                label={
                  <Group gap={6} wrap="nowrap">
                    <Text size="sm">{s.name}</Text>
                    <Text size="xs" c="dimmed">
                      {PLATFORM_TITLE[s.platform]}
                      {s.city ? ` · ${s.city}` : ""}
                      {s.is_active ? "" : " · не активен"}
                    </Text>
                  </Group>
                }
              />
            ))}
          </Stack>
        </ScrollArea.Autosize>
        <Group justify="space-between">
          <Anchor component={Link} to="/sources" size="sm">
            Управление источниками
          </Anchor>
          <Button onClick={onClose}>Готово</Button>
        </Group>
      </Stack>
    </Drawer>
  );
}
