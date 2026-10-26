import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Bookmark,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  Film,
  Headphones,
  LayoutDashboard,
  ListVideo,
  Pause,
  Play,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  X,
  AlertTriangle,
  Info,
  Printer,
  MoreHorizontal,
  RotateCcw,
} from "lucide-react";
import {
  band,
  createDemoInterviews,
  createDemoReviews,
  emptyReview,
  fmtTime,
  reviewKey,
  statusOf,
  tone,
  type Answer,
  type Feedback,
  type Interview,
  type Reviews,
  type Review,
} from "./data";
import { logo } from "./logo";

type Page = "overview" | "interviews" | "review" | "summary";
type Route = { page: Page; id?: string; question?: string };
const STORE = "techstra-review-v2";
const statusNames = [
  "Awaiting review",
  "In review",
  "Follow-up needed",
  "Reviewed",
];
const feedbackNames: Feedback[] = [
  "Relevant",
  "Explained by context",
  "Inconclusive",
];
function load() {
  try {
    const saved = JSON.parse(
      localStorage.getItem(STORE) ||
        localStorage.getItem("techstra-review-mock-v1") ||
        "null",
    );
    if (
      saved &&
      Array.isArray(saved.interviews) &&
      saved.interviews.length &&
      saved.reviews
    ) {
      const reviews: Reviews = Object.fromEntries(
        Object.entries(saved.reviews as Reviews).map(([k, v]) => [
          k,
          {
            ...v,
            feedback:
              String(v.feedback) === "Valid signal"
                ? "Relevant"
                : String(v.feedback) === "False alarm"
                  ? "Explained by context"
                  : v.feedback,
          },
        ]),
      );
      return {
        interviews: saved.interviews.map((i: Interview) => ({
          ...i,
          completedAt:
            i.completedAt ??
            (i.status === "Reviewed" ? i.date + "T12:00:00Z" : null),
        })) as Interview[],
        reviews,
      };
    }
  } catch {}
  const interviews = createDemoInterviews();
  return { interviews, reviews: createDemoReviews(interviews) };
}
const initial = load();
function readRoute(): Route {
  const match = location.hash.match(
    /^#\/interviews\/([^/?]+)(\/summary)?(?:\?question=([^&]+))?/,
  );
  if (match)
    return {
      page: match[2] ? "summary" : "review",
      id: decodeURIComponent(match[1]),
      question: match[3],
    };
  return { page: location.hash === "#/overview" ? "overview" : "interviews" };
}
function download(name: string, value: unknown) {
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = u;
  link.download = name;
  link.click();
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
  children,
  action,
  className = "",
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <h3>{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}
function Stat({
  label,
  value,
  icon,
  onClick,
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
  onClick?: () => void;
}) {
  return (
    <button className="stat stat-button" disabled={!onClick} onClick={onClick}>
      <div className="stat-top">
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
    </button>
  );
}
function Bars({
  items,
  onSelect,
}: {
  items: { label: string; value: number; color?: string }[];
  onSelect?: (label: string) => void;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="bar-list">
      {items.map((i) => (
        <button
          key={i.label}
          className={`bar-row ${onSelect ? "" : "static"}`}
          disabled={!onSelect}
          onClick={() => onSelect?.(i.label)}
          aria-label={`${i.label}: ${i.value}`}
        >
          <span className="bar-label">{i.label}</span>
          <span className="bar-track">
            <span
              style={{
                width: `${(i.value / max) * 100}%`,
                background: i.color || "var(--brand-chart)",
              }}
            />
          </span>
          <strong>{i.value}</strong>
        </button>
      ))}
    </div>
  );
}
function Compare({
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
  const max = Math.max(value || 0, baseline || 0, 1) * 1.1;
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
                width: typeof v === "number" ? `${(v / max) * 100}%` : "0%",
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
  const [interviews, setInterviews] = useState<Interview[]>(initial.interviews),
    [reviews, setReviews] = useState<Reviews>(initial.reviews);
  const [route, setRoute] = useState<Route>(readRoute),
    [selectedQ, setSelectedQ] = useState(readRoute().question || "Q01");
  const [filters, setFilters] = useState({
    role: "All roles",
    interviewer: "All interviewers",
    period: "All time",
    status: "All statuses",
    band: "All signals",
    search: "",
  });
  const [questionFilter, setQuestionFilter] = useState(false),
    [tab, setTab] = useState<"audio" | "transcript" | "visual">("audio");
  const [time, setTime] = useState(35),
    [playing, setPlaying] = useState(false),
    [answerOnly, setAnswerOnly] = useState(false),
    [followPlayback, setFollowPlayback] = useState(true);
  const [media, setMedia] = useState<Record<string, string>>({}),
    [duration, setDuration] = useState(800);
  const [dialog, setDialog] = useState<"complete" | "scale" | "reset" | null>(
      null,
    ),
    [toast, setToast] = useState(""),
    [saved, setSaved] = useState(true),
    [storageError, setStorageError] = useState(false);
  const [noteSearch, setNoteSearch] = useState("");
  const video = useRef<HTMLVideoElement>(null),
    transcript = useRef<HTMLDivElement>(null);
  const sample = interviews.find((i) => i.id === route.id),
    i = sample || interviews[0],
    a = i.answers.find((q) => q.id === selectedQ) || i.answers[0];
  const ready = i.processing === "Ready",
    score = (s: Interview, q: Answer) =>
      s.processing === "Ready" ? q.score : null;
  const review = reviews[reviewKey(i.id, a.id)] || emptyReview;
  const reviewedCount = i.answers.filter(
    (q) => reviews[reviewKey(i.id, q.id)]?.reviewed,
  ).length;
  const followupCount = i.answers.filter(
    (q) => reviews[reviewKey(i.id, q.id)]?.followup,
  ).length;
  const needCount = i.answers.filter(
    (q) =>
      !reviews[reviewKey(i.id, q.id)]?.reviewed &&
      ((score(i, q) ?? -1) >= 3 || score(i, q) === null),
  ).length;
  const sessionDuration = Math.max(...i.answers.map((q) => q.end)) + 35;
  const maxTime = media[i.id] ? duration : sessionDuration;
  const changeRoute = (page: Page, id?: string, question?: string) => {
    setPlaying(false);
    video.current?.pause();
    location.hash =
      page === "review"
        ? `/interviews/${encodeURIComponent(id || i.id)}${question ? "?question=" + question : ""}`
        : page === "summary"
          ? `/interviews/${encodeURIComponent(id || i.id)}/summary`
          : `/${page}`;
  };
  const seek = (t: number) => {
    const target = Math.min(Math.max(0, t), maxTime);
    setTime(target);
    if (video.current) video.current.currentTime = target;
  };
  const selectQuestion = (q: Answer) => {
    setSelectedQ(q.id);
    seek(q.start);
    setAnswerOnly(false);
    if (route.page === "review")
      history.replaceState(
        null,
        "",
        `#/interviews/${encodeURIComponent(i.id)}?question=${q.id}`,
      );
  };
  const openInterview = (s: Interview) => {
    const q =
      s.answers.find(
        (q) =>
          !reviews[reviewKey(s.id, q.id)]?.reviewed && (score(s, q) ?? 0) >= 3,
      ) || s.answers[0];
    setSelectedQ(q.id);
    setTime(q.start);
    setDuration(800);
    setQuestionFilter(false);
    setNoteSearch("");
    changeRoute("review", s.id, q.id);
  };
  useEffect(() => {
    const changed = () => {
      const next = readRoute();
      setRoute(next);
      setPlaying(false);
      if (next.question) setSelectedQ(next.question);
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    if (route.page === "review" && route.question) {
      const s = interviews.find((s) => s.id === route.id);
      const q = s?.answers.find((q) => q.id === route.question);
      if (q) {
        setSelectedQ(q.id);
        setTime(q.start);
      }
    }
  }, [route.id, route.question, route.page]);
  useEffect(() => {
    setSaved(false);
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(
          STORE,
          JSON.stringify({ version: 2, interviews, reviews }),
        );
        setStorageError(false);
        setSaved(true);
      } catch {
        setStorageError(true);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [interviews, reviews]);
  useEffect(() => {
    const flush = () => {
      try {
        localStorage.setItem(
          STORE,
          JSON.stringify({ version: 2, interviews, reviews }),
        );
      } catch {}
    };
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, [interviews, reviews]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (!playing || media[i.id]) return;
    const timer = setInterval(
      () => setTime((t) => Math.min(t + 1, maxTime)),
      1000,
    );
    return () => clearInterval(timer);
  }, [playing, media, i.id, maxTime]);
  useEffect(() => {
    if (time >= maxTime || (answerOnly && time >= a.end)) {
      setPlaying(false);
      video.current?.pause();
      setAnswerOnly(false);
    }
  }, [time, maxTime, answerOnly, a.end]);
  useEffect(() => {
    if (!playing || !followPlayback || answerOnly) return;
    const next = i.answers.find((q) => time >= q.start && time < q.end);
    if (next && next.id !== selectedQ) setSelectedQ(next.id);
  }, [time, playing, followPlayback, answerOnly, i.id, selectedQ]);
  useEffect(() => {
    const pane = transcript.current;
    const section = pane?.querySelector<HTMLElement>(
      `[data-question="${a.id}"]`,
    );
    if (pane && section) pane.scrollTop = section.offsetTop;
  }, [a.id, i.id, route.page]);
  useEffect(() => {
    if (!dialog) return;
    const previous = document.activeElement as HTMLElement;
    const el = document.querySelector<HTMLElement>('[role="dialog"]');
    const list = () =>
      Array.from(
        el?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input,textarea,select",
        ) || [],
      );
    list()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDialog(null);
      if (e.key === "Tab") {
        const items = list();
        const first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [dialog]);
  const updateReview = (patch: Partial<Review>) => {
    setReviews((previous) => ({
      ...previous,
      [reviewKey(i.id, a.id)]: {
        ...(previous[reviewKey(i.id, a.id)] || emptyReview),
        ...patch,
      },
    }));
    if (i.completedAt)
      setInterviews((rows) =>
        rows.map((s) => (s.id === i.id ? { ...s, completedAt: null } : s)),
      );
  };
  const attach = (file: File) => {
    setPlaying(false);
    setDuration(sessionDuration);
    setMedia((v) => {
      if (v[i.id]) URL.revokeObjectURL(v[i.id]);
      return { ...v, [i.id]: URL.createObjectURL(file) };
    });
  };
  const play = (only = false) => {
    setAnswerOnly(only);
    if (only) seek(a.start);
    if (video.current) {
      void video.current
        .play()
        .then(() => setPlaying(true))
        .catch(() => setToast("Unable to play this file. Try an MP4 video."));
    } else setPlaying(true);
  };
  const togglePlay = () => {
    if (playing) {
      setPlaying(false);
      video.current?.pause();
    } else play();
  };
  const exportSummary = () =>
    download(`${i.id}-review.json`, {
      sample_data: true,
      scoring_version: "sample-v1",
      score_definition:
        "Illustrative 0–9 signal strength, not a probability; bands 0–2, 3–5, 6–9.",
      interview: {
        id: i.id,
        candidate: i.candidate,
        role: i.role,
        date: i.date,
        completedAt: i.completedAt,
        quality: i.quality,
        processing: i.processing,
      },
      answers: i.answers.map((q) => ({
        ...q,
        score: score(i, q),
        review: reviews[reviewKey(i.id, q.id)] || emptyReview,
      })),
    });
  const anchor = interviews.reduce(
    (latest, s) => (s.date > latest ? s.date : latest),
    "2026-10-23",
  );
  const cutoff =
    filters.period === "All time"
      ? ""
      : new Date(
          new Date(anchor + "T12:00:00Z").getTime() -
            (filters.period === "Last 7 days" ? 6 : 29) * 86400000,
        )
          .toISOString()
          .slice(0, 10);
  const filtered = interviews.filter(
    (s) =>
      (!cutoff || s.date >= cutoff) &&
      (filters.role === "All roles" || s.role === filters.role) &&
      (filters.interviewer === "All interviewers" ||
        s.interviewer === filters.interviewer),
  );
  const rows = filtered.filter(
    (s) =>
      (filters.status === "All statuses" ||
        statusOf(s, reviews) === filters.status) &&
      (filters.band === "All signals" ||
        s.answers.some((q) => band(score(s, q)) === filters.band)) &&
      `${s.candidate} ${s.id} ${s.role}`
        .toLowerCase()
        .includes(filters.search.toLowerCase()),
  );
  const drill = (kind: "role" | "status" | "band", value: string) => {
    setFilters((f) => ({ ...f, [kind]: value, search: "" }));
    changeRoute("interviews");
  };
  const statusItems = statusNames.map((label, j) => ({
    label,
    value: filtered.filter((s) => statusOf(s, reviews) === label).length,
    color: ["#8b9194", "#b89545", "#bc7661", "#629b16"][j],
  }));
  const weeks = Array.from({ length: 11 }, (_, j) => {
    const end = new Date(anchor + "T12:00:00Z");
    end.setUTCDate(end.getUTCDate() - (10 - j) * 7);
    const start = new Date(end);
    start.setUTCDate(start.getUTCDate() - 6);
    return {
      label: start.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      }),
      count: filtered.filter(
        (s) =>
          s.date >= start.toISOString().slice(0, 10) &&
          s.date <= end.toISOString().slice(0, 10),
      ).length,
    };
  });
  const allAnswers = filtered.flatMap((s) =>
    s.answers.map((q) => ({ ...q, score: score(s, q) })),
  );
  const shownQuestions = i.answers.filter(
    (q) =>
      !questionFilter ||
      (!reviews[reviewKey(i.id, q.id)]?.reviewed &&
        ((score(i, q) ?? -1) >= 3 || score(i, q) === null)),
  );
  const summary = route.page === "summary";
  const qualityLabel =
    i.quality === "Good"
      ? "Recording quality: Good"
      : i.quality === "Limited audio"
        ? "Limited audio"
        : "Transcript unavailable";
  const renderTable = () => (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Candidate</th>
            <th>Role</th>
            <th>Date</th>
            <th>Review status</th>
            <th>Progress</th>
            <th>Analysis</th>
            <th aria-label="Open interview" />
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id}>
              <td>
                <button className="candidate" onClick={() => openInterview(s)}>
                  <span className="avatar">
                    {s.candidate
                      .split(" ")
                      .map((v) => v[0])
                      .join("")}
                  </span>
                  <span>
                    <b>{s.candidate}</b>
                    <small>
                      {s.id} · {s.interviewer}
                    </small>
                  </span>
                </button>
              </td>
              <td>{s.role}</td>
              <td>{s.date}</td>
              <td>
                <Badge
                  color={
                    statusOf(s, reviews) === "Reviewed"
                      ? "teal"
                      : statusOf(s, reviews) === "Follow-up needed"
                        ? "coral"
                        : "amber"
                  }
                >
                  {statusOf(s, reviews)}
                </Badge>
              </td>
              <td>
                <span className="table-progress">
                  {
                    s.answers.filter(
                      (q) => reviews[reviewKey(s.id, q.id)]?.reviewed,
                    ).length
                  }
                  /{s.answers.length}
                </span>
              </td>
              <td>
                <span className={s.processing === "Failed" ? "failed" : ""}>
                  {s.processing}
                </span>
                {s.quality !== "Good" && (
                  <small className="table-quality">{s.quality}</small>
                )}
              </td>
              <td>
                <button
                  className="icon-btn"
                  aria-label={`Open ${s.id}`}
                  onClick={() => openInterview(s)}
                >
                  <ArrowRight size={17} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <div className="empty">No interviews match these filters.</div>
      )}
    </div>
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand brand-v2"
          href="#/interviews"
          aria-label="Techstra interviews"
        >
          <img src={logo} alt="Techstra Solutions" />
        </a>
        <nav>
          <button
            aria-label="Interviews"
            className={`nav-item ${route.page !== "overview" ? "active" : ""}`}
            onClick={() => changeRoute("interviews")}
          >
            <ListVideo size={19} />
            Interviews<span>{interviews.length}</span>
          </button>
          <button
            aria-label="Overview"
            className={`nav-item ${route.page === "overview" ? "active" : ""}`}
            onClick={() => changeRoute("overview")}
          >
            <LayoutDashboard size={19} />
            Overview
          </button>
        </nav>
        <div className="sidebar-bottom">
          <details className="workspace-tools">
            <summary>
              <MoreHorizontal size={18} />
              Workspace tools
            </summary>
            <button onClick={() => setDialog("reset")}>
              <RotateCcw size={14} />
              Reset sample records
            </button>
          </details>
          <div className="profile">
            <span className="avatar">TR</span>
            <div>
              <b>Interview review</b>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="breadcrumb">Techstra</span>
            <ChevronRight size={14} />
            <b>
              {route.page === "overview"
                ? "Overview"
                : route.page === "interviews"
                  ? "Interviews"
                  : i.id}
            </b>
          </div>
          <div className="topbar-right">
            <span className="sample-label">Sample data</span>
            {route.page === "review" && (
              <span className="save-state" role="status">
                {storageError
                  ? "Not saved"
                  : saved
                    ? "All changes saved"
                    : "Saving…"}
              </span>
            )}
          </div>
        </header>
        <main>
          {storageError && (
            <div className="notice warning">
              Browser storage is unavailable. Notes will not persist after
              closing this page.
            </div>
          )}
          {route.id && !sample && (
            <div className="notice warning">
              Interview not found.{" "}
              <button
                className="text-btn"
                onClick={() => changeRoute("interviews")}
              >
                Return to interviews
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              {(route.page === "review" || summary) && (
                <button
                  aria-label="Back to interviews"
                  className="text-btn back-link"
                  onClick={() => changeRoute("interviews")}
                >
                  <ArrowLeft size={14} />
                  Interviews
                </button>
              )}
              <h1>
                {route.page === "overview"
                  ? "Overview"
                  : route.page === "interviews"
                    ? "Interviews"
                    : summary
                      ? "Review summary"
                      : i.candidate}
              </h1>
              {(route.page === "review" || summary) && (
                <div className="interview-details">
                  {i.role}
                  <span>·</span>
                  {i.date}
                  <span>·</span>
                  {fmtTime(sessionDuration)}
                  <span>·</span>
                  {i.interviewer}
                </div>
              )}
            </div>
            {(route.page === "review" || summary) && (
              <div className="heading-actions">
                {summary ? (
                  <>
                    <button
                      className="secondary"
                      onClick={() => changeRoute("review", i.id, a.id)}
                    >
                      <ArrowLeft size={15} />
                      Back to analysis
                    </button>
                    <button className="secondary" onClick={exportSummary}>
                      <ArrowDownToLine size={15} />
                      JSON
                    </button>
                    <button
                      className="primary"
                      onClick={() => {
                        document
                          .querySelectorAll("details.summary-observations")
                          .forEach((el) => el.setAttribute("open", ""));
                        window.print();
                      }}
                    >
                      <Printer size={16} />
                      Print / PDF
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className="secondary"
                      onClick={() => changeRoute("summary", i.id)}
                    >
                      <FileText size={15} />
                      Summary
                    </button>
                    <button
                      className="primary"
                      disabled={!ready || !!i.completedAt}
                      onClick={() => setDialog("complete")}
                    >
                      <CheckCircle2 size={16} />
                      {i.completedAt ? "Review complete" : "Complete review"}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
          {(route.page === "interviews" || route.page === "overview") && (
            <div className="filters">
              <SlidersHorizontal size={16} />
              <select
                aria-label="Date range"
                value={filters.period}
                onChange={(e) =>
                  setFilters({ ...filters, period: e.target.value })
                }
              >
                {["All time", "Last 30 days", "Last 7 days"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
              <select
                aria-label="Role"
                value={filters.role}
                onChange={(e) =>
                  setFilters({ ...filters, role: e.target.value })
                }
              >
                <option>All roles</option>
                {Array.from(new Set(interviews.map((s) => s.role))).map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
              <select
                aria-label="Interviewer"
                value={filters.interviewer}
                onChange={(e) =>
                  setFilters({ ...filters, interviewer: e.target.value })
                }
              >
                <option>All interviewers</option>
                {Array.from(new Set(interviews.map((s) => s.interviewer))).map(
                  (s) => (
                    <option key={s}>{s}</option>
                  ),
                )}
              </select>
              <button
                className="text-btn"
                onClick={() =>
                  setFilters({
                    role: "All roles",
                    interviewer: "All interviewers",
                    period: "All time",
                    status: "All statuses",
                    band: "All signals",
                    search: "",
                  })
                }
              >
                Reset filters
              </button>
              <span className="filter-count">{filtered.length} interviews</span>
            </div>
          )}
          {route.page === "interviews" && (
            <Panel
              title="Interviews"
              action={<span className="panel-count">{rows.length}</span>}
            >
              <div className="directory-tools">
                <div className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Search interviews"
                    value={filters.search}
                    onChange={(e) =>
                      setFilters({ ...filters, search: e.target.value })
                    }
                    placeholder="Search candidate or interview ID"
                  />
                </div>
                <select
                  aria-label="Review status"
                  value={filters.status}
                  onChange={(e) =>
                    setFilters({ ...filters, status: e.target.value })
                  }
                >
                  <option>All statuses</option>
                  {statusNames.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
                <select
                  aria-label="Signal filter"
                  value={filters.band}
                  onChange={(e) =>
                    setFilters({ ...filters, band: e.target.value })
                  }
                >
                  <option>All signals</option>
                  {["Low signal", "Review", "Strong signal", "Unscored"].map(
                    (s) => (
                      <option key={s}>{s}</option>
                    ),
                  )}
                </select>
              </div>
              {renderTable()}
            </Panel>
          )}
          {route.page === "overview" && (
            <>
              <div className="stats-grid">
                <Stat
                  label="Interviews"
                  value={filtered.length}
                  icon={<Users size={19} />}
                  onClick={() => changeRoute("interviews")}
                />
                <Stat
                  label="Awaiting review"
                  value={statusItems[0].value}
                  icon={<Clock3 size={19} />}
                  onClick={() => drill("status", "Awaiting review")}
                />
                <Stat
                  label="Follow-up needed"
                  value={statusItems[2].value}
                  icon={<FileText size={19} />}
                  onClick={() => drill("status", "Follow-up needed")}
                />
                <Stat
                  label="Completed reviews"
                  value={statusItems[3].value}
                  icon={<CheckCircle2 size={19} />}
                  onClick={() => drill("status", "Reviewed")}
                />
              </div>
              <div className="overview-grid">
                <Panel
                  title="Interview activity"
                  action={<span className="chart-unit">Interviews / week</span>}
                >
                  <div className="activity-chart">
                    <div className="y-axis">
                      {[4, 3, 2, 1, 0].map((n) => (
                        <span key={n}>{n}</span>
                      ))}
                    </div>
                    <div className="activity-columns">
                      {weeks.map((w) => (
                        <div className="activity-col" key={w.label}>
                          <div className="column-space">
                            <span
                              style={{
                                height: `${(w.count / Math.max(4, ...weeks.map((v) => v.count))) * 100}%`,
                              }}
                            >
                              <b>{w.count}</b>
                            </span>
                          </div>
                          <small>{w.label}</small>
                        </div>
                      ))}
                    </div>
                  </div>
                </Panel>
                <Panel
                  title="Review workload"
                  action={<span className="chart-unit">Interviews</span>}
                >
                  <Bars
                    items={statusItems}
                    onSelect={(v) => drill("status", v)}
                  />
                </Panel>
              </div>
              <div className="analytics-grid">
                <Panel
                  title="Signal distribution"
                  action={<span className="chart-unit">Answers</span>}
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
                      color: ["#78a83b", "#bc943d", "#b76f5c", "#a1a5a8"][j],
                    }))}
                    onSelect={(v) => drill("band", v)}
                  />
                </Panel>
                <Panel
                  title="Interviews by role"
                  action={<span className="chart-unit">Interviews</span>}
                >
                  <Bars
                    items={Array.from(
                      new Set(interviews.map((s) => s.role)),
                    ).map((label) => ({
                      label,
                      value: filtered.filter((s) => s.role === label).length,
                    }))}
                    onSelect={(v) => drill("role", v)}
                  />
                </Panel>
                <Panel
                  title="Recording quality"
                  action={<span className="chart-unit">Interviews</span>}
                >
                  <Bars
                    items={["Good", "Limited audio", "Missing transcript"].map(
                      (label) => ({
                        label,
                        value: filtered.filter((s) => s.quality === label)
                          .length,
                      }),
                    )}
                  />
                </Panel>
                <Panel
                  title="Reviewer feedback"
                  action={<span className="chart-unit">Answers</span>}
                >
                  <Bars
                    items={feedbackNames.map((label) => ({
                      label,
                      value: filtered
                        .flatMap((s) =>
                          s.answers.map((q) => reviews[reviewKey(s.id, q.id)]),
                        )
                        .filter((r) => r?.feedback === label).length,
                    }))}
                  />
                </Panel>
              </div>
            </>
          )}
          {route.page === "review" && sample && (
            <>
              <div className="session-meta v2-meta">
                <Badge color={i.completedAt ? "teal" : "neutral"}>
                  {i.completedAt ? "Review complete" : statusOf(i, reviews)}
                </Badge>
                <span>
                  <CheckCircle2 size={14} />
                  {reviewedCount}/{i.answers.length} reviewed
                </span>
                <span>{needCount} answers need review</span>
                <span>{followupCount} follow-ups</span>
                <span
                  title={
                    i.consent
                      ? "Monitoring consent recorded"
                      : "Monitoring consent not recorded"
                  }
                >
                  <ShieldCheck size={14} />
                  {i.consent ? "Consent recorded" : "Consent missing"}
                </span>
              </div>
              {!ready && (
                <div className="notice warning">
                  <AlertTriangle size={16} />
                  {i.processing === "Failed"
                    ? "Analysis failed. Results are unavailable."
                    : "Analysis is processing. Results are unavailable."}
                </div>
              )}
              <div className="review-layout">
                <aside className="question-panel">
                  <div className="question-heading">
                    <h3>Questions</h3>
                    <label className="compact-check">
                      <input
                        type="checkbox"
                        checked={questionFilter}
                        onChange={(e) => setQuestionFilter(e.target.checked)}
                      />
                      Needs review only
                    </label>
                  </div>
                  {shownQuestions.map((q) => (
                    <button
                      className={`question-item ${q.id === a.id ? "selected" : ""}`}
                      key={q.id}
                      onClick={() => selectQuestion(q)}
                    >
                      <div>
                        <span>{q.id}</span>
                        {reviews[reviewKey(i.id, q.id)]?.reviewed && (
                          <CheckCircle2 size={14} />
                        )}
                      </div>
                      <p>{q.question}</p>
                      <div>
                        <Badge color={tone(score(i, q))}>
                          {score(i, q) === null
                            ? "Unscored"
                            : `${score(i, q)}/9`}
                        </Badge>
                        <small>{fmtTime(q.start)}</small>
                      </div>
                    </button>
                  ))}
                  {!shownQuestions.length && (
                    <div className="empty small">No answers need review.</div>
                  )}
                </aside>
                <div className="review-center">
                  <Panel
                    title="Signals by question"
                    action={
                      <button
                        className="icon-btn"
                        aria-label="Signal scale details"
                        onClick={() => setDialog("scale")}
                      >
                        <Info size={16} />
                      </button>
                    }
                  >
                    <div className="question-chart">
                      {i.answers.map((q) => (
                        <button
                          key={q.id}
                          aria-label={`Select ${q.id}`}
                          className={q.id === a.id ? "selected" : ""}
                          onClick={() => selectQuestion(q)}
                        >
                          <strong>
                            {score(i, q) === null ? "N/A" : score(i, q)}
                          </strong>
                          <div>
                            <span
                              className={tone(score(i, q))}
                              style={{
                                height: `${score(i, q) === null ? 0 : (Number(score(i, q)) / 9) * 100}%`,
                              }}
                            />
                          </div>
                          <small>{q.id}</small>
                        </button>
                      ))}
                    </div>
                  </Panel>
                  <Panel
                    title={`${a.id} · ${a.question}`}
                    action={
                      <div className="question-arrows">
                        <button
                          className="icon-btn"
                          disabled={a.id === i.answers[0].id}
                          aria-label="Previous question"
                          onClick={() =>
                            selectQuestion(i.answers[i.answers.indexOf(a) - 1])
                          }
                        >
                          <ChevronLeft size={17} />
                        </button>
                        <button
                          className="icon-btn"
                          disabled={a.id === i.answers.at(-1)?.id}
                          aria-label="Next question"
                          onClick={() =>
                            selectQuestion(i.answers[i.answers.indexOf(a) + 1])
                          }
                        >
                          <ChevronRight size={17} />
                        </button>
                      </div>
                    }
                  >
                    <div className="player">
                      {media[i.id] ? (
                        <video
                          key={media[i.id]}
                          ref={video}
                          src={media[i.id]}
                          controls
                          onLoadedMetadata={(e) => {
                            setDuration(e.currentTarget.duration);
                            e.currentTarget.currentTime = Math.min(
                              a.start,
                              e.currentTarget.duration,
                            );
                          }}
                          onTimeUpdate={(e) =>
                            setTime(e.currentTarget.currentTime)
                          }
                          onPlay={() => setPlaying(true)}
                          onPause={() => setPlaying(false)}
                        />
                      ) : (
                        <div className="player-placeholder">
                          <Film size={30} />
                          <h4>Recording unavailable</h4>
                          <label className="player-attach">
                            <UploadIcon />
                            Attach local recording
                            <input
                              type="file"
                              accept="video/*"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f) attach(f);
                              }}
                            />
                          </label>
                        </div>
                      )}
                      <div className="player-controls">
                        <button
                          aria-label={playing ? "Pause" : "Play"}
                          onClick={togglePlay}
                        >
                          {playing ? <Pause size={16} /> : <Play size={16} />}
                        </button>
                        <span>{fmtTime(time)}</span>
                        <input
                          aria-label="Recording position"
                          type="range"
                          min="0"
                          max={maxTime}
                          value={Math.min(time, maxTime)}
                          onChange={(e) => seek(Number(e.target.value))}
                        />
                        <span>{fmtTime(maxTime)}</span>
                      </div>
                    </div>
                    <div className="play-actions">
                      <button
                        className="secondary"
                        onClick={() => play(true)}
                        disabled={a.start >= maxTime}
                      >
                        <Play size={13} />
                        Play answer
                      </button>
                      <span>
                        {fmtTime(a.start)}–{fmtTime(a.end)}
                      </span>
                      {media[i.id] && a.start >= maxTime && (
                        <small>Answer is beyond recording duration</small>
                      )}
                      <button
                        className="text-btn"
                        onClick={() => {
                          const entered = prompt("Bookmark label (optional)");
                          if (entered === null) return;
                          const value =
                            entered.trim() || `Bookmark at ${fmtTime(time)}`;
                          updateReview({
                            bookmarks: [
                              ...(review.bookmarks || []),
                              { id: crypto.randomUUID(), time, label: value },
                            ],
                          });
                          setToast("Bookmark saved.");
                        }}
                      >
                        <Bookmark size={14} />
                        Bookmark
                      </button>
                    </div>
                    <div
                      className="recording-timeline"
                      aria-label="Answer windows"
                    >
                      {i.answers.map((q) => (
                        <button
                          key={q.id}
                          title={`${q.id}: ${fmtTime(q.start)}–${fmtTime(q.end)}`}
                          aria-label={`Jump to ${q.id}`}
                          className={q.id === a.id ? "selected" : ""}
                          style={{
                            left: `${(q.start / sessionDuration) * 100}%`,
                            width: `${((q.end - q.start) / sessionDuration) * 100}%`,
                          }}
                          onClick={() => selectQuestion(q)}
                        >
                          {q.id}
                        </button>
                      ))}
                      {i.answers.flatMap((q) =>
                        (reviews[reviewKey(i.id, q.id)]?.bookmarks || []).map(
                          (b) => (
                            <button
                              className="bookmark-marker"
                              key={b.id}
                              title={b.label}
                              aria-label={`Bookmark ${b.label}`}
                              style={{
                                left: `${(b.time / sessionDuration) * 100}%`,
                              }}
                              onClick={() => {
                                setSelectedQ(q.id);
                                seek(b.time);
                              }}
                            >
                              <Bookmark size={10} />
                            </button>
                          ),
                        ),
                      )}
                      <span
                        style={{
                          left: `${Math.min((time / sessionDuration) * 100, 100)}%`,
                        }}
                      />
                    </div>
                    <small className="timeline-note">Answer windows</small>
                  </Panel>
                  <Panel
                    title="Transcript"
                    action={
                      <label className="compact-check">
                        <input
                          type="checkbox"
                          checked={followPlayback}
                          onChange={(e) => setFollowPlayback(e.target.checked)}
                        />
                        Follow playback
                      </label>
                    }
                  >
                    <div className="transcript-search">
                      <Search size={14} />
                      <input
                        aria-label="Search transcript"
                        placeholder="Search transcript"
                        value={noteSearch}
                        onChange={(e) => setNoteSearch(e.target.value)}
                      />
                    </div>
                    <div
                      className="transcript transcript-scroll"
                      ref={transcript}
                    >
                      {ready && i.answers.some((q) => q.transcript.length) ? (
                        i.answers.map((q) => (
                          <section
                            data-question={q.id}
                            key={q.id}
                            className={
                              q.id === a.id ? "selected-transcript" : ""
                            }
                          >
                            <div className="transcript-question">
                              <b>{q.id}</b>
                              {q.question}
                            </div>
                            {q.transcript
                              .filter((t) =>
                                t.text
                                  .toLowerCase()
                                  .includes(noteSearch.toLowerCase()),
                              )
                              .map((t, j) => (
                                <button
                                  key={t.start}
                                  className={
                                    time >= t.start &&
                                    time < (q.transcript[j + 1]?.start || q.end)
                                      ? "current"
                                      : ""
                                  }
                                  onClick={() => {
                                    setSelectedQ(q.id);
                                    seek(t.start);
                                  }}
                                >
                                  <span>{fmtTime(t.start)}</span>
                                  <p>{t.text}</p>
                                </button>
                              ))}
                          </section>
                        ))
                      ) : (
                        <div className="empty">
                          {ready
                            ? "Transcript unavailable."
                            : "Transcript unavailable until analysis completes."}
                        </div>
                      )}
                    </div>
                  </Panel>
                  <Panel title="Candidate baseline">
                    <Compare
                      title="Speech rate"
                      value={ready ? a.speechRate : null}
                      baseline={ready ? a.baselineRate : null}
                      unit="words/min"
                    />
                    <Compare
                      title="Response latency"
                      value={ready ? a.latency : null}
                      baseline={ready ? a.baselineLatency : null}
                      unit="seconds"
                    />
                  </Panel>
                </div>
                <aside className="review-right">
                  <Panel
                    title="Review signal"
                    action={
                      <button
                        className="icon-btn"
                        aria-label="About score"
                        onClick={() => setDialog("scale")}
                      >
                        <Info size={15} />
                      </button>
                    }
                  >
                    <div className={`score-display ${tone(score(i, a))}`}>
                      <strong>
                        {score(i, a) === null ? "N/A" : score(i, a)}
                      </strong>
                      <span>/9</span>
                      <Badge color={tone(score(i, a))}>
                        {band(score(i, a))}
                      </Badge>
                    </div>
                    <div className="score-scale">
                      {Array.from({ length: 11 }, (_, j) => (
                        <span
                          key={j}
                          className={`${tone(j)} ${score(i, a) === j ? "marker" : ""}`}
                        />
                      ))}
                    </div>
                    <div className="score-spacer" />
                  </Panel>
                  <Panel title="Observations">
                    <div className="tabs" role="tablist" aria-label="Modality">
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
                          key={t.id}
                          role="tab"
                          aria-selected={tab === t.id}
                          className={tab === t.id ? "active" : ""}
                          onClick={() => setTab(t.id as typeof tab)}
                        >
                          {t.icon}
                          {t.label}
                        </button>
                      ))}
                    </div>
                    {tab === "visual" ? (
                      <div className="empty small">
                        Video analysis unavailable.
                      </div>
                    ) : !ready ? (
                      <div className="empty small">Analysis unavailable.</div>
                    ) : (
                      a.signals
                        .filter((s) => s.modality === tab)
                        .map((s) => (
                          <div className="observation" key={s.signal_name}>
                            <div>
                              <h4>{s.signal_name.replaceAll("_", " ")}</h4>
                              <b>{s.value === null ? "N/A" : s.value}</b>
                            </div>
                            <p>
                              {s.value === null
                                ? "Not measurable with available data."
                                : s.signal_name === "long_pause_count"
                                  ? "Pauses of at least one second."
                                  : s.signal_name === "speech_rate"
                                    ? "Words per minute across this answer."
                                    : "Words in the supplied transcript."}
                            </p>
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
                    )}
                  </Panel>
                  <div
                    className={`quality-box ${i.quality === "Good" ? "" : "limited"}`}
                  >
                    <AlertTriangle size={16} />
                    <div>
                      <b>{qualityLabel}</b>
                      {i.quality !== "Good" && (
                        <p>
                          {i.quality === "Limited audio"
                            ? "Audio measurements are limited."
                            : "Text observations are unavailable."}
                        </p>
                      )}
                    </div>
                  </div>
                  <Panel
                    title="Your review"
                    action={
                      <span className="save-state">
                        {saved ? "Saved" : "Saving…"}
                      </span>
                    }
                  >
                    <label className="field">
                      Feedback
                      <select
                        aria-label="Feedback"
                        value={review.feedback}
                        onChange={(e) =>
                          updateReview({
                            feedback: e.target.value as Feedback | "",
                          })
                        }
                      >
                        <option value="">Select feedback</option>
                        {feedbackNames.map((f) => (
                          <option key={f}>{f}</option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      Notes
                      <textarea
                        rows={4}
                        placeholder="Add context or a follow-up question"
                        value={review.notes}
                        onChange={(e) =>
                          updateReview({ notes: e.target.value })
                        }
                      />
                    </label>
                    <label className="check-label">
                      <input
                        type="checkbox"
                        checked={review.followup}
                        onChange={(e) =>
                          updateReview({ followup: e.target.checked })
                        }
                      />
                      Follow-up needed
                    </label>
                    <label className="check-label">
                      <input
                        type="checkbox"
                        checked={review.reviewed}
                        onChange={(e) =>
                          updateReview({ reviewed: e.target.checked })
                        }
                      />
                      Answer reviewed
                    </label>
                    <div className="bookmark-list">
                      {(review.bookmarks || []).map((b) => (
                        <div key={b.id}>
                          <button
                            className="text-btn"
                            onClick={() => seek(b.time)}
                          >
                            <Bookmark size={12} />
                            {fmtTime(b.time)} · {b.label}
                          </button>
                          <button
                            className="icon-btn"
                            aria-label={`Remove ${b.label}`}
                            onClick={() =>
                              updateReview({
                                bookmarks: review.bookmarks?.filter(
                                  (v) => v.id !== b.id,
                                ),
                              })
                            }
                          >
                            <X size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </Panel>
                </aside>
              </div>
            </>
          )}
          {summary && sample && (
            <>
              <div className="summary-grid">
                <Stat
                  label="Answers reviewed"
                  value={`${reviewedCount}/${i.answers.length}`}
                  icon={<CheckCircle2 size={19} />}
                />
                <Stat
                  label="Follow-ups"
                  value={followupCount}
                  icon={<FileText size={19} />}
                />
                <Stat
                  label="Review status"
                  value={i.completedAt ? "Complete" : "In progress"}
                  icon={<ShieldCheck size={19} />}
                />
              </div>
              <Panel title="Review record">
                <div className="summary-answers">
                  {i.answers.map((q) => {
                    const r = reviews[reviewKey(i.id, q.id)] || emptyReview;
                    return (
                      <article key={q.id}>
                        <div>
                          <button
                            className="text-btn"
                            onClick={() => changeRoute("review", i.id, q.id)}
                          >
                            {q.id} · {fmtTime(q.start)} <ArrowRight size={13} />
                          </button>
                          <Badge color={tone(score(i, q))}>
                            {score(i, q) === null
                              ? "Unscored"
                              : `${score(i, q)}/9 · ${band(score(i, q))}`}
                          </Badge>
                        </div>
                        <h4>{q.question}</h4>
                        <p>
                          {r.reviewed ? "Reviewed" : "Not reviewed"} ·{" "}
                          {r.feedback || "No feedback"}
                          {r.followup ? " · Follow-up needed" : ""}
                        </p>
                        <p className="summary-note">{r.notes || "No notes"}</p>
                        {(r.bookmarks || []).map((b) => (
                          <p key={b.id}>
                            Bookmark {fmtTime(b.time)}: {b.label}
                          </p>
                        ))}
                        <details className="summary-observations">
                          <summary>Observations</summary>
                          {q.signals.map((s) => (
                            <p key={s.signal_name}>
                              {s.signal_name.replaceAll("_", " ")}:{" "}
                              {ready
                                ? (s.value ?? "Unavailable")
                                : "Unavailable"}{" "}
                              · {fmtTime(q.start)}–{fmtTime(q.end)}
                            </p>
                          ))}
                        </details>
                      </article>
                    );
                  })}
                </div>
              </Panel>
            </>
          )}
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={16} />
          {toast}
        </div>
      )}
      {dialog && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="dialog-title"
          >
            <button
              className="modal-close icon-btn"
              aria-label="Close dialog"
              onClick={() => setDialog(null)}
            >
              <X size={18} />
            </button>
            <h2 id="dialog-title">
              {dialog === "complete"
                ? "Complete this review?"
                : dialog === "scale"
                  ? "Review signal scale"
                  : "Reset sample records?"}
            </h2>
            {dialog === "scale" ? (
              <>
                <div className="help-bands">
                  <Badge color="teal">0–2 Low signal</Badge>
                  <Badge color="amber">3–5 Review</Badge>
                  <Badge color="coral">6–9 Strong signal</Badge>
                </div>
                <p>
                  The score describes review signal strength, not the
                  probability of AI use. Current scores and thresholds are
                  illustrative. Supporting observations require human
                  interpretation.
                </p>
                <p>
                  Recording quality limits measurement availability. It is
                  separate from assistance signals. A missing score means
                  insufficient data.
                </p>
              </>
            ) : dialog === "reset" ? (
              <>
                <p>
                  This clears locally saved notes, bookmarks, and review
                  progress, then restores the sample interviews.
                </p>
                <button
                  className="primary"
                  onClick={() => {
                    Object.values(media).forEach((u) => URL.revokeObjectURL(u));
                    setMedia({});
                    const records = createDemoInterviews();
                    setInterviews(records);
                    setReviews(createDemoReviews(records));
                    setDialog(null);
                    changeRoute("interviews");
                    setToast("Sample records restored.");
                  }}
                >
                  Reset records
                </button>
              </>
            ) : (
              <>
                <p>
                  {reviewedCount} of {i.answers.length} answers reviewed.{" "}
                  {followupCount} follow-ups.
                  {reviewedCount < i.answers.length
                    ? " Unreviewed answers will remain visible in the summary."
                    : ""}
                </p>
                <p>
                  This records completion of your analysis. It does not make a
                  hiring decision.
                </p>
                <div className="heading-actions">
                  <button className="secondary" onClick={() => setDialog(null)}>
                    Continue reviewing
                  </button>
                  <button
                    className="primary"
                    onClick={() => {
                      setInterviews((v) =>
                        v.map((s) =>
                          s.id === i.id
                            ? { ...s, completedAt: new Date().toISOString() }
                            : s,
                        ),
                      );
                      setDialog(null);
                      changeRoute("summary", i.id);
                      setToast("Review completed.");
                    }}
                  >
                    Complete review
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function UploadIcon() {
  return <ArrowDownToLine size={14} style={{ transform: "rotate(180deg)" }} />;
}
