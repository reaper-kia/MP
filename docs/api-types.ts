// Сгенерировано из contracts/http/openapi.yaml — не править руками.
// Версия контракта 1.0.0. Для кода фронта используйте openapi-typescript (FE-01).

export type Platform = "vk" | "ok" | "max" | "news";

/** direct — прямо по запросу; indirect — косвенно; disputed — спорно, проверить; rejected — отсеяно системой (не в подборке) */
export type Relevance = "direct" | "indirect" | "disputed" | "rejected";

export type DateStatus = "in_period" | "unknown";

export type QueryType = "topic" | "event" | "person" | "news_text";

export interface ErrorResponse {
  error: { code: string; message: string; request_id: string; details: Record<string, unknown>[] };
}

export interface PlatformInfo {
  code: Platform;
  title: string;
  /** Поддерживает поиск по выбранным источникам */
  source_mode: boolean;
  /** Поддерживает поиск по всей площадке */
  global_mode: boolean;
  status: "ok" | "degraded" | "unavailable";
  note: string | null;
}

export interface QueryAnalyzeIn {
  query: string;
}

export interface QueryAnalysis {
  /** null — тип не определён (ML в упрощённом режиме): показать «тип запроса не определён» */
  query_type: QueryType | null;
  summary: string;
  search_queries: string[];
  needs_clarification: boolean;
  clarification_hint: string | null;
}

export interface Source {
  id: string;
  platform: Platform;
  external_id: string;
  url: string;
  name: string;
  city: string | null;
  /** Относится к Красноярскому краю */
  is_regional: boolean;
  /** Участвует в поиске «везде» и выбран по умолчанию */
  is_active: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface SourcePage {
  items: Source[];
  total: number;
  has_more: boolean;
}

export interface SourceCreateIn {
  url: string;
  /** Пусто — взять с площадки */
  name?: string | null;
  is_regional?: boolean;
  notes?: string;
}

export interface SourceUpdateIn {
  name?: string;
  is_regional?: boolean;
  is_active?: boolean;
  notes?: string;
}

export interface SourceResolveIn {
  url: string;
}

export interface SourcePreview {
  platform: Platform;
  external_id: string;
  url: string;
  name: string;
  city: string | null;
  members_count: number | null;
  /** Не null — уже в каталоге */
  existing_source_id: string | null;
}

export interface SourceImportReport {
  created: number;
  duplicates: number;
  failed: { row: number; value: string; code: string; message: string }[];
}

export interface SearchCreateIn {
  /** Тема, событие, человек или текст новости — одно поле */
  query: string;
  period_from: string;
  period_to: string;
  mode: "selected" | "global";
  platforms: Platform[];
  /** Обязательно непустой при mode=selected */
  source_ids: string[];
  /** По умолчанию false. true — не брать готовую подборку из кэша, искать заново («Обновить») */
  fresh?: boolean;
}

/** Подборка взята из кэша — копия недавнего такого же поиска (B2-20) */
export interface SearchCache {
  /** Исходный поиск, с которого снята копия */
  from_search_id: string;
  /** Когда исходный поиск завершился («собрана N мин назад») */
  created_at: string;
}

export interface SearchParams {
  query: string;
  query_type: QueryType | null;
  period_from: string;
  period_to: string;
  mode: "selected" | "global";
  platforms: Platform[];
  source_ids: string[];
}

/** completed + counts.total=0 → «Подходящие публикации не найдены» (показать, где искали). partial → подборка + баннер «Не удалось обработать N источников» + «Повторить». failed → ошибка + «Повторить». */
export type SearchStatus = "queued" | "running" | "completed" | "partial" | "failed" | "cancelled";

/** Подписи: Разбираем запрос… / Собираем публикации… / Проверяем связь с запросом… / Группируем… */
export type SearchStage = "queued" | "analyzing_query" | "collecting" | "scoring" | "grouping" | "done";

/** done — найдены посты; empty — источник обработан, постов за период нет; failed — не удалось получить */
export type TargetStatus = "pending" | "running" | "done" | "empty" | "failed" | "skipped";

export interface ErrorInfo {
  /** PLATFORM_UNAVAILABLE | SOURCE_NOT_FOUND | SOURCE_PRIVATE | RATE_LIMITED | TIMEOUT | PARSE_ERROR | AUTH_REQUIRED */
  code: string;
  message: string;
}

export interface SearchTarget {
  id: string;
  kind: "source" | "platform_search";
  platform: Platform;
  source_id: string | null;
  /** Снимок названия на момент поиска */
  name: string;
  url: string | null;
  status: TargetStatus;
  /** Получено постов за период */
  fetched: number;
  /** Из них в подборке */
  matched: number;
  error: ErrorInfo | null;
  attempts: number;
  finished_at: string | null;
}

export interface SearchCounts {
  /** В подборке = direct+indirect+disputed минус исключённые. Каждое размещение считается отдельно. */
  total: number;
  direct: number;
  indirect: number;
  disputed: number;
  /** Отсеяно системой */
  rejected: number;
  /** Исключено пользователем */
  excluded: number;
  /** Из total — без даты публикации */
  unknown_date: number;
  /** Сюжетов среди total */
  groups: number;
}

export interface Search {
  id: string;
  status: SearchStatus;
  stage: SearchStage;
  progress: { targets_total: number; targets_finished: number; percent: number };
  params: SearchParams;
  query_analysis: QueryAnalysis | null;
  targets: SearchTarget[];
  counts: SearchCounts;
  warnings: string[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  /** Не null — подборка из кэша */
  cache: SearchCache | null;
}

export interface SearchSummary {
  id: string;
  status: SearchStatus;
  params: SearchParams;
  counts: SearchCounts;
  created_at: string;
  finished_at: string | null;
}

export interface SearchSummaryPage {
  items: SearchSummary[];
  has_more: boolean;
}

export interface ExcerptPart {
  text: string;
  highlight: boolean;
}

export interface Result {
  id: string;
  publication_id: string;
  platform: Platform;
  source: { id: string | null; name: string; url: string; is_regional: boolean };
  /** Прямая ссылка на пост */
  url: string;
  title: string;
  /** post_start — заголовка нет, показано начало поста (пометить) */
  title_source: "title" | "post_start";
  /** Дословный фрагмент исходного текста */
  excerpt: string;
  excerpt_parts: ExcerptPart[];
  /** null → «Дата недоступна» */
  published_at: string | null;
  date_status: DateStatus;
  relevance: Relevance;
  score: number;
  /** Почему система так решила */
  explanation: string;
  region: { by_source: boolean; by_content: boolean; evidence: string | null };
  sentiment: "positive" | "neutral" | "negative" | null;
  group_id: string | null;
  /** Сколько размещений в сюжете (1 — одиночка) */
  group_size: number;
  metrics: { views: number | null; likes: number | null; reposts: number | null; comments: number | null };
  excluded: boolean;
  found_by_target_id: string;
}

export interface ResultPage {
  items: Result[];
  total: number;
  has_more: boolean;
}

export interface ResultGroup {
  group_id: string;
  title: string;
  size: number;
  platforms: Platform[];
  earliest_published_at: string | null;
  /** Все размещения сюжета */
  items: Result[];
}

export interface GroupPage {
  items: ResultGroup[];
  total: number;
  has_more: boolean;
}

export interface ExclusionIn {
  result_ids: string[];
  excluded: boolean;
}
