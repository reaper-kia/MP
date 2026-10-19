import { createBrowserRouter, createHashRouter, RouterProvider } from "react-router";

import { AppLayout } from "./layout/AppLayout";
import { HistoryPage } from "./pages/HistoryPage";
import { SearchPage } from "./pages/SearchPage";
import { SourcesPage } from "./pages/SourcesPage";

const routes = [
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <SearchPage /> },
      { path: "/search/:searchId", element: <SearchPage /> },
      { path: "/sources", element: <SourcesPage /> },
      { path: "/history", element: <HistoryPage /> },
    ],
  },
];

// В расширении (FE-10) нет серверных путей — там hash-роутер.
const router = import.meta.env.MODE === "extension" ? createHashRouter(routes) : createBrowserRouter(routes);

export function App() {
  return <RouterProvider router={router} />;
}
