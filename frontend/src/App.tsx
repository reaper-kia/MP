import { createBrowserRouter, createHashRouter, RouterProvider } from "react-router";

import { AppLayout } from "./layout/AppLayout";
import { HomePage } from "./pages/HomePage";

// Страницы, кроме главной, грузятся при переходе (FE-16): главная не тянет форму поиска, даты и таблицы.
const routes = [
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/search", lazy: () => import("./pages/SearchPage").then((m) => ({ Component: m.SearchPage })) },
      {
        path: "/search/:searchId",
        lazy: () => import("./pages/SearchPage").then((m) => ({ Component: m.SearchPage })),
      },
      { path: "/sources", lazy: () => import("./pages/SourcesPage").then((m) => ({ Component: m.SourcesPage })) },
      { path: "/history", lazy: () => import("./pages/HistoryPage").then((m) => ({ Component: m.HistoryPage })) },
    ],
  },
];

// В расширении (FE-10) нет серверных путей — там hash-роутер.
const router = import.meta.env.MODE === "extension" ? createHashRouter(routes) : createBrowserRouter(routes);

export function App() {
  return <RouterProvider router={router} />;
}
