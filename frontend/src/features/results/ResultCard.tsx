import { Anchor, Badge, Button, Checkbox, Group, Paper, Stack, Text, Tooltip } from "@mantine/core";
import { useState } from "react";

import type { S } from "../../api/client";
import { PlatformBadge } from "../../components/PlatformBadge";
import { fmtDateTime } from "../../lib/dates";
import { fmtNumber } from "../../lib/format";
import { RELEVANCE, SENTIMENT } from "./relevance";
import classes from "./ResultCard.module.css";

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
    r.metrics.views !== null && `👁 ${fmtNumber(r.metrics.views)}`,
    r.metrics.likes !== null && `♥ ${fmtNumber(r.metrics.likes)}`,
    r.metrics.reposts !== null && `↻ ${fmtNumber(r.metrics.reposts)}`,
    r.metrics.comments !== null && `💬 ${fmtNumber(r.metrics.comments)}`,
  ].filter(Boolean);

  return (
    <Paper
      withBorder={!compact}
      p={compact ? "xs" : "md"}
      radius="md"
      className={r.excluded ? classes.excluded : undefined}
      data-selected={selected || undefined}
    >
      <Group align="flex-start" wrap="nowrap" gap="sm">
        <Checkbox
          mt={4}
          checked={selected}
          onChange={(e) => onSelect(e.currentTarget.checked)}
          aria-label="Выбрать публикацию"
        />
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          {/* источник */}
          <Group gap="xs" wrap="wrap">
            <PlatformBadge platform={r.platform} />
            <Anchor href={r.source.url} target="_blank" rel="noopener noreferrer" size="sm" fw={500}>
              {r.source.name}
            </Anchor>
            {r.source.is_regional && (
              <Badge size="sm" variant="light" color="grape">
                Региональный источник
              </Badge>
            )}
            {r.region.by_content && r.region.evidence && (
              <Badge size="sm" variant="light" color="grape">
                {r.region.evidence}
              </Badge>
            )}
            <Text size="sm" c={date ? "dimmed" : "orange"} ml="auto">
              {date ?? (
                <Tooltip label="Площадка не отдала дату — публикация может быть вне выбранного периода" multiline w={260}>
                  <span style={{ cursor: "help" }}>Дата недоступна ⓘ</span>
                </Tooltip>
              )}
            </Text>
          </Group>

          {/* заголовок */}
          <Text fw={600} size={compact ? "sm" : "md"}>
            {r.title}
            {r.title_source === "post_start" && (
              <Text span size="xs" c="dimmed" fw={400} ml={6}>
                начало поста
              </Text>
            )}
          </Text>

          {/* выдержка — дословно из источника */}
          <div>
            <Text size="sm" lineClamp={expanded ? undefined : 3} className={classes.excerpt}>
              {r.excerpt_parts.map((p, i) => (p.highlight ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}
            </Text>
            {r.excerpt.length > 200 && (
              <Anchor component="button" type="button" size="xs" onClick={() => setExpanded((x) => !x)}>
                {expanded ? "Свернуть" : "Показать полностью"}
              </Anchor>
            )}
          </div>

          {/* оценка и действия */}
          <Group gap="xs" wrap="wrap">
            <Tooltip label={r.explanation} multiline w={300}>
              <Badge color={rel.color} variant="light" style={{ cursor: "help" }}>
                {rel.label}
              </Badge>
            </Tooltip>
            {r.sentiment && (
              <Badge color={SENTIMENT[r.sentiment].color} variant="dot">
                {SENTIMENT[r.sentiment].label}
              </Badge>
            )}
            {metrics.length > 0 && (
              <Text size="xs" c="dimmed">
                {metrics.join(" · ")}
              </Text>
            )}
            <Group gap="xs" ml="auto">
              <Button
                size="compact-sm"
                variant="subtle"
                color={r.excluded ? "blue" : "gray"}
                onClick={() => onExclude(!r.excluded)}
              >
                {r.excluded ? "Вернуть в подборку" : "Исключить"}
              </Button>
              <Button
                size="compact-sm"
                variant="light"
                component="a"
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Открыть пост
              </Button>
            </Group>
          </Group>
        </Stack>
      </Group>
    </Paper>
  );
}
