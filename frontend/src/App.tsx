import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Activity,
  Bell,
  Building2,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Clock3,
  FlaskConical,
  Globe2,
  LayoutDashboard,
  LoaderCircle,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  PawPrint,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { api, ApiError } from "./api/client";
import type { Evaluation, Facility } from "./api/schemas";
import { useCommandCenter } from "./hooks/useCommandCenter";
import { useManagerWorkflow } from "./hooks/useManagerWorkflow";
import { DecisionHistory } from "./components/DecisionHistory";
import { NotificationPlanPanel } from "./components/NotificationPlanPanel";
import { confirmedClosures } from "./lib/dashboard";
import { formatTime } from "./lib/utils";
import { AssistantMascot } from "./components/AssistantMascot";
import { EvidenceFeed } from "./components/EvidenceFeed";
import { EvaluationEvidence } from "./components/EvaluationEvidence";
import { FacilitiesPage } from "./components/FacilitiesPage";
import { AlertsPage } from "./components/AlertsPage";
import { ReportsPage } from "./components/ReportsPage";
import { SettingsPage } from "./components/SettingsPage";
import { useMotionPreference } from "./hooks/MotionPreference";
import { savedEvaluations } from "./lib/reports";
import { RecommendationPanel } from "./components/RecommendationPanel";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card } from "./components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "./components/ui/dialog";

const FacilityMap = lazy(() => import("./components/FacilityMap"));
const navigation = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Facilities", icon: Building2 },
  { name: "Alerts", icon: Bell },
  { name: "Decision Queue", icon: ClipboardList },
  { name: "History", icon: Clock3 },
  { name: "Reports", icon: ChartNoAxesCombined },
  { name: "Settings", icon: Settings },
] as const;
type Screen = (typeof navigation)[number]["name"];

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand">
      <span className="brand-icon">
        <PawPrint size={23} />
        <span />
      </span>
      {!compact && (
        <div>
          <strong>
            Closure<span>Ops</span>
          </strong>
          <small>Clarity before action.</small>
        </div>
      )}
    </div>
  );
}
function Navigation({
  screen,
  onNavigate,
  collapsed = false,
}: {
  screen: Screen;
  onNavigate: (screen: Screen) => void;
  collapsed?: boolean;
}) {
  return (
    <nav aria-label="Main navigation">
      {navigation.map(({ name, icon: Icon }) => (
        <button
          key={name}
          className={`nav-item ${screen === name ? "active" : ""}`}
          onClick={() => onNavigate(name)}
          aria-current={screen === name ? "page" : undefined}
          title={name}
          aria-label={name}
        >
          <Icon size={19} />
          {!collapsed && (
            <>
              <span>{name}</span>
              {screen === name && <ChevronRight size={13} />}
            </>
          )}
        </button>
      ))}
    </nav>
  );
}

function App() {
  const resources = useCommandCenter();
  const { reducedMotion } = useMotionPreference();
  const [screen, setScreen] = useState<Screen>("Overview");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [evaluationId, setEvaluationId] = useState(() => {
    try {
      return sessionStorage.getItem("closureops-evaluation-id") ?? "";
    } catch {
      return "";
    }
  });
  const [scenarioId, setScenarioId] = useState("severe_applicable_flood");
  const [writesDenied, setWritesDenied] = useState(false);
  const evaluationLock = useRef(false);
  const [evaluationLoading, setEvaluationLoading] = useState(false);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [historyInspectionId, setHistoryInspectionId] = useState<string | null>(
    null,
  );
  const evaluationRequest = useRef<AbortController | null>(null);
  const pageHeading = useRef<HTMLHeadingElement>(null);
  const evidenceTrigger = useRef<HTMLElement | null>(null);
  const facilities = resources.facilities.data ?? [];
  const selected =
    facilities.find((f) => f.id === selectedId) ?? facilities[0] ?? null;
  const visibleEvaluation =
    evaluation?.result.facility_id === selected?.id ? evaluation : null;
  const writesEnabled =
    resources.health.status === "ready" &&
    resources.health.data?.local_demo_writes_enabled === true &&
    !writesDenied;
  const workflow = useManagerWorkflow(
    visibleEvaluation,
    writesEnabled && !evaluationLoading,
  );
  const refreshAudit = resources.refreshAudit;
  useEffect(() => {
    if (workflow.decision) void refreshAudit();
  }, [workflow.decision, refreshAudit]);
  const connection = resources.health.status;
  const audit = resources.audit.data;
  const availableEvaluations = savedEvaluations(
    visibleEvaluation,
    audit,
    selected?.id,
  );
  const facilityEvaluation =
    visibleEvaluation ?? availableEvaluations[0] ?? null;
  const closures = confirmedClosures(audit, resources.facilities.data);
  useEffect(() => () => evaluationRequest.current?.abort(), []);

  function selectFacility(id: string) {
    if (evaluationLoading || workflow.pending) return;
    if (id === selected?.id) {
      setSelectedId(id);
      return;
    }
    evaluationRequest.current?.abort();
    setSelectedId(id);
    setEvaluation(null);
    setEvaluationId("");
    setEvaluationError(null);
    setEvaluationLoading(false);
    setEvidenceOpen(false);
  }
  function navigate(next: Screen) {
    if (next === "History" || next === "Reports") void resources.refreshAudit();
    setScreen(next);
    setMobileOpen(false);
    requestAnimationFrame(() => pageHeading.current?.focus());
  }
  function openEvidence() {
    evidenceTrigger.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setEvidenceOpen(true);
  }
  async function loadEvaluation(event: FormEvent) {
    event.preventDefault();
    if (!selected || evaluationLock.current || workflow.pending) return;
    evaluationLock.current = true;
    evaluationRequest.current?.abort();
    const controller = new AbortController();
    evaluationRequest.current = controller;
    const facility: Facility = selected;
    setEvaluationLoading(true);
    setEvaluationError(null);
    setEvaluation(null);
    try {
      const data = await api.evaluation(evaluationId.trim(), controller.signal);
      if (controller.signal.aborted) return;
      if (data.result.facility_id !== facility.id)
        throw new Error(
          "This evaluation belongs to a different facility. Select the matching facility first.",
        );
      setEvaluation(data);
      rememberEvaluation(data.evaluation_id);
    } catch (error) {
      if (!controller.signal.aborted)
        setEvaluationError(
          error instanceof Error ? error.message : "Evaluation unavailable.",
        );
    } finally {
      evaluationLock.current = false;
      if (!controller.signal.aborted) setEvaluationLoading(false);
    }
  }
  function rememberEvaluation(id: string) {
    setEvaluationId(id);
    try {
      sessionStorage.setItem("closureops-evaluation-id", id);
    } catch {
      /* Persistence remains in SQLite when browser storage is unavailable. */
    }
  }
  function focusRecommendation() {
    requestAnimationFrame(() => {
      const heading = document.getElementById("operating-recommendation");
      heading?.focus({ preventScroll: true });
      heading?.scrollIntoView({ block: "center" });
    });
  }
  async function createEvaluation() {
    const scenario = resources.scenarios.data?.find(
      (s) => s.scenario_id === scenarioId && s.facility_id === selected?.id,
    );
    if (
      !selected ||
      !scenario ||
      !writesEnabled ||
      evaluationLock.current ||
      workflow.pending
    )
      return;
    evaluationLock.current = true;
    setEvaluationLoading(true);
    setEvaluationError(null);
    setEvaluation(null);
    try {
      const data = await api.createEvaluation(
        selected.id,
        scenario.scenario_id,
      );
      setEvaluation(data);
      rememberEvaluation(data.evaluation_id);
      focusRecommendation();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403)
        setWritesDenied(true);
      setEvaluationError(
        `${error instanceof Error ? error.message : "Evaluation unavailable."} No evaluation was confirmed in the browser. Retrying may create a separate evaluation; no manager action was submitted.`,
      );
    } finally {
      evaluationLock.current = false;
      setEvaluationLoading(false);
    }
  }
  const metrics = [
    {
      label: "Facilities represented",
      value: resources.facilities.data?.length,
      icon: Building2,
      tone: "blue",
      detail:
        resources.facilities.status === "loading"
          ? "Loading facility catalog"
          : resources.facilities.status === "error"
            ? "Facility catalog unavailable"
            : "Synthetic facility catalog",
      source: "GET /api/facilities",
      time: selected?.source_timestamp,
    },
    {
      label: "Active alerts",
      value: null,
      icon: TriangleAlert,
      tone: "red",
      detail: "No current alert feed",
      source: "Current weather unavailable",
      time: null,
    },
    {
      label: "Evaluations pending review",
      value: null,
      icon: ClipboardList,
      tone: "amber",
      detail: "Evaluation list unavailable",
      source: "No evaluation-list endpoint",
      time: null,
    },
    {
      label: "Manager-confirmed closures",
      value: closures,
      icon: ShieldCheck,
      tone: "green",
      detail: "Latest synthetic manager actions",
      source: "GET /api/audit · up to 100 records",
      time: resources.audit.checkedAt,
    },
  ];

  return (
    <div
      className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}
      data-reduced-motion={reducedMotion}
    >
      <a className="skip-link" href="#main-content">
        Skip to dashboard
      </a>
      <aside className="sidebar">
        <Brand compact={collapsed} />
        <div className="sidebar-section-label">
          {!collapsed && "OPERATIONS"}
        </div>
        <Navigation
          screen={screen}
          onNavigate={navigate}
          collapsed={collapsed}
        />
        <div className="sidebar-bottom">
          {!collapsed && (
            <div className="sidebar-companion">
              <AssistantMascot state="idle" size="small" />
              <div>
                <strong>Stay informed.</strong>
                <span>Keep people at the center.</span>
              </div>
            </div>
          )}
          <Button
            variant="ghost"
            className="collapse-button"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((c) => !c)}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} />
            ) : (
              <>
                <PanelLeftClose size={18} />
                <span>Collapse sidebar</span>
              </>
            )}
          </Button>
          <span className="sidebar-version">
            {collapsed ? "9B.2" : "LOCAL DEMO · TASK 9B.2"}
          </span>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
            <DialogTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="mobile-menu"
                aria-label="Open navigation"
              >
                <Menu size={21} />
              </Button>
            </DialogTrigger>
            <DialogContent className="mobile-navigation">
              <DialogTitle>
                <Brand />
              </DialogTitle>
              <DialogDescription>
                ClosureOps local demo navigation
              </DialogDescription>
              <Navigation screen={screen} onNavigate={navigate} />
            </DialogContent>
          </Dialog>
          <div className="top-brand">
            <PawPrint size={18} />
            <strong>ClosureOps</strong>
          </div>
          <div className="facility-selector">
            <Building2 size={16} />
            <label className="sr-only" htmlFor="facility-select">
              Selected facility
            </label>
            <select
              id="facility-select"
              value={selected?.id ?? ""}
              disabled={
                !facilities.length || evaluationLoading || workflow.pending
              }
              onChange={(e) => selectFacility(e.target.value)}
            >
              {facilities.length ? (
                facilities.map((f) => (
                  <option value={f.id} key={f.id}>
                    {f.name}
                  </option>
                ))
              ) : (
                <option value="">
                  {resources.facilities.status === "loading"
                    ? "Loading facilities…"
                    : "Facilities unavailable"}
                </option>
              )}
            </select>
          </div>
          <div
            className="search-placeholder"
            aria-label="Search unavailable in this phase"
          >
            <Search size={16} />
            <span>Search unavailable</span>
            <kbd>—</kbd>
          </div>
          <span className="region-context">
            <Globe2 size={15} /> Midwest <ChevronDown size={12} />
          </span>
          <span
            className={`connection-state connection-${connection}`}
            role="status"
            title={`API health check: ${formatTime(resources.health.checkedAt)}`}
          >
            <Activity size={14} />
            {connection === "ready"
              ? "API connected"
              : connection === "loading"
                ? "Checking API"
                : "API offline"}
          </span>
          <Dialog>
            <DialogTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Notification availability"
              >
                <Bell size={18} />
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogTitle>Notifications unavailable</DialogTitle>
              <DialogDescription>
                Prepare group-specific simulated messages after an explicit
                manager decision in Overview. No real notifications are sent.
              </DialogDescription>
            </DialogContent>
          </Dialog>
          <div
            className="manager-identity"
            title="Synthetic Demo Manager · no authentication"
          >
            <span className="manager-avatar">DM</span>
            <div>
              <strong>Demo manager</strong>
              <small>Synthetic · no authentication</small>
            </div>
          </div>
        </header>
        <main id="main-content" className="main-content">
          <div className="demo-banner">
            <FlaskConical size={14} />
            <strong>SIMULATED DEMO</strong>
            <span>
              Synthetic facility · trusted demo evidence · human decisions
              required
            </span>
            <Badge>{writesEnabled ? "LOCAL DEMO WRITES" : "READ ONLY"}</Badge>
          </div>
          <div className="page-heading">
            <div>
              <p className="breadcrumb">
                OPERATIONS <ChevronRight size={11} /> {screen.toUpperCase()}
              </p>
              <h1 ref={pageHeading} tabIndex={-1}>
                {screen === "Overview" ? "Command center" : screen}
              </h1>
              <p>
                {screen === "Overview"
                  ? "The evidence you need. The authority stays with you."
                  : screen === "Decision Queue"
                    ? "Evaluate evidence, confirm a human decision, and prepare simulated messages."
                    : screen === "History"
                      ? "Inspect saved human actions, original evidence, and simulated plans."
                      : screen === "Facilities"
                        ? "Inspect the synthetic facility, recorded configuration, and reference location."
                        : screen === "Alerts"
                          ? "Inspect nationwide NWS alerts separately from saved facility evidence."
                          : screen === "Reports"
                            ? "Summarize loaded human decisions and inspect recorded employee impact."
                            : "Check local system capabilities and manage browser accessibility preferences."}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setWritesDenied(false);
                resources.refresh();
              }}
              disabled={connection === "loading"}
            >
              <RefreshCw
                size={13}
                className={connection === "loading" ? "spin" : ""}
              />{" "}
              Refresh API
            </Button>
          </div>
          {resources.health.error && (
            <div className="api-error" role="alert">
              <TriangleAlert size={16} />
              <span>
                <strong>Local API unavailable.</strong> {resources.health.error}
              </span>
            </div>
          )}
          {resources.facilities.error && connection !== "error" && (
            <p className="api-error" role="alert">
              Facility catalog: {resources.facilities.error}
            </p>
          )}
          {screen === "Overview" || screen === "Decision Queue" ? (
            <>
              <Card className="scenario-workflow">
                <div>
                  <label htmlFor="demo-scenario">1. Choose demo scenario</label>
                  <select
                    id="demo-scenario"
                    value={scenarioId}
                    disabled={
                      evaluationLoading ||
                      workflow.pending ||
                      !resources.scenarios.data?.length
                    }
                    onChange={(event) => setScenarioId(event.target.value)}
                  >
                    {resources.scenarios.data
                      ?.filter((s) => s.facility_id === selected?.id)
                      .map((s) => (
                        <option key={s.scenario_id} value={s.scenario_id}>
                          {s.scenario_id.replaceAll("_", " ")}
                        </option>
                      ))}
                  </select>
                </div>
                <Button
                  disabled={
                    !writesEnabled ||
                    !selected ||
                    evaluationLoading ||
                    workflow.pending ||
                    !resources.scenarios.data?.some(
                      (s) =>
                        s.scenario_id === scenarioId &&
                        s.facility_id === selected.id,
                    )
                  }
                  onClick={() => void createEvaluation()}
                >
                  {evaluationLoading
                    ? "Checking NWS / USGS demo evidence…"
                    : "Evaluate demo scenario"}
                </Button>
                <p>
                  2. Review & confirm a human decision. 3. Prepare simulated
                  notifications.
                  <br />
                  {
                    resources.scenarios.data?.find(
                      (s) =>
                        s.scenario_id === scenarioId &&
                        s.facility_id === selected?.id,
                    )?.disclosure
                  }
                </p>
                {!writesEnabled && (
                  <p role="status">
                    READ ONLY · Restart the local backend with writes enabled to
                    run this workflow.
                  </p>
                )}
                {resources.scenarios.error && (
                  <p className="inline-error" role="alert">
                    {resources.scenarios.error}
                  </p>
                )}
                {evaluationError && (
                  <p className="inline-error" role="alert">
                    {evaluationError}
                  </p>
                )}
              </Card>
              <div className="dashboard-grid">
                <div className="dashboard-main">
                  <div className="metric-grid">
                    {metrics.map(
                      ({
                        label,
                        value,
                        icon: Icon,
                        tone,
                        detail,
                        source,
                        time,
                      }) => (
                        <Card className="metric-card" key={label}>
                          <div className="metric-top">
                            <span className={`metric-icon ${tone}`}>
                              <Icon size={19} />
                            </span>
                            <span className="metric-label">{label}</span>
                          </div>
                          <strong
                            className={`metric-value ${value === null || value === undefined ? "unknown" : ""}`}
                          >
                            {value ?? "Unavailable"}
                          </strong>
                          <p>{detail}</p>
                          <small title={source}>
                            {source}
                            <br />
                            {time
                              ? `${label === "Manager-confirmed closures" ? "Read " : ""}${formatTime(time)}`
                              : "Timestamp unavailable"}
                          </small>
                        </Card>
                      ),
                    )}
                  </div>
                  <div className="operations-grid">
                    <Suspense
                      fallback={
                        <Card className="map-loading">
                          <LoaderCircle className="spin" /> Loading map
                          component…
                        </Card>
                      }
                    >
                      <FacilityMap
                        facilities={facilities}
                        selected={selected}
                        onSelect={selectFacility}
                      />
                    </Suspense>
                    <EvidenceFeed
                      evaluation={visibleEvaluation}
                      onReview={openEvidence}
                    />
                  </div>
                  {workflow.plan && (
                    <NotificationPlanPanel plan={workflow.plan} />
                  )}
                  <Card className="scenario-catalog">
                    <details>
                      <summary>
                        <span>
                          <FlaskConical size={16} />
                          <strong>Demo scenario catalog</strong>
                          <span className="scenario-count">
                            {resources.scenarios.data
                              ? `${resources.scenarios.data.filter((s) => s.facility_id === selected?.id).length} available`
                              : resources.scenarios.status === "loading"
                                ? "Loading…"
                                : "Unavailable"}
                          </span>
                        </span>
                        <ChevronDown size={15} />
                      </summary>
                      <p>
                        Catalog expectations are test fixtures, not evaluated
                        recommendations. Use Evaluate demo scenario to obtain a
                        trusted Python engine result.
                      </p>
                      {resources.scenarios.error ? (
                        <p role="alert" className="inline-error">
                          {resources.scenarios.error}
                        </p>
                      ) : (
                        <div className="scenario-list">
                          {resources.scenarios.data
                            ?.filter((s) => s.facility_id === selected?.id)
                            .map((s) => (
                              <article key={s.scenario_id}>
                                <span>
                                  {s.scenario_id.replaceAll("_", " ")}
                                </span>
                                <Badge
                                  tone={
                                    s.expected_status === "REVIEW_REQUIRED"
                                      ? "amber"
                                      : "neutral"
                                  }
                                >
                                  {s.expected_status === "REVIEW_REQUIRED"
                                    ? "REVIEW_REQUIRED · NO POSTURE"
                                    : `EXPECTED ${s.expected_recommendation}`}
                                </Badge>
                                <small>
                                  {s.source} · {formatTime(s.source_timestamp)}
                                  <br />
                                  Fixture clock:{" "}
                                  {formatTime(s.evaluation_clock)} ·{" "}
                                  {s.data_label}
                                </small>
                                <p>{s.disclosure}</p>
                              </article>
                            ))}
                          {resources.scenarios.data &&
                            !resources.scenarios.data.filter(
                              (s) => s.facility_id === selected?.id,
                            ).length && (
                              <p>
                                No scenarios are configured for the selected
                                facility.
                              </p>
                            )}
                        </div>
                      )}
                    </details>
                  </Card>
                </div>
                <RecommendationPanel
                  aiBriefingEnabled={
                    resources.health.status === "ready" &&
                    resources.health.data?.ai_briefing_enabled === true &&
                    resources.health.data.local_demo_writes_enabled
                  }
                  facility={selected}
                  evaluation={visibleEvaluation}
                  records={
                    workflow.decision
                      ? [workflow.decision, ...(audit ?? [])]
                      : audit
                  }
                  loading={
                    evaluationLoading ||
                    (!visibleEvaluation && workflow.pending)
                  }
                  error={evaluationError}
                  evaluationId={evaluationId}
                  onIdChange={setEvaluationId}
                  onLoad={loadEvaluation}
                  onReview={openEvidence}
                  workflow={workflow}
                  writesEnabled={writesEnabled}
                />
              </div>
              {resources.audit.error && (
                <p className="data-warning" role="status">
                  Decision history unavailable: {resources.audit.error} Closure
                  counts have not been inferred.
                </p>
              )}
              {resources.facilities.status === "ready" &&
                !facilities.length && (
                  <p className="data-warning" role="status">
                    The API returned an empty facility catalog. Selection and
                    evaluation loading are unavailable.
                  </p>
                )}
            </>
          ) : screen === "History" ? (
            <DecisionHistory
              key={historyInspectionId ?? "history"}
              initialId={historyInspectionId}
              resource={resources.audit}
              refresh={resources.refresh}
            />
          ) : screen === "Facilities" ? (
            <FacilitiesPage
              resource={resources.facilities}
              selected={selected}
              evaluation={facilityEvaluation}
              scenarios={resources.scenarios}
              onSelect={selectFacility}
              onEvaluate={() => navigate("Decision Queue")}
              onAlerts={() => navigate("Alerts")}
            />
          ) : screen === "Alerts" ? (
            <AlertsPage
              key={selected?.id ?? "no-facility"}
              evaluations={availableEvaluations}
              current={visibleEvaluation}
              audit={resources.audit}
              onEvaluate={() => navigate("Decision Queue")}
            />
          ) : screen === "Reports" ? (
            <ReportsPage
              resource={resources.audit}
              refresh={resources.refreshAudit}
              onEvaluate={() => navigate("Decision Queue")}
              onInspect={(id) => {
                setHistoryInspectionId(id);
                navigate("History");
              }}
            />
          ) : (
            <SettingsPage
              health={resources.health}
              facilities={resources.facilities}
              audit={resources.audit}
              onRefresh={resources.refresh}
            />
          )}
          <footer className="workspace-footer">
            <span>
              <ShieldCheck size={12} /> Decision support. Human authority.
            </span>
            <span>
              ClosureOps · Hack Midwest 2026{" "}
              <span className="footer-dot">/</span> Local synthetic demo
            </span>
          </footer>
        </main>
      </div>
      <Dialog open={evidenceOpen} onOpenChange={setEvidenceOpen}>
        <DialogContent
          className="evidence-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            evidenceTrigger.current?.focus();
          }}
        >
          <DialogTitle>Evaluation evidence</DialogTitle>
          <DialogDescription>
            Original backend snapshot. Historical source states are preserved;
            evidence has not been refreshed.
          </DialogDescription>
          {visibleEvaluation && (
            <EvaluationEvidence evaluation={visibleEvaluation} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default App;
