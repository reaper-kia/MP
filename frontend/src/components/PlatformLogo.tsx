// Квадратные логотипы площадок из макета: VK — синий, OK — оранжевый, MAX — картинка, сайты — газета.
import type { S } from "../api/client";
import { PLATFORM_NAME } from "../lib/platforms";
import { Icon } from "./Icon";
import classes from "./PlatformLogo.module.css";

interface Props {
  platform: S["Platform"];
  size?: "sm" | "md";
  /** Нативная подсказка; null — не показывать (когда снаружи уже есть Tooltip). */
  title?: string | null;
}

export function PlatformLogo({ platform, size = "md", title }: Props) {
  const cls = `${classes.logo} ${size === "sm" ? classes.sm : classes.md}`;
  const glyph = size === "sm" ? classes.glyphSm : classes.glyphMd;
  const label = PLATFORM_NAME[platform];
  const hint = title === null ? undefined : (title ?? label);

  if (platform === "vk") {
    return (
      <span className={cls} style={{ background: "#2787f5" }} role="img" aria-label={label} title={hint}>
        <svg viewBox="0 0 24 24" className={glyph} aria-hidden="true">
          <path
            fill="white"
            d="M4.7 7.2h3.1c.2 0 .4.2.5.5.7 2.1 1.8 4 2.7 4.6.3.2.5.1.5-.4V7.8c0-.5-.2-.7-.6-.8h-.7c-.2 0-.1-.5.2-.7.5-.4 1.3-.6 2.6-.6 1.1 0 1.5.2 1.5 1v5.1c0 .4.2.6.4.4.9-.6 2-2.5 2.7-4.6.1-.3.3-.5.6-.5h3.1c.4 0 .6.2.5.6-.4 1.7-3 4.7-3 4.7-.2.3-.2.5 0 .7.2.2 2.7 2.5 3.3 4.3.1.4-.1.6-.6.6h-2.8c-.4 0-.7-.2-.9-.5-.7-1.1-1.6-2.2-2.5-2.7-.3-.2-.6-.1-.6.4v2.2c0 .4-.2.6-.6.6-4.7.2-8.3-3.2-9.8-10-.1-.5.1-.8.4-.8Z"
          />
        </svg>
      </span>
    );
  }
  if (platform === "ok") {
    return (
      <span className={cls} style={{ background: "#ee8208" }} role="img" aria-label={label} title={hint}>
        <svg
          viewBox="0 0 24 24"
          className={glyph}
          fill="none"
          stroke="white"
          strokeWidth="2.3"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="7.5" r="3.2" />
          <path d="M7.5 13.2c2.8 1.9 6.2 1.9 9 0M12 14.7v5M8.5 18.8 12 15.5l3.5 3.3" />
        </svg>
      </span>
    );
  }
  if (platform === "max") {
    return (
      <span className={cls} role="img" aria-label={label} title={hint}>
        <img src={`${import.meta.env.BASE_URL}max-logo.webp`} alt="" className={classes.image} />
      </span>
    );
  }
  return (
    <span className={`${cls} ${classes.news}`} role="img" aria-label={label} title={hint}>
      <Icon name="news" size={size === "sm" ? 14 : 22} />
    </span>
  );
}
