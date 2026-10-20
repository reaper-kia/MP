import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from "@mantine/core";

// Токены из макета «МедиаПульс» (Figma Make): Manrope, тёплые оливковые серые, лаймовый акцент.
// Остальные цвета страницы — CSS-переменные --mp-* в styles.css.

const lime: MantineColorsTuple = [
  "#f7fee7",
  "#ecfccb",
  "#d9f99d",
  "#bef264",
  "#a3e635",
  "#84cc16",
  "#65a30d",
  "#4d7c0f",
  "#3f6212",
  "#365314",
];

// «slate» макета, перекрашенный в тёплый оливковый
const gray: MantineColorsTuple = [
  "#f7f6f0",
  "#f2f1e9",
  "#e8eadf",
  "#dcded2",
  "#c5c9ba",
  "#979b8d",
  "#74786a",
  "#575b4e",
  "#383b31",
  "#171914",
];

// тёмная тема макета
const dark: MantineColorsTuple = [
  "#f3f4eb",
  "#c9cdbf",
  "#969b8b",
  "#74776c",
  "#414737",
  "#2c3026",
  "#1c1f18",
  "#11130e",
  "#0d0f0b",
  "#080906",
];

export const theme = createTheme({
  primaryColor: "lime",
  primaryShade: { light: 3, dark: 3 },
  autoContrast: true,
  luminanceThreshold: 0.45,
  colors: { lime, gray, dark },
  black: "#171914",
  white: "#fffefa",
  fontFamily: '"Manrope", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  headings: {
    fontFamily: '"Manrope", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    fontWeight: "700",
  },
  defaultRadius: "md",
  radius: { xs: "6px", sm: "8px", md: "12px", lg: "16px", xl: "24px" },
  shadows: {
    xs: "0 1px 2px rgb(23 25 20 / 6%)",
    sm: "0 1px 3px rgb(23 25 20 / 8%), 0 1px 2px rgb(23 25 20 / 4%)",
    md: "0 8px 20px rgb(23 25 20 / 10%)",
    lg: "0 12px 28px rgb(23 25 20 / 14%)",
    xl: "0 24px 48px rgb(23 25 20 / 18%)",
  },
  components: {
    Button: { defaultProps: { radius: "md" }, styles: { root: { fontWeight: 700 } } },
    Paper: { defaultProps: { radius: "lg" } },
    Badge: { styles: { root: { textTransform: "none", fontWeight: 700, letterSpacing: 0 } } },
    Tooltip: { defaultProps: { radius: "md" } },
    Alert: { defaultProps: { radius: "lg" } },
    Drawer: { defaultProps: { radius: 0 } },
    Modal: { defaultProps: { radius: "lg" } },
  },
});

/** Переменные Mantine под палитру макета: карточки — «бумага» #fffefa, рамки и приглушённый текст — оливковые. */
export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {
    "--mantine-color-body": "#fffefa",
    "--mantine-color-text": "#171914",
    "--mantine-color-dimmed": "#65695b",
    "--mantine-color-placeholder": "#979b8d",
    "--mantine-color-default": "#fffefa",
    "--mantine-color-default-hover": "#f2f1e9",
    "--mantine-color-default-color": "#171914",
    "--mantine-color-default-border": "#dcded2",
    "--mantine-color-anchor": "#4d7c0f",
    "--mantine-primary-color-light-color": "#4d7c0f",
  },
  dark: {
    "--mantine-color-body": "#1c1f18",
    "--mantine-color-text": "#f3f4eb",
    "--mantine-color-dimmed": "#b0b5a4",
    "--mantine-color-placeholder": "#74776c",
    "--mantine-color-default": "#1c1f18",
    "--mantine-color-default-hover": "#25291f",
    "--mantine-color-default-color": "#f3f4eb",
    "--mantine-color-default-border": "#414737",
    "--mantine-color-anchor": "#bef264",
    "--mantine-primary-color-light-color": "#bef264",
  },
});
