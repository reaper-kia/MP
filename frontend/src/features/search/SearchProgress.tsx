import { Button, Progress } from "@mantine/core";

import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import classes from "./SearchProgress.module.css";
import { isFinal, stageText } from "./status";
import { useCancel } from "./useSearch";

/** Стадия и прогресс, пока поиск идёт; предупреждения — всегда. */
export function SearchProgress({ search }: { search: S["Search"] }) {
  const cancel = useCancel(search.id);
  const running = !isFinal(search.status);
  if (!running && search.warnings.length === 0) return null;

  return (
    <div className={classes.wrap}>
      {running && (
        <div className={`mp-card ${classes.card}`}>
          <span className={`${classes.icon} mp-pulse`}>
            <Icon name="search" size={22} />
          </span>
          <div className={classes.body}>
            <p className={classes.title}>{stageText(search)}</p>
            <p className={classes.sub}>Проверяем публикации по смыслу — найденное появится ниже по мере обработки</p>
            <Progress value={search.progress.percent} animated striped size="sm" radius="xl" mt={12} />
          </div>
          <Button
            variant="default"
            size="compact-sm"
            leftSection={<Icon name="stop" size={14} />}
            loading={cancel.isPending}
            onClick={() => cancel.mutate(undefined)}
          >
            Остановить
          </Button>
        </div>
      )}
      {search.warnings.map((w) => (
        <div key={w} className={classes.warning}>
          <Icon name="info" />
          {w}
        </div>
      ))}
    </div>
  );
}
