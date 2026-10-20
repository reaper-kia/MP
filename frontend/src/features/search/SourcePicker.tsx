import {
  Anchor,
  Button,
  Checkbox,
  Drawer,
  Group,
  Loader,
  ScrollArea,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api, unwrap, type S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { PLATFORM_TITLE } from "../../lib/platforms";
import classes from "./SourcePicker.module.css";

const VISIBLE_CHIPS = 8;

interface Props {
  value: string[];
  onChange: (ids: string[]) => void;
  platforms: S["Platform"][]; // выбранные в форме площадки
  catalog: S["Source"][];
  error?: string;
  opened: boolean;
  onOpen: () => void;
  onClose: () => void;
}

/** Чипы выбранных источников + шторка «Изменить список». */
export function SourcePicker({ value, onChange, platforms, catalog, error, opened, onOpen, onClose }: Props) {
  const byId = new Map(catalog.map((s) => [s.id, s]));
  const chosen = value.map((id) => byId.get(id)).filter((s): s is S["Source"] => !!s);

  return (
    <div className={classes.row}>
      <span className={classes.label}>Источники</span>
      {chosen.length === 0 && (
        <span className={classes.empty} data-error={!!error || undefined}>
          не выбраны
        </span>
      )}
      {chosen.slice(0, VISIBLE_CHIPS).map((s) => (
        <span key={s.id} className={classes.chip}>
          <PlatformLogo platform={s.platform} size="sm" />
          <span className={classes.chipName}>{s.name}</span>
          <button
            type="button"
            className={classes.chipRemove}
            onClick={() => onChange(value.filter((id) => id !== s.id))}
            aria-label={`Убрать ${s.name}`}
          >
            <Icon name="close" size={12} />
          </button>
        </span>
      ))}
      {chosen.length > VISIBLE_CHIPS && (
        <button type="button" className={classes.more} onClick={onOpen}>
          +{chosen.length - VISIBLE_CHIPS}
        </button>
      )}
      <button type="button" className={classes.edit} onClick={onOpen}>
        Изменить список
      </button>
      <SourceDrawer opened={opened} onClose={onClose} value={value} onChange={onChange} platforms={platforms} catalog={catalog} />
    </div>
  );
}

function SourceDrawer({
  opened,
  onClose,
  value,
  onChange,
  platforms,
  catalog,
}: Omit<Props, "error" | "onOpen">) {
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
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="md"
      padding={24}
      title={
        <div>
          <Text fw={700} size="lg">
            Источники для поиска
          </Text>
          <Text size="xs" c="dimmed">
            Группы, сообщества и каналы
          </Text>
        </div>
      }
      overlayProps={{ backgroundOpacity: 0.3, blur: 3, color: "#171914" }}
    >
      <Stack gap="sm">
        <TextInput
          placeholder="Найти по названию или ссылке"
          leftSection={<Icon name="search" />}
          value={q}
          onChange={(e) => setQ(e.currentTarget.value)}
        />
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

        <ScrollArea.Autosize mah="calc(100vh - 290px)">
          <Stack gap={4}>
            {list.isPending && <Loader size="sm" />}
            {list.isSuccess && items.length === 0 && (
              <Text size="sm" c="dimmed">
                Ничего не нашлось. Источники добавляются на странице «Источники».
              </Text>
            )}
            {items.map((s) => (
              <label key={s.id} className={classes.option} data-checked={selected.has(s.id) || undefined}>
                <Checkbox
                  checked={selected.has(s.id)}
                  onChange={(e) => toggle(s.id, e.currentTarget.checked)}
                  aria-label={s.name}
                />
                <PlatformLogo platform={s.platform} size="sm" />
                <span className={classes.optionText}>
                  <span className={classes.optionName}>{s.name}</span>
                  <span className={classes.optionMeta}>
                    {PLATFORM_TITLE[s.platform]}
                    {s.city ? ` · ${s.city}` : ""}
                    {s.is_active ? "" : " · не активен"}
                  </span>
                </span>
              </label>
            ))}
          </Stack>
        </ScrollArea.Autosize>
        <Group justify="space-between">
          <Anchor component={Link} to="/sources" size="sm" fw={700}>
            Управление источниками
          </Anchor>
          <Button onClick={onClose}>Готово</Button>
        </Group>
      </Stack>
    </Drawer>
  );
}
