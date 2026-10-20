import { Collapse } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";

import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { fmtDateTime } from "../../lib/dates";
import { plural } from "../../lib/format";
import classes from "./GroupCard.module.css";
import { ResultCard } from "./ResultCard";

interface Props {
  group: S["ResultGroup"];
  selected: Set<string>;
  onSelect: (id: string, on: boolean) => void;
  onExclude: (ids: string[], excluded: boolean) => void;
}

export function GroupCard({ group: g, selected, onSelect, onExclude }: Props) {
  const [opened, { toggle }] = useDisclosure(false);

  // Одиночка — сразу карточка, без обёртки сюжета
  if (g.size === 1) {
    const r = g.items[0];
    return (
      <ResultCard
        result={r}
        selected={selected.has(r.id)}
        onSelect={(on) => onSelect(r.id, on)}
        onExclude={(ex) => onExclude([r.id], ex)}
      />
    );
  }

  const date = fmtDateTime(g.earliest_published_at);
  return (
    <section className={classes.card} data-opened={opened || undefined}>
      <button type="button" className={classes.head} onClick={toggle} aria-expanded={opened}>
        <span className={classes.stack}>
          {g.platforms.slice(0, 3).map((p) => (
            <PlatformLogo key={p} platform={p} />
          ))}
        </span>
        <span className={classes.headBody}>
          <span className={classes.title}>{g.title}</span>
          <span className={classes.meta}>
            <span className={classes.size}>
              {g.size} {plural(g.size, ["размещение", "размещения", "размещений"])}
            </span>
            <span>·</span>
            <span className={date ? undefined : classes.noDate}>{date ? `с ${date}` : "Дата недоступна"}</span>
          </span>
        </span>
        <span className={classes.toggle}>
          {opened ? "Свернуть" : "Все размещения"}
          <Icon name="chevron" size={14} className={opened ? classes.flip : undefined} />
        </span>
      </button>
      <Collapse expanded={opened}>
        <div className={classes.items}>
          {g.items.map((r) => (
            <ResultCard
              key={r.id}
              compact
              result={r}
              selected={selected.has(r.id)}
              onSelect={(on) => onSelect(r.id, on)}
              onExclude={(ex) => onExclude([r.id], ex)}
            />
          ))}
          <div className={classes.groupActions}>
            <button type="button" className="mp-text-action" onClick={() => onExclude(g.items.map((r) => r.id), true)}>
              <Icon name="trash" /> Исключить весь сюжет
            </button>
          </div>
        </div>
      </Collapse>
    </section>
  );
}
