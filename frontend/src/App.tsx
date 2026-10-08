import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileText,
  Film,
  Headphones,
  LayoutDashboard,
  ListVideo,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Upload,
  Users,
  X,
  AlertTriangle,
  Info,
  BarChart3,
  RotateCcw,
} from "lucide-react";
import {
  band,
  createDemoInterviews,
  createDemoReviews,
  emptyReview,
  fmtTime,
  makeAnswers,
  reviewKey,
  statusOf,
  tone,
  type Answer,
  type Feedback,
  type Interview,
  type Reviews,
  type ReviewStatus,
} from "./data";

type Page = "overview" | "interviews" | "analytics" | "review" | "summary";
type Filters = {
  period: string;
  role: string;
  team: string;
  interviewer: string;
  from: string;
  to: string;
};
const defaults: Filters = {
  period: "All time",
  role: "All roles",
  team: "All teams",
  interviewer: "All interviewers",
  from: "2026-08-01",
  to: "2026-10-08",
};
const statuses: ReviewStatus[] = [
  "Awaiting review",
  "In review",
  "Follow-up needed",
  "Reviewed",
];
const STORAGE = "techstra-review-mock-v1";
function load() {
  try {
    const x = JSON.parse(localStorage.getItem(STORAGE) || "null");
    if (x?.version === 1 && Array.isArray(x.interviews) && x.reviews) return x;
  } catch {}
  const interviews = createDemoInterviews();
  return { interviews, reviews: createDemoReviews(interviews) };
}
const initial = load();
function download(name: string, value: unknown) {
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = u;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(u), 1000);
}
function Badge({
  children,
  color = "neutral",
}: {
  children: ReactNode;
  color?: string;
}) {
  return (
    <span className={`badge ${color}`}>
      <span className="badge-dot" />
      {children}
    </span>
  );
}
function Panel({
  title,
  subtitle,
  children,
  action,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h3>{title}</h3>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Stat({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: ReactNode;
}) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
function Bars({
  items,
  onSelect,
  empty = "No matching records",
}: {
  items: { label: string; value: number; color?: string; detail?: string }[];
  onSelect?: (label: string) => void;
  empty?: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="bar-list">
      {items.every((i) => !i.value) ? (
        <div className="empty small">{empty}</div>
      ) : (
        items.map((i) => (
          <button
            type="button"
            key={i.label}
            className={`bar-row ${!onSelect ? "static" : ""}`}
            disabled={!onSelect}
            onClick={() => onSelect?.(i.label)}
            aria-label={`${i.label}: ${i.value}${onSelect ? ", show matching interviews" : ""}`}
          >
            <span className="bar-label">{i.label}</span>
            <span className="bar-track">
              <span
                style={{
                  width: `${(i.value / max) * 100}%`,
                  background: i.color || "var(--teal)",
                }}
              />
            </span>
            <strong>{i.value}</strong>
            {i.detail && <small>{i.detail}</small>}
          </button>
        ))
      )}
    </div>
  );
}
function ReviewEditor({
  interview,
  answer,
  reviews,
  onSave,
}: {
  interview: Interview;
  answer: Answer;
  reviews: Reviews;
  onSave: (v: Reviews[string]) => void;
}) {
  const saved = reviews[reviewKey(interview.id, answer.id)] || emptyReview;
  const [draft, setDraft] = useState(saved);
  const dirty = JSON.stringify(saved) !== JSON.stringify(draft);
  return (
    <Panel
      title="Your review"
      subtitle="Your interpretation stays separate from the system signal."
    >
      <label className="field">
        Feedback
        <select
          aria-label="Feedback"
          value={draft.feedback}
          onChange={(e) =>
            setDraft({ ...draft, feedback: e.target.value as Feedback | "" })
          }
        >
          <option value="">Select feedback</option>
          {["Valid signal", "False alarm", "Inconclusive"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </label>
      <label className="field">
        Notes
        <textarea
          placeholder="Add context, an alternative explanation, or a follow-up question…"
          value={draft.notes}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
          rows={4}
        />
      </label>
      <label className="check-label">
        <input
          type="checkbox"
          checked={draft.followup}
          onChange={(e) => setDraft({ ...draft, followup: e.target.checked })}
        />
        Follow-up needed
      </label>
      <label className="check-label">
        <input
          type="checkbox"
          checked={draft.reviewed}
          onChange={(e) => setDraft({ ...draft, reviewed: e.target.checked })}
        />
        Mark this answer reviewed
      </label>
      <div className="editor-footer">
        <span>
          {dirty
            ? "Unsaved changes"
            : reviews[reviewKey(interview.id, answer.id)]
              ? "Saved on this browser"
              : "No review saved"}
        </span>
        <button className="primary" onClick={() => onSave(draft)}>
          <Check size={15} />
          Save review
        </button>
      </div>
    </Panel>
  );
}
function Comparison({
  title,
  value,
  baseline,
  unit,
}: {
  title: string;
  value: number | null;
  baseline: number | null;
  unit: string;
}) {
  const max = Math.max(value || 0, baseline || 0, 1) * 1.15;
  return (
    <div className="comparison">
      <h4>
        {title}
        <span>{unit}</span>
      </h4>
      {[
        ["This answer", value],
        ["Baseline", baseline],
      ].map(([label, v]) => (
        <div className="comparison-row" key={String(label)}>
          <span>{label}</span>
          <div>
            <i
              style={{
                width: `${typeof v === "number" ? (v / max) * 100 : 0}%`,
              }}
            />
          </div>
          <b>{v === null ? "Unavailable" : v}</b>
        </div>
      ))}
    </div>
  );
}
export default function App() {
  const [interviews, setInterviews] = useState<Interview[]>(initial.interviews);
  const [reviews, setReviews] = useState<Reviews>(initial.reviews);
  const [page, setPage] = useState<Page>("overview");
  const [filters, setFilters] = useState<Filters>(defaults);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [bandFilter, setBandFilter] = useState("All signals");
  const [selectedId, setSelectedId] = useState(interviews[0]?.id);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [tab, setTab] = useState("audio");
  const [upload, setUpload] = useState(false);
  const [help, setHelp] = useState(false);
  const [reset, setReset] = useState(false);
  const [toast, setToast] = useState("");
  const [time, setTime] = useState(35);
  const [playing, setPlaying] = useState(false);
  const [media, setMedia] = useState<Record<string, string>>({});
  const video = useRef<HTMLVideoElement>(null);
  const [storageError, setStorageError] = useState(false);
  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE,
        JSON.stringify({ version: 1, interviews, reviews }),
      );
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  }, [interviews, reviews]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(t);
  }, [toast]);
  useEffect(() => {
    if (!playing || media[selectedId]) return;
    const t = setInterval(() => setTime((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [playing, media, selectedId]);
  useEffect(() => {
    if (time >= 800) {
      setPlaying(false);
      setTime(800);
    }
  }, [time]);
  useEffect(() => {
    if (!help && !reset && !upload) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const focusable = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select, textarea, [tabindex="0"]',
        ) || [],
      ).filter((el) => el.getClientRects().length > 0);
    const first = focusable()[0];
    first?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (help) setHelp(false);
        if (reset) setReset(false);
      }
      if (e.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0],
        last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [help, reset, upload]);
  const i = interviews.find((v) => v.id === selectedId) || interviews[0];
  const a = i?.answers[questionIndex] || i?.answers[0];
  const ready = (v: Interview) => v.processing === "Ready";
  const scoreOf = (v: Interview, ans: Answer) => (ready(v) ? ans.score : null);
  const cutoff =
    filters.period === "Last 30 days"
      ? "2026-09-09"
      : filters.period === "Last 7 days"
        ? "2026-10-02"
        : filters.period === "Custom range"
          ? filters.from
          : "";
  const until = filters.period === "Custom range" ? filters.to : "2026-10-08";
  const filtered = interviews.filter(
    (v) =>
      (!cutoff || v.date >= cutoff) &&
      v.date <= until &&
      (filters.role === "All roles" || v.role === filters.role) &&
      (filters.team === "All teams" || v.team === filters.team) &&
      (filters.interviewer === "All interviewers" ||
        v.interviewer === filters.interviewer),
  );
  const rows = filtered.filter(
    (v) =>
      (statusFilter === "All statuses" ||
        statusOf(v, reviews) === statusFilter) &&
      (bandFilter === "All signals" ||
        v.answers.some((q) => band(scoreOf(v, q)) === bandFilter)) &&
      `${v.id} ${v.candidate} ${v.role} ${v.interviewer}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const allAnswers = filtered.flatMap((v) =>
    v.answers.map((q) => ({ ...q, score: scoreOf(v, q) })),
  );
  const reviewed = filtered.filter(
    (v) => statusOf(v, reviews) === "Reviewed",
  ).length;
  const queue = filtered
    .filter((v) => ready(v) && statusOf(v, reviews) !== "Reviewed")
    .sort(
      (x, y) =>
        Number(statusOf(y, reviews) === "Follow-up needed") -
        Number(statusOf(x, reviews) === "Follow-up needed"),
    );
  const openInterview = (id: string) => {
    setSelectedId(id);
    setQuestionIndex(0);
    const v = interviews.find((x) => x.id === id);
    setTime(v?.answers[0]?.start || 0);
    setPlaying(false);
    setPage("review");
  };
  const navigate = (p: Page) => {
    setPage(p);
    setPlaying(false);
  };
  const drill = (status?: string, role?: string, signal?: string) => {
    setSearch("");
    setStatusFilter(status || "All statuses");
    setBandFilter(signal || "All signals");
    if (role) setFilters({ ...filters, role });
    navigate("interviews");
  };
  const seek = (t: number) => {
    setTime(t);
    if (video.current) video.current.currentTime = t;
  };
  const attach = (id: string, file: File) => {
    setMedia((v) => {
      if (v[id]) URL.revokeObjectURL(v[id]);
      return { ...v, [id]: URL.createObjectURL(file) };
    });
    setPlaying(false);
  };
  const exportSummary = () =>
    download(`${i.id}-review-summary.json`, {
      demo: true,
      score_definition:
        "Illustrative review signal strength, 0–9. Not a probability. Bands: 0–2 / 3–5 / 6–9. Not validated.",
      interview: {
        id: i.id,
        candidate: i.candidate,
        role: i.role,
        date: i.date,
        consent: i.consent,
        status: statusOf(i, reviews),
        processing: i.processing,
        quality: i.quality,
      },
      answers: i.answers.map((q) => ({
        ...q,
        score: scoreOf(i, q),
        band: band(scoreOf(i, q)),
        review: reviews[reviewKey(i.id, q.id)] || emptyReview,
      })),
    });
  const title = {
    overview: "Company overview",
    interviews: "Interviews",
    analytics: "Interview analytics",
    review: "Interview review",
    summary: "Review summary",
  }[page];
  const roleItems = Array.from(new Set(interviews.map((v) => v.role))).map(
    (label) => ({
      label,
      value: filtered.filter((v) => v.role === label).length,
    }),
  );
  const statusItems = statuses.map((label, j) => ({
    label,
    value: filtered.filter((v) => statusOf(v, reviews) === label).length,
    color: ["#74909a", "#c79542", "#c77361", "#28877f"][j],
  }));
  const weeks = Array.from({ length: 11 }, (_, j) => {
    const start = new Date(Date.UTC(2026, 6, 27 + j * 7));
    const end = new Date(+start + 6 * 86400000);
    return {
      start: start.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
      label: start.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      }),
      count: filtered.filter(
        (v) =>
          v.date >= start.toISOString().slice(0, 10) &&
          v.date <= end.toISOString().slice(0, 10),
      ).length,
    };
  });
  const activityMax = Math.max(6, ...weeks.map((w) => w.count));
  const table = (data: Interview[], compact = false) => (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Candidate / interview</th>
            <th>Role</th>
            {!compact && <th>Date</th>}
            <th>Review status</th>
            <th>Processing</th>
            <th>
              <span className="sr-only">Open interview</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((v) => (
            <tr key={v.id}>
              <td>
                <button
                  className="candidate"
                  onClick={() => openInterview(v.id)}
                >
                  <span className="avatar">
                    {v.candidate
                      .split(" ")
                      .map((n) => n[0])
                      .join("")}
                  </span>
                  <span>
                    <b>{v.candidate}</b>
                    <small>
                      {v.id} · {v.interviewer}
                    </small>
                  </span>
                </button>
              </td>
              <td>{v.role}</td>
              {!compact && (
                <td>
                  {new Date(v.date + "T12:00:00").toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })}
                </td>
              )}
              <td>
                <Badge
                  color={
                    statusOf(v, reviews) === "Reviewed"
                      ? "teal"
                      : statusOf(v, reviews) === "Follow-up needed"
                        ? "coral"
                        : "amber"
                  }
                >
                  {statusOf(v, reviews)}
                </Badge>
              </td>
              <td>
                <span
                  className={`processing ${v.processing === "Failed" ? "failed" : ""}`}
                >
                  {v.processing === "Ready" ? (
                    <CheckCircle2 size={14} />
                  ) : v.processing === "Failed" ? (
                    <AlertTriangle size={14} />
                  ) : (
                    <Clock3 size={14} />
                  )}{" "}
                  {v.processing}
                </span>
              </td>
              <td>
                <button
                  className="icon-btn"
                  aria-label={`Open ${v.id}`}
                  onClick={() => openInterview(v.id)}
                >
                  <ArrowRight size={17} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!data.length && (
        <div className="empty">
          No interviews match these filters. Try a wider date range.
        </div>
      )}
    </div>
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("overview");
          }}
        >
          <span className="brand-symbol">
            <ShieldCheck size={26} />
          </span>
          <span>
            techstra<small>INTERVIEW INTEGRITY</small>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav>
          {[
            {
              p: "overview",
              label: "Overview",
              icon: <LayoutDashboard size={19} />,
            },
            {
              p: "interviews",
              label: "Interviews",
              icon: <ListVideo size={19} />,
            },
            {
              p: "analytics",
              label: "Analytics",
              icon: <BarChart3 size={19} />,
            },
          ].map((n) => (
            <button
              key={n.p}
              aria-label={n.label}
              className={`nav-item ${page === n.p || (n.p === "interviews" && ["review", "summary"].includes(page)) ? "active" : ""}`}
              onClick={() => {
                if (n.p === "interviews") {
                  setStatusFilter("All statuses");
                  setBandFilter("All signals");
                  setSearch("");
                }
                navigate(n.p as Page);
              }}
            >
              {n.icon}
              {n.label}
              {n.p === "interviews" && <span>{interviews.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="live-dot" />
          PROTOTYPE WORKSPACE
          <h4>
            Evidence. Context.
            <br />
            Human judgment.
          </h4>
          <p>Explore the review experience with fictional interview data.</p>
          <button onClick={() => setHelp(true)}>
            About this demo <ArrowRight size={14} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <button onClick={() => setReset(true)}>
            <RotateCcw size={16} />
            Reset demo
          </button>
          <div className="profile">
            <span className="avatar">SS</span>
            <div>
              <b>Sriya Shabadu</b>
              <small>Demo reviewer</small>
            </div>
            <MoreHorizontal size={18} />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="breadcrumb">Techstra workspace</span>
            <ChevronRight size={14} />
            <b>{title}</b>
          </div>
          <div className="topbar-right">
            <button className="demo-pill" onClick={() => setHelp(true)}>
              <span />
              Demo data <Info size={13} />
            </button>
            <span className="topbar-date">October 8, 2026</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "overview"
                  ? "THE BIG PICTURE"
                  : page === "review" || page === "summary"
                    ? i.id
                    : "INTERVIEW WORKSPACE"}
              </div>
              <h1>{title}</h1>
              <p>
                {page === "overview"
                  ? "A clear view of interview activity and the work ahead."
                  : page === "analytics"
                    ? "Explore patterns, coverage, and the review workflow."
                    : page === "interviews"
                      ? "Find an interview. Review its evidence in context."
                      : `${i.candidate} · ${i.role} · ${i.date}`}
              </p>
            </div>
            {["review", "summary"].includes(page) ? (
              <div className="heading-actions">
                <button
                  className="secondary"
                  onClick={() =>
                    navigate(page === "summary" ? "review" : "interviews")
                  }
                >
                  <ArrowLeft size={16} />
                  {page === "summary" ? "Back to review" : "All interviews"}
                </button>
                <button
                  className="primary"
                  onClick={
                    page === "summary"
                      ? exportSummary
                      : () => navigate("summary")
                  }
                >
                  {page === "summary" ? (
                    <ArrowDownToLine size={16} />
                  ) : (
                    <FileText size={16} />
                  )}{" "}
                  {page === "summary" ? "Export summary" : "Review summary"}
                </button>
              </div>
            ) : (
              <button className="primary" onClick={() => setUpload(true)}>
                <Plus size={18} />
                Add interview
              </button>
            )}
          </div>
          {storageError && (
            <div className="notice warning">
              Browser storage is unavailable. Changes will last only until you
              close this page.
            </div>
          )}
          {!["review", "summary"].includes(page) && (
            <div className="filters">
              <SlidersHorizontal size={17} />
              <label>
                <span className="sr-only">Date range</span>
                <select
                  value={filters.period}
                  onChange={(e) =>
                    setFilters({ ...filters, period: e.target.value })
                  }
                >
                  {[
                    "All time",
                    "Last 30 days",
                    "Last 7 days",
                    "Custom range",
                  ].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
              {filters.period === "Custom range" && (
                <>
                  <input
                    aria-label="Start date"
                    type="date"
                    value={filters.from}
                    onChange={(e) =>
                      setFilters({ ...filters, from: e.target.value })
                    }
                  />
                  <input
                    aria-label="End date"
                    type="date"
                    value={filters.to}
                    onChange={(e) =>
                      setFilters({ ...filters, to: e.target.value })
                    }
                  />
                </>
              )}
              {(["role", "team", "interviewer"] as const).map((key) => (
                <label key={key}>
                  <span className="sr-only">{key}</span>
                  <select
                    aria-label={key}
                    value={filters[key]}
                    onChange={(e) =>
                      setFilters({ ...filters, [key]: e.target.value })
                    }
                  >
                    <option>{defaults[key]}</option>
                    {Array.from(new Set(interviews.map((v) => v[key]))).map(
                      (v) => (
                        <option key={v}>{v}</option>
                      ),
                    )}
                  </select>
                </label>
              ))}
              <button
                className="text-btn filter-reset"
                onClick={() => {
                  setFilters(defaults);
                  setSearch("");
                  setStatusFilter("All statuses");
                  setBandFilter("All signals");
                }}
              >
                Reset filters
              </button>
              <span className="filter-count">{filtered.length} interviews</span>
            </div>
          )}
          {(page === "overview" || page === "analytics") && (
            <div className="stats-grid">
              <Stat
                label="Total interviews"
                value={filtered.length}
                detail="Registered in this demo workspace"
                icon={<Users size={19} />}
              />
              <Stat
                label="Awaiting review"
                value={
                  filtered.filter(
                    (v) => statusOf(v, reviews) === "Awaiting review",
                  ).length
                }
                detail="Interviews with review not started"
                icon={<Clock3 size={19} />}
              />
              <Stat
                label="Follow-up needed"
                value={
                  filtered.filter(
                    (v) => statusOf(v, reviews) === "Follow-up needed",
                  ).length
                }
                detail="Interviews needing reviewer attention"
                icon={<FileText size={19} />}
              />
              <Stat
                label="Review completion"
                value={
                  filtered.length
                    ? `${Math.round((reviewed / filtered.length) * 100)}%`
                    : "—"
                }
                detail={`${reviewed} of ${filtered.length} interviews reviewed`}
                icon={<CheckCircle2 size={19} />}
              />
            </div>
          )}
          {page === "overview" && (
            <>
              <div className="overview-grid">
                <Panel
                  title="Interview activity"
                  subtitle="Interviews by week · click a bar to explore"
                  action={
                    <span className="chart-legend">
                      <i />
                      Interview count
                    </span>
                  }
                >
                  <div className="activity-chart">
                    <div className="y-axis">
                      {[
                        activityMax,
                        Math.round((activityMax * 2) / 3),
                        Math.round(activityMax / 3),
                        0,
                      ].map((v) => (
                        <span key={v}>{v}</span>
                      ))}
                    </div>
                    <div className="activity-columns">
                      {weeks.map((w) => (
                        <button
                          key={w.start}
                          aria-label={`${w.label}: ${w.count} interviews`}
                          title={`${w.label}: ${w.count} interviews`}
                          onClick={() => {
                            setFilters({
                              ...filters,
                              period: "Custom range",
                              from: w.start,
                              to: w.end,
                            });
                            drill();
                          }}
                        >
                          <div className="column-space">
                            <span
                              style={{
                                height: `${(w.count / activityMax) * 100}%`,
                              }}
                            >
                              <b>{w.count}</b>
                            </span>
                          </div>
                          <small>{w.label}</small>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="chart-footer">
                    <span>Fictional data · Jul–Oct 2026</span>
                    <button
                      className="text-btn"
                      onClick={() => navigate("analytics")}
                    >
                      Explore analytics <ArrowRight size={14} />
                    </button>
                  </div>
                </Panel>
                <Panel
                  title="Review workload"
                  subtitle="Interview count by current review status"
                >
                  <Bars items={statusItems} onSelect={(s) => drill(s)} />
                  <div className="workload-footer">
                    <div className="progress-track">
                      <span
                        style={{
                          width: `${filtered.length ? (reviewed / filtered.length) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <p>
                      <b>{reviewed}</b> interviews reviewed in this selection
                    </p>
                  </div>
                </Panel>
              </div>
              <div className="lower-grid">
                <Panel
                  title="Ready for your review"
                  subtitle="Follow-ups first, then interviews awaiting review"
                  action={
                    <button className="text-btn" onClick={() => drill()}>
                      View all <ArrowRight size={14} />
                    </button>
                  }
                >
                  {table(queue.slice(0, 4), true)}
                </Panel>
                <Panel
                  title="Interviews by role"
                  subtitle="Click a role to open its interviews"
                >
                  <Bars
                    items={roleItems}
                    onSelect={(r) => drill(undefined, r)}
                  />
                  <div className="tip">
                    <Info size={16} />
                    <p>
                      Every observation has context. Open an interview to see
                      its transcript and supporting timestamps.
                    </p>
                  </div>
                </Panel>
              </div>
            </>
          )}
          {page === "interviews" && (
            <Panel
              title="Interview directory"
              subtitle={`${rows.length} matching interviews`}
            >
              <div className="directory-tools">
                <div className="search-field">
                  <Search size={17} />
                  <input
                    aria-label="Search interviews"
                    placeholder="Search candidate, role, or interview ID"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <select
                  aria-label="Review status filter"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option>All statuses</option>
                  {statuses.map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
                <select
                  aria-label="Signal filter"
                  value={bandFilter}
                  onChange={(e) => setBandFilter(e.target.value)}
                >
                  <option>All signals</option>
                  {["Low signal", "Review", "Strong signal", "Unscored"].map(
                    (v) => (
                      <option key={v}>{v}</option>
                    ),
                  )}
                </select>
              </div>
              {bandFilter !== "All signals" && (
                <div className="inline-note">
                  Showing interviews with at least one{" "}
                  {bandFilter.toLowerCase()} answer. Signal bands are
                  illustrative.
                </div>
              )}
              {table(rows)}
            </Panel>
          )}
          {page === "analytics" && (
            <>
              <div className="notice">
                <Info size={17} />
                <span>
                  Signal charts use illustrative answer-level scores, not
                  validated detection results. No score is a probability of AI
                  use.
                </span>
                <button className="text-btn" onClick={() => setHelp(true)}>
                  Scale details
                </button>
              </div>
              <div className="analytics-grid">
                <Panel
                  title="Answer signal distribution"
                  subtitle={`${allAnswers.length} answers · unscored answers included`}
                >
                  <Bars
                    items={[
                      "Low signal",
                      "Review",
                      "Strong signal",
                      "Unscored",
                    ].map((label, j) => ({
                      label,
                      value: allAnswers.filter((q) => band(q.score) === label)
                        .length,
                      color: ["#28877f", "#c79542", "#c77361", "#a8b5ba"][j],
                    }))}
                    onSelect={(s) => drill(undefined, undefined, s)}
                  />
                  <div className="inline-note">
                    Click a band to find interviews containing those answers.
                  </div>
                </Panel>
                <Panel
                  title="Recording quality"
                  subtitle="Interview count · quality is separate from review signals"
                >
                  <Bars
                    items={["Good", "Limited audio", "Missing transcript"].map(
                      (label, j) => ({
                        label,
                        value: filtered.filter((v) => v.quality === label)
                          .length,
                        color: ["#28877f", "#c79542", "#8497a0"][j],
                      }),
                    )}
                  />
                </Panel>
                <Panel
                  title="Modality coverage"
                  subtitle="Ready interviews with usable observations · interview count"
                >
                  <Bars
                    items={["Audio", "Transcript", "Video"].map((label) => ({
                      label,
                      value: filtered.filter(
                        (v) =>
                          ready(v) &&
                          (label === "Audio"
                            ? v.quality !== "Limited audio"
                            : label === "Transcript"
                              ? v.quality !== "Missing transcript"
                              : false),
                      ).length,
                      color: "#4b8995",
                    }))}
                  />
                  <div className="inline-note">
                    Video analysis is planned. Media playback is available
                    separately.
                  </div>
                </Panel>
                <Panel
                  title="Reviewer feedback"
                  subtitle="Saved feedback in this browser · answer count"
                >
                  <Bars
                    items={["Valid signal", "False alarm", "Inconclusive"].map(
                      (label, j) => ({
                        label,
                        value: filtered
                          .flatMap((v) =>
                            v.answers.map(
                              (q) => reviews[reviewKey(v.id, q.id)],
                            ),
                          )
                          .filter((r) => r?.feedback === label).length,
                        color: ["#28877f", "#c77361", "#8497a0"][j],
                      }),
                    )}
                    empty="Save answer feedback to populate this chart."
                  />
                  <div className="inline-note">
                    Reviewer interpretation is not labeled ground truth or
                    detection accuracy.
                  </div>
                </Panel>
                <Panel
                  title="Interviewers"
                  subtitle="Interview count in the selected period"
                >
                  <Bars
                    items={Array.from(
                      new Set(interviews.map((v) => v.interviewer)),
                    ).map((label) => ({
                      label,
                      value: filtered.filter((v) => v.interviewer === label)
                        .length,
                    }))}
                    onSelect={(name) => {
                      setFilters({ ...filters, interviewer: name });
                      drill();
                    }}
                  />
                </Panel>
                <Panel
                  title="Interviews by role"
                  subtitle="Click to drill into an interview list"
                >
                  <Bars
                    items={roleItems}
                    onSelect={(r) => drill(undefined, r)}
                  />
                </Panel>
              </div>
            </>
          )}
          {page === "review" && i && a && (
            <>
              <div className="session-meta">
                <Badge
                  color={statusOf(i, reviews) === "Reviewed" ? "teal" : "amber"}
                >
                  {statusOf(i, reviews)}
                </Badge>
                <span>
                  <ShieldCheck size={15} />
                  {i.consent ? "Consent recorded" : "Consent missing"}
                </span>
                <span>
                  <Clock3 size={15} />
                  {i.processing}
                </span>
                <span>
                  <Users size={15} />
                  {i.interviewer}
                </span>
                <span>Scoring version: demo-v1</span>
              </div>
              {!ready(i) && (
                <div className="notice warning">
                  <AlertTriangle size={18} />
                  {i.processing === "Failed"
                    ? "Processing failed. No analysis results are available."
                    : "Processing is simulated and still pending for this sample. No analysis results are available."}
                  <button
                    className="text-btn"
                    onClick={() => {
                      setInterviews((v) =>
                        v.map((x) =>
                          x.id === i.id ? { ...x, processing: "Ready" } : x,
                        ),
                      );
                      setToast(
                        "Demo processing completed. Results are illustrative.",
                      );
                    }}
                  >
                    Simulate completion
                  </button>
                </div>
              )}
              <div className="review-layout">
                <aside className="question-panel">
                  <div className="question-heading">
                    <h3>Questions</h3>
                    <span>{i.answers.length} answers</span>
                  </div>
                  {i.answers.map((q, j) => (
                    <button
                      className={`question-item ${j === questionIndex ? "selected" : ""}`}
                      key={q.id}
                      onClick={() => {
                        setQuestionIndex(j);
                        seek(q.start);
                      }}
                    >
                      <div>
                        <span>{q.id}</span>
                        {reviews[reviewKey(i.id, q.id)]?.reviewed && (
                          <CheckCircle2 size={15} />
                        )}
                      </div>
                      <p>{q.question}</p>
                      <div>
                        <Badge color={tone(scoreOf(i, q))}>
                          {scoreOf(i, q) === null
                            ? "Unscored"
                            : `${scoreOf(i, q)}/9 · ${band(q.score)}`}
                        </Badge>
                        <small>{fmtTime(q.start)}</small>
                      </div>
                    </button>
                  ))}
                  <div className="scale-key">
                    <h4>Illustrative scale</h4>
                    <span>
                      <i className="teal-dot" />
                      0–2 Low signal
                    </span>
                    <span>
                      <i className="amber-dot" />
                      3–5 Review
                    </span>
                    <span>
                      <i className="coral-dot" />
                      6–9 Strong signal
                    </span>
                    <p>Thresholds await validation.</p>
                  </div>
                </aside>
                <div className="review-center">
                  <Panel
                    title="Signals across questions"
                    subtitle="Illustrative answer-level strength · select a question"
                  >
                    <div className="question-chart">
                      {i.answers.map((q, j) => (
                        <button
                          key={q.id}
                          onClick={() => {
                            setQuestionIndex(j);
                            seek(q.start);
                          }}
                          className={j === questionIndex ? "selected" : ""}
                          aria-label={`${q.id}: ${scoreOf(i, q) === null ? "unscored" : scoreOf(i, q) + " of 9"}`}
                        >
                          <strong>
                            {scoreOf(i, q) === null ? "—" : scoreOf(i, q)}
                          </strong>
                          <div>
                            <span
                              className={tone(scoreOf(i, q))}
                              style={{
                                height: `${scoreOf(i, q) === null ? 0 : Math.max(4, (Number(scoreOf(i, q)) / 9) * 100)}%`,
                              }}
                            />
                          </div>
                          <small>{q.id}</small>
                        </button>
                      ))}
                    </div>
                  </Panel>
                  <Panel
                    title={`${a.id} · Answer details`}
                    subtitle={a.question}
                    action={
                      <Badge color={tone(scoreOf(i, a))}>
                        {scoreOf(i, a) === null
                          ? "Unscored"
                          : `${scoreOf(i, a)}/9`}
                      </Badge>
                    }
                  >
                    <div className="player">
                      {media[i.id] ? (
                        <video
                          ref={video}
                          src={media[i.id]}
                          controls
                          onTimeUpdate={(e) =>
                            setTime(e.currentTarget.currentTime)
                          }
                          onPlay={() => setPlaying(true)}
                          onPause={() => setPlaying(false)}
                        />
                      ) : (
                        <div className="player-placeholder">
                          <div className="player-grid" />
                          <div className="media-symbol">
                            <Film size={34} />
                          </div>
                          <h4>Recording preview</h4>
                          <p>
                            Attach a local video to review your player layout.
                            <br />
                            Sample transcript and signals remain fictional.
                          </p>
                          <label className="player-attach">
                            <Upload size={15} />
                            Choose local video
                            <input
                              type="file"
                              accept="video/*"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f) attach(i.id, f);
                              }}
                            />
                          </label>
                          <span className="player-demo">
                            SIMULATED PLAYBACK
                          </span>
                        </div>
                      )}
                      <div className="player-controls">
                        <button
                          aria-label={
                            playing ? "Pause playback" : "Play playback"
                          }
                          onClick={() => {
                            if (media[i.id] && video.current) {
                              if (playing) video.current.pause();
                              else
                                void video.current
                                  .play()
                                  .catch(() =>
                                    setToast(
                                      "This file could not be played. Try an MP4 video.",
                                    ),
                                  );
                            } else setPlaying(!playing);
                          }}
                        >
                          {playing ? <Pause size={17} /> : <Play size={17} />}
                        </button>
                        <span>{fmtTime(time)}</span>
                        <input
                          aria-label="Recording position"
                          type="range"
                          min="0"
                          max="800"
                          value={Math.min(time, 800)}
                          onChange={(e) => seek(Number(e.target.value))}
                        />
                        <span>13:20 demo</span>
                      </div>
                    </div>
                    <div className="answer-timeline">
                      <div>
                        <b>Answer window</b>
                        <span>
                          {fmtTime(a.start)}–{fmtTime(a.end)}
                        </span>
                      </div>
                      <button
                        onClick={() => seek(a.start)}
                        className="window-track"
                        aria-label="Jump to answer window"
                      >
                        <span
                          style={{
                            left: `${(a.start / 800) * 100}%`,
                            width: `${((a.end - a.start) / 800) * 100}%`,
                          }}
                        />
                        <i
                          style={{
                            left: `${(Math.min(time, 800) / 800) * 100}%`,
                          }}
                        />
                      </button>
                      <small>
                        Observations cover this answer window; exact event times
                        are not available.
                      </small>
                    </div>
                  </Panel>
                  <Panel
                    title="Transcript"
                    subtitle="Illustrative segment timestamps · click to seek"
                    action={<FileText size={17} />}
                  >
                    <div className="transcript">
                      {ready(i) && a.transcript.length ? (
                        a.transcript.map((t, j) => (
                          <button
                            key={t.start}
                            className={
                              time >= t.start &&
                              time < (a.transcript[j + 1]?.start || a.end)
                                ? "current"
                                : ""
                            }
                            onClick={() => seek(t.start)}
                          >
                            <span>{fmtTime(t.start)}</span>
                            <p>{t.text}</p>
                          </button>
                        ))
                      ) : (
                        <div className="empty">
                          {ready(i)
                            ? "Transcript unavailable. No text observations can be measured."
                            : "Transcript results unavailable until processing completes."}
                        </div>
                      )}
                    </div>
                  </Panel>
                  <Panel
                    title="Candidate baseline"
                    subtitle="Descriptive comparisons, not proof of assistance"
                  >
                    <Comparison
                      title="Speech rate"
                      value={ready(i) ? a.speechRate : null}
                      baseline={ready(i) ? a.baselineRate : null}
                      unit="words/min"
                    />
                    <Comparison
                      title="Response latency"
                      value={ready(i) ? a.latency : null}
                      baseline={ready(i) ? a.baselineLatency : null}
                      unit="seconds"
                    />
                    <div className="inline-note">
                      Baseline values are fictional calibration measurements.
                      Missing measurements stay unavailable.
                    </div>
                  </Panel>
                </div>
                <aside className="review-right">
                  <Panel
                    title="Review signal"
                    subtitle="Illustrative strength · not an AI-use probability"
                  >
                    <div className={`score-display ${tone(scoreOf(i, a))}`}>
                      <strong>
                        {scoreOf(i, a) === null ? "—" : scoreOf(i, a)}
                      </strong>
                      <span>/ 9</span>
                      <Badge color={tone(scoreOf(i, a))}>
                        {band(scoreOf(i, a))}
                      </Badge>
                    </div>
                    <div className="score-scale">
                      {Array.from({ length: 10 }, (_, j) => (
                        <span
                          key={j}
                          className={`${tone(j)} ${j === scoreOf(i, a) ? "marker" : ""}`}
                        />
                      ))}
                    </div>
                    <p className="signal-note">
                      {scoreOf(i, a) === null
                        ? "Insufficient data or processing incomplete."
                        : "This demo score is a sample UI value. The observations below do not calculate or validate this score."}
                    </p>
                  </Panel>
                  <Panel
                    title="Supporting observations"
                    subtitle="Measurements for this answer"
                  >
                    <div
                      className="tabs"
                      role="tablist"
                      aria-label="Observation modality"
                    >
                      {[
                        {
                          id: "audio",
                          label: "Audio",
                          icon: <Headphones size={14} />,
                        },
                        {
                          id: "transcript",
                          label: "Text",
                          icon: <FileText size={14} />,
                        },
                        {
                          id: "visual",
                          label: "Video",
                          icon: <Film size={14} />,
                        },
                      ].map((t) => (
                        <button
                          role="tab"
                          aria-selected={tab === t.id}
                          key={t.id}
                          className={tab === t.id ? "active" : ""}
                          onClick={() => setTab(t.id)}
                        >
                          {t.icon}
                          {t.label}
                        </button>
                      ))}
                    </div>
                    {tab === "visual" ? (
                      <div className="planned">
                        <Film size={25} />
                        <h4>Video analysis is planned</h4>
                        <p>
                          No visual model is connected. Local playback lets you
                          inspect the recording yourself.
                        </p>
                      </div>
                    ) : ready(i) ? (
                      a.signals
                        .filter((s) => s.modality === tab)
                        .map((s) => (
                          <div className="observation" key={s.signal_name}>
                            <div>
                              <h4>{s.signal_name.replaceAll("_", " ")}</h4>
                              <b>
                                {s.value === null ? "Unavailable" : s.value}
                              </b>
                            </div>
                            <p>{s.explanation}</p>
                            <button
                              className="timestamp"
                              onClick={() =>
                                seek(s.supporting_timestamps[0][0])
                              }
                            >
                              <Clock3 size={12} />
                              {fmtTime(s.supporting_timestamps[0][0])}–
                              {fmtTime(s.supporting_timestamps[0][1])}
                              <ArrowRight size={12} />
                            </button>
                          </div>
                        ))
                    ) : (
                      <div className="empty small">
                        Processing results unavailable.
                      </div>
                    )}
                  </Panel>
                  <div
                    className={`quality-box ${i.quality === "Good" ? "" : "limited"}`}
                  >
                    <AlertTriangle size={17} />
                    <div>
                      <b>Recording quality: {i.quality}</b>
                      <p>
                        {i.quality === "Good"
                          ? "No demo quality limitations recorded."
                          : i.quality === "Limited audio"
                            ? "Audio measurements are unavailable. Noise is a limitation, not evidence."
                            : "Text observations are unavailable. Other modalities may still be reviewed."}
                      </p>
                    </div>
                  </div>
                  <ReviewEditor
                    key={`${i.id}/${a.id}`}
                    interview={i}
                    answer={a}
                    reviews={reviews}
                    onSave={(v) => {
                      setReviews({ ...reviews, [reviewKey(i.id, a.id)]: v });
                      setToast("Review saved on this browser.");
                    }}
                  />
                </aside>
              </div>
            </>
          )}
          {page === "summary" && (
            <>
              <div className="summary-grid">
                <Stat
                  label="Answers reviewed"
                  value={`${i.answers.filter((q) => reviews[reviewKey(i.id, q.id)]?.reviewed).length} / ${i.answers.length}`}
                  detail="Explicitly marked reviewed by you"
                  icon={<CheckCircle2 size={19} />}
                />
                <Stat
                  label="Follow-ups"
                  value={
                    i.answers.filter(
                      (q) => reviews[reviewKey(i.id, q.id)]?.followup,
                    ).length
                  }
                  detail="Answers marked for follow-up"
                  icon={<FileText size={19} />}
                />
                <Stat
                  label="Consent"
                  value={i.consent ? "Recorded" : "Missing"}
                  detail="Demo session metadata"
                  icon={<ShieldCheck size={19} />}
                />
              </div>
              <Panel
                title="Question-level review"
                subtitle="Review signals and your feedback, kept separate"
              >
                <div className="summary-answers">
                  {i.answers.map((q, j) => {
                    const r = reviews[reviewKey(i.id, q.id)] || emptyReview;
                    return (
                      <article key={q.id}>
                        <div>
                          <button
                            className="text-btn"
                            onClick={() => {
                              setQuestionIndex(j);
                              seek(q.start);
                              navigate("review");
                            }}
                          >
                            {q.id} · {fmtTime(q.start)} <ArrowRight size={14} />
                          </button>
                          <Badge color={tone(scoreOf(i, q))}>
                            {scoreOf(i, q) === null
                              ? "Unscored"
                              : `${scoreOf(i, q)}/9 · ${band(q.score)}`}
                          </Badge>
                        </div>
                        <h4>{q.question}</h4>
                        <p>
                          <b>Reviewer feedback:</b>{" "}
                          {r.feedback || "Not provided"} ·{" "}
                          {r.reviewed ? "Reviewed" : "Not yet reviewed"}
                          {r.followup ? " · Follow-up needed" : ""}
                        </p>
                        <p className="summary-note">
                          {r.notes || "No notes saved."}
                        </p>
                      </article>
                    );
                  })}
                </div>
              </Panel>
              <div className="notice">
                <Info size={17} />
                Export includes fictional transcript, observations, scores, and
                your saved feedback. Media files are never included.
              </div>
            </>
          )}
          <footer className="page-footer">
            <span>TECHSTRA × CMU HEINZ COLLEGE</span>
            <span>Prototype · Fictional data · Human review required</span>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={17} />
          {toast}
        </div>
      )}
      {upload && (
        <UploadModal
          onClose={() => setUpload(false)}
          onCreate={(name, role, interviewer, file, consent) => {
            const id = `INT-DEMO-${Date.now().toString().slice(-6)}`;
            const created: Interview = {
              id,
              candidate: name,
              role,
              team:
                role === "Data Engineer" || role === "BI Analyst"
                  ? "Data & Analytics"
                  : "Engineering",
              interviewer,
              date: "2026-10-08",
              status: "Awaiting review",
              processing: "Ready",
              consent,
              quality: "Good",
              answers: makeAnswers(id, 0, "Good"),
            };
            setInterviews((v) => [created, ...v]);
            if (file) attach(id, file);
            setFilters(defaults);
            setUpload(false);
            setSelectedId(id);
            setQuestionIndex(0);
            setTime(35);
            navigate("review");
            setToast("Demo interview created. Analysis results are fictional.");
          }}
        />
      )}
      {help && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="demo-title"
          >
            <button
              className="modal-close icon-btn"
              aria-label="Close demo details"
              onClick={() => setHelp(false)}
            >
              <X size={20} />
            </button>
            <div className="modal-icon">
              <ShieldCheck size={26} />
            </div>
            <h2 id="demo-title">A workspace for human review</h2>
            <p>
              This standalone mock demonstrates the proposed Techstra interface.
              All interviews, transcripts, baseline values, and scores are
              fictional.
            </p>
            <div className="help-bands">
              <Badge color="teal">0–2 Low signal</Badge>
              <Badge color="amber">3–5 Review</Badge>
              <Badge color="coral">6–9 Strong signal</Badge>
            </div>
            <p>
              The 0–9 scale is illustrative signal strength, not probability or
              proof of AI use. Thresholds, fusion, and scoring require team
              agreement and validation. Backend evidence confidence remains
              null.
            </p>
            <p>
              Notes and demo records are saved only in this browser. Attached
              videos stay local and must be reattached after reload. No API,
              login, cloud upload, or live monitoring is connected.
            </p>
            <button className="primary" onClick={() => setHelp(false)}>
              Continue exploring <ArrowRight size={16} />
            </button>
          </section>
        </div>
      )}
      {reset && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-title"
          >
            <h2 id="reset-title">Reset this demo?</h2>
            <p>
              This clears your local notes, feedback, and added demo interviews.
              The original fictional data will be restored.
            </p>
            <div className="heading-actions">
              <button className="secondary" onClick={() => setReset(false)}>
                Keep my changes
              </button>
              <button
                className="primary"
                onClick={() => {
                  Object.values(media).forEach((u) => URL.revokeObjectURL(u));
                  setMedia({});
                  const demo = createDemoInterviews();
                  setInterviews(demo);
                  setSelectedId(demo[0].id);
                  setReviews(createDemoReviews(demo));
                  setFilters(defaults);
                  setSearch("");
                  setStatusFilter("All statuses");
                  setBandFilter("All signals");
                  setPlaying(false);
                  setReset(false);
                  navigate("overview");
                  setToast("Demo reset.");
                }}
              >
                Reset demo
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
function UploadModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (
    name: string,
    role: string,
    interviewer: string,
    file: File | null,
    consent: boolean,
  ) => void;
}) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("Data Engineer");
  const [interviewer, setInterviewer] = useState("Priya Nair");
  const [consent, setConsent] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!busy) return;
    const t = setTimeout(() => {
      if (step < 3) setStep(step + 1);
      else onCreate(name.trim(), role, interviewer, file, consent);
    }, 600);
    return () => clearTimeout(t);
  }, [busy, step, name, role, interviewer, file, consent, onCreate]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [busy, onClose]);
  return (
    <div className="modal-backdrop">
      <section
        className="modal upload-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-title"
      >
        <button
          className="modal-close icon-btn"
          aria-label="Close add interview"
          disabled={busy}
          onClick={onClose}
        >
          <X size={20} />
        </button>
        <div className="modal-icon">
          <Upload size={26} />
        </div>
        <h2 id="upload-title">Add a demo interview</h2>
        <p>Try the intake workflow. Processing and analysis are simulated.</p>
        {busy ? (
          <div className="processing-steps">
            {[
              "Register interview",
              "Check recording",
              "Prepare sample observations",
              "Open review workspace",
            ].map((s, j) => (
              <div className={j <= step ? "done" : ""} key={s}>
                {j < step ? <CheckCircle2 size={20} /> : <Clock3 size={20} />}
                <span>{s}</span>
                {j === step && <small>Simulating…</small>}
              </div>
            ))}
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim() && consent) setBusy(true);
            }}
          >
            <label className="drop-zone">
              <Upload size={24} />
              <b>{file ? file.name : "Choose a local video (optional)"}</b>
              <span>Video stays on your computer. No upload occurs.</span>
              <input
                type="file"
                accept="video/*"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <label className="field">
              Candidate display name
              <input
                autoFocus
                required
                maxLength={80}
                value={name}
                placeholder="Use a fictional name"
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <div className="form-row">
              <label className="field">
                Role
                <select value={role} onChange={(e) => setRole(e.target.value)}>
                  {[
                    "Data Engineer",
                    "Java Developer",
                    "BI Analyst",
                    "ML Engineer",
                  ].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                Interviewer
                <select
                  value={interviewer}
                  onChange={(e) => setInterviewer(e.target.value)}
                >
                  {["Priya Nair", "Michael Evans", "Paul Bennett"].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            </div>
            <label className="check-label">
              <input
                required
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              Monitoring consent recorded for this demo session
            </label>
            <div className="notice compact">
              <Info size={16} />
              <span>
                The sample transcript and scores will not be derived from your
                video.
              </span>
            </div>
            <button
              className="primary full-width"
              disabled={!name.trim() || !consent}
              type="submit"
            >
              Simulate processing <ArrowRight size={16} />
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
