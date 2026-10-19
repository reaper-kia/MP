import type { S } from "../api/client";

export const PLATFORM_TITLE: Record<S["Platform"], string> = {
  vk: "VK",
  ok: "OK",
  max: "MAX",
  news: "Новости",
};

/** Полное название — в карточках и подсказках. */
export const PLATFORM_NAME: Record<S["Platform"], string> = {
  vk: "ВКонтакте",
  ok: "Одноклассники",
  max: "MAX",
  news: "Новостные сайты",
};
