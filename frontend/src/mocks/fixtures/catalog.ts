import type { S } from "../../api/client";

export const PLATFORMS: S["PlatformInfo"][] = [
  { code: "vk", title: "ВКонтакте", source_mode: true, global_mode: true, status: "ok", note: null },
  {
    code: "ok",
    title: "Одноклассники",
    source_mode: true,
    global_mode: true,
    status: "degraded",
    note: "Глобальный поиск через Яндекс — покрытие неполное",
  },
  {
    code: "max",
    title: "MAX",
    source_mode: true,
    global_mode: false,
    status: "degraded",
    note: "Поиск только по каналам из списка",
  },
  {
    code: "news",
    title: "Новостные сайты",
    source_mode: true,
    global_mode: false,
    status: "ok",
    note: "Сайты из перечня агентства",
  },
];

export const PLATFORM_NAME: Record<S["Platform"], string> = {
  vk: "ВКонтакте",
  ok: "Одноклассники",
  max: "MAX",
  news: "Новостные сайты",
};

const CREATED = "2026-10-01T04:00:00Z";

function src(
  n: number,
  platform: S["Platform"],
  external_id: string,
  url: string,
  name: string,
  city: string | null,
  extra: Partial<S["Source"]> = {},
): S["Source"] {
  return {
    id: `5b0e2f6e-1c1a-4c47-9a39-6a1b2f0b0a${String(n).padStart(2, "0")}`,
    platform,
    external_id,
    url,
    name,
    city,
    is_regional: true,
    is_active: true,
    notes: "",
    created_at: CREATED,
    updated_at: CREATED,
    ...extra,
  };
}

export const SOURCES: S["Source"][] = [
  src(1, "vk", "-12345678", "https://vk.com/krsk_news", "Новости Красноярска", "Красноярск"),
  src(2, "vk", "-23456789", "https://vk.com/krasnoyarsk_dtp", "ДТП и ЧП | Красноярск", "Красноярск"),
  src(3, "vk", "-34567890", "https://vk.com/achinsk_online", "Ачинск онлайн", "Ачинск"),
  src(4, "vk", "-45678901", "https://vk.com/kansk_today", "Канск сегодня", "Канск"),
  src(5, "vk", "-56789012", "https://vk.com/norilsk_live", "Норильск LIVE", "Норильск"),
  src(6, "vk", "-67890123", "https://vk.com/sibir_auto", "Авто Сибирь", null, { is_regional: false, notes: "Федеральный, иногда пишет про край" }),
  src(7, "ok", "54000000001", "https://ok.ru/group/54000000001", "Красноярск | Одноклассники", "Красноярск"),
  src(8, "ok", "54000000002", "https://ok.ru/group/54000000002", "Зеленогорск — наш город", "Зеленогорск"),
  src(9, "ok", "54000000003", "https://ok.ru/group/54000000003", "Минусинск инфо", "Минусинск", { is_active: false }),
  src(10, "max", "krsk24", "https://max.ru/krsk24", "Красноярск 24", "Красноярск"),
  src(11, "max", "gibdd_24", "https://max.ru/gibdd_24", "Госавтоинспекция края", "Красноярск"),
  src(12, "max", "lesosibirsk", "https://max.ru/lesosibirsk", "Лесосибирск сейчас", "Лесосибирск"),
  src(13, "news", "ngs24.ru", "https://ngs24.ru", "НГС24", "Красноярск"),
  src(14, "news", "newslab.ru", "https://newslab.ru", "Newslab", "Красноярск"),
];

/** Сообщества, которые находит глобальный поиск, но которых нет в каталоге (source.id = null). */
export const GLOBAL_COMMUNITIES: Record<S["Platform"], { name: string; url: string }[]> = {
  vk: [
    { name: "Типичный Красноярск", url: "https://vk.com/typical_krsk" },
    { name: "Подслушано Железногорск", url: "https://vk.com/podsl_zheleznogorsk" },
    { name: "Шарыпово — город", url: "https://vk.com/sharypovo_city" },
    { name: "Дивногорск | Новости", url: "https://vk.com/divnogorsk_news" },
  ],
  ok: [
    { name: "Мы из Красноярского края", url: "https://ok.ru/group/54000000099" },
    { name: "Бородино и окрестности", url: "https://ok.ru/group/54000000098" },
  ],
  max: [{ name: "Сибирь сегодня", url: "https://max.ru/sibir_today" }],
  news: [{ name: "Красноярский рабочий", url: "https://krasrab.ru" }],
};
