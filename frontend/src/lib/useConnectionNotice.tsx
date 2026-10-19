// «Нет связи с сервером» (FE-06): фоновый перезапрос упал, а данные на экране уже есть.
// Показываем одно красное уведомление с «Повторить», данные не стираем; при успехе — убираем.
import { Anchor, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useRef } from "react";

import { ApiError } from "../api/client";
import { errorText } from "./errors";

const ID = "connection-lost";

interface WatchedQuery {
  isError: boolean;
  error: unknown;
  data: unknown;
  errorUpdatedAt: number;
  dataUpdatedAt: number;
  refetch: () => unknown;
}

/** Только сеть и 5xx: 4xx — это не «нет связи», их показывает сам экран. */
function isConnectionError(err: unknown) {
  return !(err instanceof ApiError) || err.status >= 500;
}

export function useConnectionNotice(q: WatchedQuery) {
  const shown = useRef(false);
  const refetch = useRef(q.refetch);
  refetch.current = q.refetch;

  useEffect(() => {
    if (!q.isError || q.data === undefined || !isConnectionError(q.error)) return;
    const title = q.error instanceof ApiError ? errorText(q.error) : "Нет связи с сервером";
    const message = (
      <Text size="sm">
        Данные на экране сохранены.{" "}
        <Anchor component="button" type="button" size="sm" onClick={() => refetch.current()}>
          Повторить
        </Anchor>
      </Text>
    );
    if (shown.current) notifications.update({ id: ID, color: "red", title, message, autoClose: false });
    else notifications.show({ id: ID, color: "red", title, message, autoClose: false, onClose: () => (shown.current = false) });
    shown.current = true;
  }, [q.errorUpdatedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (shown.current && !q.isError) {
      notifications.hide(ID);
      shown.current = false;
    }
  }, [q.dataUpdatedAt, q.isError]);
}
