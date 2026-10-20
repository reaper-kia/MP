// Главная по макету v2: пульс-отметка, «С чего начнём?», живая строка охвата, две карточки-входа и «О сервисе».
import { Link } from "react-router";

import { Icon, type IconName } from "../components/Icon";
import { DataPulse } from "../components/Signal";
import { useAllSources, usePlatforms } from "../features/search/useCatalog";
import { fmtNumber, plural } from "../lib/format";
import classes from "./HomePage.module.css";

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: "search", title: "Поиск по смыслу", text: "Учитывает контекст, пересказы и изменённые заголовки." },
  { icon: "sources", title: "Площадки и сайты", text: "ВКонтакте, Одноклассники, MAX и новостные сайты региона." },
  { icon: "check", title: "Проверяемые данные", text: "Каждый материал сохраняет прямую ссылку на оригинал." },
  { icon: "filter", title: "Точная подборка", text: "Период, площадки и источники настраиваются под задачу." },
];

export function HomePage() {
  return (
    <div className={`${classes.page} mp-page-enter`}>
      <section className={classes.hero}>
        <div className={classes.heroInner}>
          <div className="mp-pulse-mark">
            <DataPulse />
          </div>
          <h1 className={classes.heroTitle}>С чего начнём?</h1>
          <p className={classes.heroLead}>
            Найдите публикации по теме или вернитесь к подборкам, которые уже собирали.
          </p>

          <CoverageRow />

          <div className={`${classes.entries} mp-stagger`}>
            <Link to="/search" className={`${classes.entry} mp-motion-card`}>
              <span className={`${classes.entryIcon} ${classes.entryIconInk}`}>
                <Icon name="search" size={20} />
              </span>
              <span className={classes.entryTitle}>Найти новости</span>
              <span className={classes.entryText}>Поиск по теме, событию, человеку или полному тексту новости.</span>
              <span className={classes.entryLink}>
                Перейти к поиску <Icon name="arrow" className={classes.entryArrow} />
              </span>
            </Link>
            <Link to="/history" className={`${classes.entry} mp-motion-card`}>
              <span className={`${classes.entryIcon} ${classes.entryIconAccent}`}>
                <Icon name="history" size={20} />
              </span>
              <span className={classes.entryTitle}>Открыть историю</span>
              <span className={classes.entryText}>Прошлые подборки из VK, Одноклассников, MAX и сайтов — с результатами.</span>
              <span className={classes.entryLink}>
                Смотреть подборки <Icon name="arrow" className={classes.entryArrow} />
              </span>
            </Link>
          </div>

          <button
            type="button"
            className={classes.aboutLink}
            onClick={() => document.getElementById("about-service")?.scrollIntoView({ behavior: "smooth" })}
          >
            О сервисе <Icon name="chevron" />
          </button>
        </div>
      </section>

      <section id="about-service" className={classes.about}>
        <div className={classes.aboutGrid}>
          <div>
            <p className="mp-eyebrow">
              <span className="mp-section-index">01</span> О сервисе
            </p>
            <h2 className={classes.aboutTitle}>Находите важное, не просматривая всё вручную</h2>
            <p className={classes.aboutLead}>
              МедиаПульс собирает публикации из социальных сетей и новостных сайтов, проверяет их связь с запросом и
              показывает источник каждого материала.
            </p>
          </div>
          <div className={classes.features}>
            {FEATURES.map((f) => (
              <div key={f.title}>
                <span className={classes.featureIcon}>
                  <Icon name={f.icon} />
                </span>
                <h3 className={classes.featureTitle}>{f.title}</h3>
                <p className={classes.featureText}>{f.text}</p>
              </div>
            ))}
          </div>
        </div>

        <div className={`${classes.cta} mp-motion-card`}>
          <div>
            <p className={classes.ctaTitle}>Готовы начать?</p>
            <p className={classes.ctaText}>Сформулируйте запрос своими словами — остальное сделает сервис.</p>
          </div>
          <Link to="/search" className="mp-accent-button mp-press">
            Найти публикации
          </Link>
        </div>
      </section>
    </div>
  );
}

/** «3 площадки · 24 источника · Прямой мониторинг» — из GET /platforms и GET /sources, а не из макета. */
function CoverageRow() {
  const platforms = usePlatforms();
  const sources = useAllSources();
  const working = (platforms.data ?? []).filter((p) => p.status !== "unavailable").length;
  const total = sources.data?.total;

  return (
    <div className={classes.coverage}>
      <span className={classes.coveragePulse}>
        <DataPulse compact />
      </span>
      <span>
        {platforms.isSuccess ? `${fmtNumber(working)} ${plural(working, ["площадка", "площадки", "площадок"])}` : "Площадки…"}
      </span>
      <span className={classes.separator} />
      <span>
        {total !== undefined ? `${fmtNumber(total)} ${plural(total, ["источник", "источника", "источников"])}` : "Источники…"}
      </span>
      <span className={classes.separator} />
      <span>Прямой мониторинг</span>
    </div>
  );
}
