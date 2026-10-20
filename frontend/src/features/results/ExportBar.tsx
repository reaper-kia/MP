// Выгрузка подборки (FE-07): «Скачать Excel» + (под флагом VITE_DOCX) «Скачать Word».
// Ссылка собирается из тех же фильтров, что на экране, — файл совпадает с подборкой.
import { Button, Group, Text, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError, unwrap, type S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { errorText } from "../../lib/errors";
import { publications } from "../../lib/format";
import { isFinal } from "../search/status";
import { exportQuery, type ResultFilters } from "./filters";

type Format = "xlsx" | "docx";
const DOCX_ENABLED = import.meta.env.VITE_DOCX === "1";

/** Query-строка с повтором ключа для массивов — как в api-клиенте. */
function toSearch(params: Record<string, string | string[] | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined) continue;
    (Array.isArray(v) ? v : [v]).forEach((x) => sp.append(k, x));
  }
  return sp.toString();
}

export function exportUrl(searchId: string, format: Format, f: ResultFilters, grouped: boolean): string {
  const base = import.meta.env.VITE_API_URL ?? "";
  return `${base}/api/v1/searches/${searchId}/export?${toSearch({ format, ...exportQuery(f, grouped) })}`;
}

/** filename*=UTF-8''… важнее filename="…" (там может быть транслит). */
function fileName(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const star = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) return decodeURIComponent(star[1]);
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  return plain?.[1] ?? fallback;
}

/**
 * Скачивание через fetch, а не голым переходом по ссылке: так ошибка (501 для Word, 404) показывается
 * уведомлением, а не скачивается файлом с JSON внутри. Ссылка в href остаётся (можно скопировать).
 */
async function download(url: string, fallback: string) {
  const res = await fetch(url);
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as S["ErrorResponse"] | null;
    throw new ApiError(res.status, body?.error.code ?? "UNKNOWN", body?.error.message ?? res.statusText);
  }
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = fileName(res.headers.get("Content-Disposition"), fallback);
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

interface Props {
  search: S["Search"];
  filters: ResultFilters;
  grouped: boolean;
}

export function ExportBar({ search, filters: f, grouped }: Props) {
  const final = isFinal(search.status);
  const rejectedTab = f.tab === "rejected";
  const q = exportQuery(f, grouped);

  // Сколько строк будет в файле: та же выборка без исключённых, limit=1 — нужен только total.
  // Ключ под ["results", id], чтобы исключение / повтор его обновляли.
  const count = useQuery({
    queryKey: ["results", search.id, "exportCount", q],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/searches/{search_id}/results", {
          params: { path: { search_id: search.id }, query: { ...q, limit: 1, offset: 0 } },
        }),
      ).then((p) => p.total),
    enabled: final && !rejectedTab,
  });
  const total = count.data;

  const [busy, setBusy] = useState<Format | null>(null);
  const run = async (format: Format) => {
    setBusy(format);
    try {
      await download(exportUrl(search.id, format, f, grouped), `podborka.${format}`);
    } catch (err) {
      notifications.show({ color: "red", title: "Не удалось скачать файл", message: errorText(err, "export") });
    } finally {
      setBusy(null);
    }
  };

  const disabledReason = !final
    ? "Дождитесь окончания поиска"
    : rejectedTab
      ? "Отсеянные системой публикации не выгружаются"
      : total === 0
        ? "Под эти фильтры ничего не подходит — выгружать нечего"
        : null;

  const button = (format: Format, label: string, variant: string) => {
    const btn = (
      <Button
        component="a"
        href={exportUrl(search.id, format, f, grouped)}
        download
        size="sm"
        variant={variant}
        leftSection={<Icon name="download" size={15} />}
        loading={busy === format}
        disabled={!!disabledReason || total === undefined}
        onClick={(e: React.MouseEvent) => {
          e.preventDefault();
          if (!disabledReason) void run(format);
        }}
      >
        {label}
      </Button>
    );
    return disabledReason ? (
      <Tooltip label={disabledReason} key={format}>
        {/* у disabled-кнопки нет событий мыши — тултип вешаем на обёртку */}
        <span>{btn}</span>
      </Tooltip>
    ) : (
      <span key={format}>{btn}</span>
    );
  };

  return (
    <Group justify="flex-end" gap="sm">
      {final && !rejectedTab && total !== undefined && (
        <Text size="xs" c="dimmed">
          В файл попадёт {publications(total)}
        </Text>
      )}
      {DOCX_ENABLED && button("docx", "Скачать Word", "default")}
      {button("xlsx", "Скачать Excel", "filled")}
    </Group>
  );
}
