// «Сигнальные» элементы макета v2: пульс-линия, сканер-орбита, индикатор близости. Стили — motion.css.

const PULSE_PATH = "M2 13h12l4-5 5 11 7-17 7 20 6-9h19";

export function DataPulse({ compact = false }: { compact?: boolean }) {
  return (
    <span className="mp-data-pulse" data-compact={compact || undefined} aria-hidden="true">
      <svg viewBox="0 0 64 24" fill="none">
        <path className="mp-data-pulse-track" d={PULSE_PATH} />
        <path className="mp-data-pulse-beat" d={PULSE_PATH} />
      </svg>
    </span>
  );
}

export function ScanOrbit() {
  return (
    <span className="mp-scan-orbit" aria-hidden="true">
      <svg viewBox="0 0 20 20" fill="none">
        <circle className="mp-scan-orbit-track" cx="10" cy="10" r="7" />
        <circle className="mp-scan-orbit-sweep" cx="10" cy="10" r="7" />
        <circle className="mp-scan-orbit-core" cx="10" cy="10" r="1.5" />
      </svg>
    </span>
  );
}

/** Полукруг, заполненный на value (0…1) — score публикации. */
export function RelevanceGauge({ value }: { value: number }) {
  const v = Math.min(1, Math.max(0, value));
  return (
    <span className="mp-gauge" aria-hidden="true" style={{ ["--mp-gauge" as string]: v }}>
      <svg viewBox="0 0 38 20" fill="none">
        <path className="mp-gauge-track" d="M3 17a16 16 0 0 1 32 0" />
        <path className="mp-gauge-value" d="M3 17a16 16 0 0 1 32 0" />
      </svg>
    </span>
  );
}

export function SourceStack() {
  return (
    <span className="mp-source-stack" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}
