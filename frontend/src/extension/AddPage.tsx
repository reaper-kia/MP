// Бонус FE-17: на странице группы VK / OK / канала MAX — «Добавить страницу в источники»
// (POST /sources/resolve → POST /sources, как AddSource на сайте).
import { Button } from "@mantine/core";
import { useEffect, useState } from "react";

import type { S } from "../api/client";
import { PlatformLogo } from "../components/PlatformLogo";
import { useCreateSource, useResolveSource } from "../features/sources/useSources";
import { errorText } from "../lib/errors";
import classes from "./popup.module.css";

const SOURCE_HOSTS = /(^|\.)(vk\.com|vk\.ru|ok\.ru|max\.ru)$/i;

/** Адрес активной вкладки, если это похоже на группу или канал. */
function useSourceTab(): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    void chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      try {
        if (tab?.url && SOURCE_HOSTS.test(new URL(tab.url).hostname)) setUrl(tab.url);
      } catch {
        /* не URL */
      }
    });
  }, []);
  return url;
}

export function AddPage() {
  const url = useSourceTab();
  const resolve = useResolveSource();
  const create = useCreateSource();
  const [added, setAdded] = useState<S["Source"] | null>(null);
  if (!url) return null;

  const preview = resolve.data;
  const exists = !!preview?.existing_source_id;

  return (
    <div className={classes.addPage}>
      {added ? (
        <p className={classes.addDone}>«{added.name}» добавлен в источники и участвует в поиске.</p>
      ) : preview ? (
        <>
          <div className={classes.addPreview}>
            <PlatformLogo platform={preview.platform} size="sm" />
            <span className={classes.addName}>{preview.name}</span>
          </div>
          {exists ? (
            <p className={classes.hint}>Уже есть в источниках.</p>
          ) : (
            <Button
              size="compact-sm"
              variant="light"
              loading={create.isPending}
              onClick={() =>
                create.mutate({ url: preview.url, is_regional: true, notes: "" }, { onSuccess: setAdded })
              }
            >
              Добавить в источники
            </Button>
          )}
        </>
      ) : (
        <Button size="compact-sm" variant="default" loading={resolve.isPending} onClick={() => resolve.mutate(url)}>
          Добавить эту страницу в источники
        </Button>
      )}
      {(resolve.isError || create.isError) && (
        <p className={classes.addError}>{errorText(resolve.error ?? create.error, "source")}</p>
      )}
    </div>
  );
}
