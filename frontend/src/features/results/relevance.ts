import type { S } from "../../api/client";

export const RELEVANCE: Record<S["Relevance"], { label: string; color: string }> = {
  direct: { label: "Прямая связь", color: "green" },
  indirect: { label: "Косвенная", color: "blue" },
  disputed: { label: "Спорно — проверьте", color: "orange" },
  rejected: { label: "Отсеяно", color: "gray" },
};

export const SENTIMENT: Record<NonNullable<S["Result"]["sentiment"]>, { label: string; color: string }> = {
  positive: { label: "позитивная", color: "teal" },
  neutral: { label: "нейтральная", color: "gray" },
  negative: { label: "негативная", color: "red" },
};
