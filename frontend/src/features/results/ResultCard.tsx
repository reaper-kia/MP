import { Anchor, Checkbox, Tooltip } from "@mantine/core";
import { useState } from "react";

import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { RelevanceGauge } from "../../components/Signal";
import { fmtDateTime } from "../../lib/dates";
import { fmtNumber } from "../../lib/format";
import classes from "./ResultCard.module.css";
import { RELEVANCE, SENTIMENT } from "./relevance";

interface Props {
  result: S["Result"];
  selected: boolean;
  onSelect: (on: boolean) => void;
  onExclude: (excluded: boolean) => void;
  /** Внутри раскрытого сюжета — без рамки и с меньшими отступами */
  compact?: boolean;
}

export function ResultCard({ result: r, selected, onSelect, onExclude, compact }: Props) {
  const [expanded, setExpanded] = useState(false);
  const rel = RELEVANCE[r.relevance];
  const date = fmtDateTime(r.published_at);
  const metrics = [
    r.metrics.views !== null && `${fmtNumber(r.metrics.views)} просмотров`,
    r.metrics.likes !== null && `♥ ${fmtNumber(r.metrics.likes)}`,
    r.metrics.reposts !== null && `↻ ${fmtNumber(r.metrics.reposts)}`,
    r.metrics.comments !== null && `💬 ${fmtNumber(r.metrics.comments)}`,
  ].filter(Boolean);
  const long = r.excerpt.length > 200;

  return (
    <article
      className={`${classes.card} ${compact ? "" : "mp-signal-card mp-motion-card"}`}
      data-lift="soft"
      data-compact={compact || undefined}
      data-excluded={r.excluded || undefined}
      data-selected={selected || undefined}
    >
      <Checkbox
        size="xs"
        mt={compact ? 4 : 12}
        checked={selected}
        onChange={(e) => onSelect(e.currentTarget.checked)}
        aria-label="Выбрать публикацию"
      />
      <PlatformLogo platform={r.platform} size={compact ? "sm" : "md"} />

      <div className={classes.body}>
        {/* заголовок */}
        <div className={classes.titleRow}>
          <h3 className={classes.title}>
            {r.title}
            {r.title_source === "post_start" && <span className={classes.titleNote}>начало поста</span>}
          </h3>
          {r.source.is_regional && (
            <span className={classes.regional}>
              <Icon name="check" size={14} /> Региональный
            </span>
          )}
          <Tooltip label="Насколько публикация близка к запросу" withArrow>
            <span className={classes.score} aria-label={`Близость к запросу ${Math.round(r.score * 100)}%`}>
              <RelevanceGauge value={r.score} />
              {Math.round(r.score * 100)}%
            </span>
          </Tooltip>
        </div>

        {/* источник · дата · регион */}
        <div className={classes.meta}>
          <Anchor href={r.source.url} target="_blank" rel="noopener noreferrer" className={classes.source}>
            {r.source.name}
          </Anchor>
          <span>·</span>
          {date ? (
            <span>{date}</span>
          ) : (
            <Tooltip label="Площадка не отдала дату — публикация может быть вне выбранного периода" multiline w={260}>
              <span className={classes.noDate}>Дата недоступна ⓘ</span>
            </Tooltip>
          )}
          {r.region.by_content && r.region.evidence && (
            <>
              <span>·</span>
              <span className={classes.evidence}>
                <Icon name="location" size={13} />
                {r.region.evidence}
              </span>
            </>
          )}
        </div>

        {/* выдержка — дословно из источника */}
        <p className={classes.excerpt} data-clamped={(!expanded && long) || undefined}>
          {r.excerpt_parts.map((p, i) => (p.highlight ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}
        </p>

        <div className="mp-expand" data-open={expanded || undefined} aria-hidden={!expanded}>
          <div>
            <div className={classes.details}>
              <p className={classes.explanation}>
                <Icon name="sparkles" size={14} />
                {r.explanation}
              </p>
              {(metrics.length > 0 || r.sentiment) && (
                <p className={classes.metrics}>
                  {[...metrics, r.sentiment ? `тональность: ${SENTIMENT[r.sentiment].label}` : null]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* оценка и действия */}
        <div className={classes.footer}>
          <Tooltip label={r.explanation} multiline w={300} disabled={expanded}>
            <span className={classes.relevance} data-rel={r.relevance}>
              {rel.label}
            </span>
          </Tooltip>
          {!expanded && r.sentiment && r.sentiment !== "neutral" && (
            <span className={classes.sentiment} data-sentiment={r.sentiment}>
              {SENTIMENT[r.sentiment].label}
            </span>
          )}

          <div className={classes.actions}>
            <button type="button" className="mp-text-action" onClick={() => setExpanded((x) => !x)}>
              {expanded ? "Свернуть" : "Читать подробнее"}
              <Icon name="chevron" size={14} className={expanded ? classes.flip : undefined} />
            </button>
            <a href={r.url} target="_blank" rel="noopener noreferrer" className="mp-text-action">
              Открыть оригинал <Icon name="external" />
            </a>
            {r.excluded ? (
              <button type="button" className="mp-text-action" onClick={() => onExclude(false)}>
                <Icon name="undo" /> Вернуть
              </button>
            ) : (
              <Tooltip label="Исключить из подборки">
                <button
                  type="button"
                  className={classes.trash}
                  onClick={() => onExclude(true)}
                  aria-label="Исключить из подборки"
                >
                  <Icon name="trash" />
                </button>
              </Tooltip>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
