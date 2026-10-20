import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { fmtPeriod } from "../../lib/dates";
import { publications } from "../../lib/format";
import classes from "./ParamsBar.module.css";

const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

/** К каким условиям относится показанная подборка. Липнет под шапкой при прокрутке. */
export function ParamsBar({ search, dirty }: { search: S["Search"]; dirty: boolean }) {
  const p = search.params;
  const period = fmtPeriod(p.period_from, p.period_to);

  return (
    <div className={classes.sticky}>
      <div className={classes.bar}>
        <span className={classes.query} title={p.query.length > 80 ? p.query : undefined}>
          «{cut(p.query.replace(/\s+/g, " "), 80)}»
        </span>
        <span className={classes.meta}>
          <Icon name="calendar" size={14} />
          {period}
        </span>
        <span className={classes.meta}>{p.mode === "selected" ? "Мои источники" : "Везде"}</span>
        <span className={classes.logos}>
          {p.platforms.map((x) => (
            <PlatformLogo key={x} platform={x} size="sm" />
          ))}
        </span>
        <span className={classes.count}>{publications(search.counts.total)}</span>
      </div>
      {dirty && (
        <div className={classes.dirty}>
          <Icon name="info" />
          <span>Параметры изменены. Ниже — подборка по прежним условиям.</span>
          {/* сабмит формы поиска по id — та же валидация, что у кнопки «Найти» */}
          <button type="submit" form="search-form" className={classes.again}>
            Найти заново
          </button>
        </div>
      )}
    </div>
  );
}
