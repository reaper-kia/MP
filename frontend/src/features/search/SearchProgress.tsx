import { Button, Progress } from "@mantine/core";

import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { DataPulse } from "../../components/Signal";
import { fmtNumber } from "../../lib/format";
import classes from "./SearchProgress.module.css";
import { isFinal, stageText } from "./status";
import { useCancel } from "./useSearch";

/** Стадия и прогресс, пока поиск идёт; предупреждения — всегда. */
export function SearchProgress({ search }: { search: S["Search"] }) {
  const cancel = useCancel(search.id);
  const running = !isFinal(search.status);
  if (!running && search.warnings.length === 0) return null;
  // B2-15: одновременно идёт один поиск, остальные ждут в очереди
  const queued = search.status === "queued" || search.stage === "queued";

  return (
    <div className={classes.wrap}>
      {running && (
        <div className={`mp-card mp-signal-loading mp-page-enter ${classes.card}`}>
          <span className={`${classes.icon} ${queued ? "mp-pulse" : ""}`} data-queued={queued || undefined}>
            {queued ? <Icon name="history" size={22} /> : <DataPulse />}
          </span>
          <div className={classes.body}>
            {queued ? (
              <>
                <p className={classes.title}>В очереди — дождитесь окончания предыдущего поиска</p>
                <p className={classes.sub}>Поиск начнётся сам, страницу можно не обновлять</p>
              </>
            ) : (
              <>
                <p className={classes.title}>{stageText(search)}</p>
                <p className={classes.sub}>Проверяем публикации по смыслу — найденное появится ниже по мере обработки</p>
                <Progress value={search.progress.percent} animated striped size="sm" radius="xl" mt={12} />
                <p className={classes.meta}>
                  <span>Обычно 1–3 минуты</span>
                  <span className={classes.found}>Найдено пока: {fmtNumber(search.counts.total)}</span>
                </p>
              </>
            )}
          </div>
          <Button
            variant="default"
            size="compact-sm"
            leftSection={<Icon name={queued ? "close" : "stop"} size={14} />}
            loading={cancel.isPending}
            onClick={() => cancel.mutate(undefined)}
          >
            {queued ? "Отменить" : "Остановить"}
          </Button>
        </div>
      )}
      {search.warnings.map((w) => (
        <div key={w} className="mp-note">
          <Icon name="info" size={14} />
          {w}
        </div>
      ))}
    </div>
  );
}
