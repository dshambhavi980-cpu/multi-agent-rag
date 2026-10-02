import { HugeiconsIcon } from "@hugeicons/react";
import {
  Activity01Icon,
  Alert01Icon,
  CloudServerIcon,
  Database01Icon,
  RefreshIcon,
  ServerIcon,
} from "@hugeicons/core-free-icons";

import { useHealth, useReadiness, useVersion } from "./useSystemStatus";

function StatusDot({ status }: { status: "ready" | "degraded" | "unavailable" }) {
  return <span className={`status-dot status-dot-${status}`} aria-hidden="true" />;
}

export function SystemOverview() {
  const health = useHealth();
  const readiness = useReadiness();
  const version = useVersion();
  const loading = health.isPending || readiness.isPending || version.isPending;
  const failed = health.isError || readiness.isError || version.isError;

  const refresh = () => {
    void health.refetch();
    void readiness.refetch();
    void version.refetch();
  };

  if (loading) {
    return (
      <section className="system-message" aria-live="polite">
        <HugeiconsIcon icon={RefreshIcon} className="spin" size={24} strokeWidth={1.8} aria-hidden="true" />
        <h1>Starting service</h1>
        <p>Connecting to the API and checking its dependencies.</p>
      </section>
    );
  }

  if (failed) {
    return (
      <section className="system-message system-message-error" role="alert">
        <HugeiconsIcon icon={Alert01Icon} size={26} strokeWidth={1.8} aria-hidden="true" />
        <h1>API unreachable</h1>
        <p>The free backend may be waking up. Retrying automatically every 10 seconds.</p>
        <button className="primary-button" type="button" onClick={refresh}>
          <HugeiconsIcon icon={RefreshIcon} size={17} strokeWidth={1.8} aria-hidden="true" />
          Retry
        </button>
      </section>
    );
  }

  const status = readiness.data.status;
  const environment = version.data.environment;
  const release = version.data.version;

  return (
    <div className="overview">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Workspace operations</p>
          <h1>System overview</h1>
        </div>
        <button className="icon-button bordered" type="button" onClick={refresh}>
          <HugeiconsIcon icon={RefreshIcon} size={18} strokeWidth={1.8} aria-hidden="true" />
          <span className="sr-only">Refresh status</span>
        </button>
      </div>

      <section className="status-banner" aria-label="Overall system status">
        <div className="status-summary">
          <div>
            <p className="status-label">
              {status === "ready" ? "Operational" : "Attention required"}
            </p>
            <p className="status-detail">
              {health.data.cold_start
                ? "The API has recently started."
                : "The API is warm and accepting traffic."}
            </p>
          </div>
        </div>
        <span className={`status-badge status-badge-${status}`}>{status}</span>
      </section>

      <section className="metric-grid" aria-label="Runtime details">
        <article className="metric-panel">
          <HugeiconsIcon icon={ServerIcon} size={20} strokeWidth={1.8} aria-hidden="true" />
          <p>API release</p>
          <strong>{release}</strong>
        </article>
        <article className="metric-panel">
          <HugeiconsIcon icon={CloudServerIcon} size={20} strokeWidth={1.8} aria-hidden="true" />
          <p>Environment</p>
          <strong>{environment}</strong>
        </article>
        <article className="metric-panel">
          <HugeiconsIcon icon={Activity01Icon} size={20} strokeWidth={1.8} aria-hidden="true" />
          <p>Process</p>
          <strong>{health.data.status}</strong>
        </article>
      </section>

      <section className="dependency-section" aria-labelledby="dependencies-title">
        <div className="section-heading">
          <div>
            <h2 id="dependencies-title">Dependencies</h2>
            <p>Readiness checks reported by the API.</p>
          </div>
        </div>
        <div className="dependency-list">
          {Object.entries(readiness.data.dependencies).map(([name, state]) => (
            <div className="dependency-row" key={name}>
              <div className="dependency-name">
                <HugeiconsIcon icon={Database01Icon} size={17} strokeWidth={1.8} aria-hidden="true" />
                <span>{name}</span>
              </div>
              <div className="dependency-state">
                <StatusDot status={state} />
                <span>{state}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
