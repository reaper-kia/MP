import { Badge } from "@mantine/core";

import type { S } from "../api/client";
import { PLATFORM_TITLE } from "../lib/platforms";

export function PlatformBadge({ platform }: { platform: S["Platform"] }) {
  return (
    <Badge variant="outline" color="gray" style={{ flexShrink: 0 }}>
      {PLATFORM_TITLE[platform]}
    </Badge>
  );
}
