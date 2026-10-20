import { Group, Text } from "@mantine/core";

import type { S } from "../api/client";
import { PLATFORM_TITLE } from "../lib/platforms";
import { PlatformLogo } from "./PlatformLogo";

/** Маленький логотип площадки с коротким названием. */
export function PlatformBadge({ platform }: { platform: S["Platform"] }) {
  return (
    <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
      <PlatformLogo platform={platform} size="sm" />
      <Text size="xs" fw={700} c="dimmed">
        {PLATFORM_TITLE[platform]}
      </Text>
    </Group>
  );
}
