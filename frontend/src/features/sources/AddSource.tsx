// Добавление источника по ссылке: blur / Enter → resolve → карточка → «Добавить» (FE-08, FE-10 переиспользует).
import { Alert, Anchor, Button, Checkbox, Group, Loader, Paper, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useRef, useState } from "react";

import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { errorText } from "../../lib/errors";
import { fmtNumber, plural } from "../../lib/format";
import { PLATFORM_NAME } from "../../lib/platforms";
import { useCreateSource, useResolveSource } from "./useSources";

interface Props {
  /** Источник уже в каталоге — показать его строку в таблице. */
  onShowExisting?: (preview: S["SourcePreview"]) => void;
  onAdded?: (source: S["Source"]) => void;
  /** Ссылка снаружи (расширение: адрес текущей вкладки) — сразу проверить. */
  initialUrl?: string;
}

const subscribers = (n: number) => `${fmtNumber(n)} ${plural(n, ["подписчик", "подписчика", "подписчиков"])}`;

export function AddSource({ onShowExisting, onAdded, initialUrl }: Props) {
  const [url, setUrl] = useState(initialUrl ?? "");
  const [regional, setRegional] = useState(true);
  const resolve = useResolveSource();
  const create = useCreateSource();
  const lastResolved = useRef<string | null>(null);

  const check = (value = url) => {
    const v = value.trim();
    if (!v || v === lastResolved.current) return;
    lastResolved.current = v;
    create.reset();
    resolve.mutate(v);
  };

  useEffect(() => {
    if (initialUrl) check(initialUrl);
  }, [initialUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  const onChange = (v: string) => {
    setUrl(v);
    // ссылку поменяли — старая карточка уже не про неё
    if (v.trim() !== lastResolved.current) {
      resolve.reset();
      create.reset();
      lastResolved.current = null;
    }
  };

  const add = (preview: S["SourcePreview"]) =>
    create.mutate(
      { url: preview.url, is_regional: regional, notes: "" },
      {
        onSuccess: (source) => {
          notifications.show({ color: "green", title: "Источник добавлен", message: `«${source.name}» участвует в поиске` });
          setUrl("");
          setRegional(true);
          resolve.reset();
          lastResolved.current = null;
          onAdded?.(source);
        },
      },
    );

  const preview = resolve.data;
  const inputError = resolve.isError ? errorText(resolve.error, "source") : null;

  return (
    <Paper withBorder radius="lg" p="lg" shadow="xs">
      <Stack gap="sm">
        <TextInput
          size="md"
          leftSection={<Icon name="plus" />}
          label="Добавить источник по ссылке"
          description="Группа ВКонтакте или Одноклассников, канал MAX, новостной сайт. Проверим ссылку и покажем, что это за источник."
          placeholder="https://vk.com/krsk_news"
          value={url}
          onChange={(e) => onChange(e.currentTarget.value)}
          onBlur={() => check()}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              check();
            }
          }}
          rightSection={resolve.isPending ? <Loader size="xs" /> : null}
          error={inputError}
        />

        {preview && (
          <Paper withBorder radius="lg" p="sm" bg="var(--mp-bg)">
            <Group justify="space-between" align="center" wrap="wrap" gap="sm">
              <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
                <PlatformLogo platform={preview.platform} />
                <Stack gap={2} style={{ minWidth: 0 }}>
                  <Anchor href={preview.url} target="_blank" rel="noopener noreferrer" fw={700} truncate>
                    {preview.name}
                  </Anchor>
                  <Text size="sm" c="dimmed">
                  {PLATFORM_NAME[preview.platform]} · {preview.city ?? "Город не указан"}
                  {preview.members_count !== null && ` · ${subscribers(preview.members_count)}`}
                  </Text>
                </Stack>
              </Group>

              {preview.existing_source_id ? (
                <Group gap="sm">
                  <Text size="sm" c="dimmed">
                    Уже в списке
                  </Text>
                  {onShowExisting && (
                    <Anchor component="button" type="button" size="sm" onClick={() => onShowExisting(preview)}>
                      Показать в таблице
                    </Anchor>
                  )}
                  <Button size="sm" disabled>
                    Добавить
                  </Button>
                </Group>
              ) : (
                <Group gap="md">
                  <Checkbox
                    label="Региональный"
                    description="Относится к Красноярскому краю"
                    checked={regional}
                    onChange={(e) => setRegional(e.currentTarget.checked)}
                  />
                  <Button size="sm" loading={create.isPending} onClick={() => add(preview)}>
                    Добавить
                  </Button>
                </Group>
              )}
            </Group>
          </Paper>
        )}

        {create.isError && (
          <Alert color="red" variant="light" p="xs">
            {errorText(create.error, "source")}
          </Alert>
        )}
      </Stack>
    </Paper>
  );
}
