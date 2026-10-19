/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_MOCKS?: string;
  /** "1" — показать «Скачать Word» (DOCX), когда бэкенд его сделает (B2-10). По умолчанию скрыто. */
  readonly VITE_DOCX?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
