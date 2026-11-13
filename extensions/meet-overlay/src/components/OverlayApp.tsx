import { useCallback, useEffect, useId, useRef, useState } from "react";
import { DEMO_SESSION } from "../data/demoScenarios";
import { useDemoSimulation } from "../demo/useDemoSimulation";
import { clampPosition, defaultLauncherPosition } from "../content/clamp";
import { useDraggable } from "../content/useDraggable";
import { useLiveCapture } from "../live/useLiveCapture";
import { useOfflineAnalysis } from "../offline/useOfflineAnalysis";
import { OfflineAnalysisPanel } from "../panel/OfflineAnalysisPanel";
import { CurrentQuestion } from "./CurrentQuestion";
import { DetectionAnalysis } from "./DetectionAnalysis";
import { FollowUpQuestions } from "./FollowUpQuestions";
import { FullAnalysisLink } from "./FullAnalysisLink";
import { CompactIcon, CloseIcon, ExpandIcon, MinimizeIcon } from "./icons";
import { LiveCaptureControls } from "./LiveCaptureControls";
import { LiveResultsPanel } from "./LiveResultsPanel";
import { LiveTranscript } from "./LiveTranscript";
import { ModeSwitcher, type OverlayMode } from "./ModeSwitcher";
import { OfflineAnalysisControls } from "./OfflineAnalysisControls";
import { SessionControls } from "./SessionControls";
import { CaptureStatus } from "../types/capture";

const LAUNCHER = 56;
const COMPACT_WIDTH = 360;
const WIDE_WIDTH = 480;
const COMPACT_HEIGHT = 560;
const WIDE_HEIGHT = 640;

type ChromeMode = "launcher" | "panel";
type PanelSize = "compact" | "wide";

export type OverlayAppProps = {
  onClose: () => void;
  /** When true, open the panel immediately (local harness). Default: launcher only. */
  startOpen?: boolean;
};

export function OverlayApp({ onClose, startOpen = false }: OverlayAppProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement | null>(null);
  const [chromeMode, setChromeMode] = useState<ChromeMode>(startOpen ? "panel" : "launcher");
  const [panelSize, setPanelSize] = useState<PanelSize>("compact");
  const [mode, setMode] = useState<OverlayMode>("demo");
  const demo = useDemoSimulation();
  const offline = useOfflineAnalysis();
  const live = useLiveCapture();

  const panelWidth =
    panelSize === "compact"
      ? Math.min(COMPACT_WIDTH, window.innerWidth - 24)
      : Math.min(WIDE_WIDTH, window.innerWidth - 24);
  const panelHeight = panelSize === "compact" ? COMPACT_HEIGHT : WIDE_HEIGHT;

  const size =
    chromeMode === "launcher"
      ? { width: LAUNCHER, height: LAUNCHER }
      : { width: panelWidth, height: Math.min(panelHeight, window.innerHeight - 24) };

  const { position, setPosition, didDrag, dragHandlers } = useDraggable(
    startOpen
      ? clampPosition(
          Math.max(12, window.innerWidth - Math.min(COMPACT_WIDTH, window.innerWidth - 24) - 24),
          Math.max(12, window.innerHeight - Math.min(COMPACT_HEIGHT, window.innerHeight - 24) - 24),
          Math.min(COMPACT_WIDTH, window.innerWidth - 24),
          Math.min(COMPACT_HEIGHT, window.innerHeight - 24),
        )
      : defaultLauncherPosition(LAUNCHER),
    size,
  );

  const minimize = useCallback(() => {
    setChromeMode("launcher");
    setPosition((prev) => clampPosition(prev.x, prev.y, LAUNCHER, LAUNCHER));
  }, [setPosition]);

  const openPanel = useCallback(() => {
    setChromeMode("panel");
    setPosition((prev) =>
      clampPosition(
        prev.x,
        prev.y,
        Math.min(COMPACT_WIDTH, window.innerWidth - 24),
        Math.min(COMPACT_HEIGHT, window.innerHeight - 24),
      ),
    );
  }, [setPosition]);

  const setWide = useCallback(() => {
    setPanelSize("wide");
    setPosition((prev) =>
      clampPosition(
        prev.x,
        prev.y,
        Math.min(WIDE_WIDTH, window.innerWidth - 24),
        Math.min(WIDE_HEIGHT, window.innerHeight - 24),
      ),
    );
  }, [setPosition]);

  const setCompact = useCallback(() => {
    setPanelSize("compact");
    setPosition((prev) =>
      clampPosition(
        prev.x,
        prev.y,
        Math.min(COMPACT_WIDTH, window.innerWidth - 24),
        Math.min(COMPACT_HEIGHT, window.innerHeight - 24),
      ),
    );
  }, [setPosition]);

  const stopLiveIfNeeded = useCallback(async () => {
    if (
      live.snapshot.status === CaptureStatus.CAPTURING ||
      live.snapshot.status === CaptureStatus.TRANSMITTING ||
      live.snapshot.status === CaptureStatus.TRANSCRIBING ||
      live.snapshot.status === CaptureStatus.STARTING
    ) {
      await live.stop();
    }
  }, [live]);

  const onModeChange = useCallback(
    (next: OverlayMode) => {
      void (async () => {
        if (mode === "live" && next !== "live") {
          await stopLiveIfNeeded();
        }
        setMode(next);
        if (next === "demo") {
          offline.reset();
          live.resetLocal();
        } else if (next === "offline") {
          demo.reset();
          live.resetLocal();
        } else {
          demo.reset();
          offline.reset();
        }
      })();
    },
    [demo, live, mode, offline, stopLiveIfNeeded],
  );

  const handleClose = useCallback(() => {
    void (async () => {
      await stopLiveIfNeeded();
      onClose();
    })();
  }, [onClose, stopLiveIfNeeded]);

  useEffect(() => {
    if (chromeMode !== "panel") return;
    const node = panelRef.current?.querySelector<HTMLElement>("[data-ii-autofocus]");
    node?.focus();
  }, [chromeMode]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && chromeMode === "panel") {
        event.stopPropagation();
        minimize();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [minimize, chromeMode]);

  if (chromeMode === "launcher") {
    return (
      <div className="ii-root">
        <button
          type="button"
          className="ii-launcher"
          style={{ left: position.x, top: position.y }}
          aria-label="Open Interview Integrity panel"
          title="Interview Integrity"
          {...dragHandlers}
          onClick={() => {
            if (didDrag()) return;
            openPanel();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              openPanel();
            }
          }}
        >
          <span className="ii-launcher-mark" aria-hidden="true">
            II
          </span>
        </button>
      </div>
    );
  }

  const wide = panelSize === "wide";
  const headerSubtitle =
    mode === "demo"
      ? DEMO_SESSION.meetContext
      : mode === "offline"
        ? "Offline processed recording — not live Meet capture."
        : "Live Meet tab audio — capture foundation only.";
  const modeBadge =
    mode === "demo" ? DEMO_SESSION.modeLabel : mode === "offline" ? "OFFLINE ANALYSIS" : "LIVE AUDIO";

  return (
    <div className="ii-root">
      <section
        ref={panelRef}
        className={`ii-panel ${wide ? "ii-panel-wide" : ""}`}
        style={{ left: position.x, top: position.y, width: panelWidth }}
        role="dialog"
        aria-modal="false"
        aria-labelledby={titleId}
      >
        <header className="ii-header" {...dragHandlers}>
          <div className="ii-brand">
            <div className="ii-brand-badge" aria-hidden="true">
              II
            </div>
            <div className="ii-brand-text">
              <strong id={titleId}>Interview Integrity</strong>
              <span>{headerSubtitle}</span>
            </div>
          </div>
          <span
            className="ii-demo-badge"
            title={
              mode === "demo"
                ? "Synthetic demonstration"
                : mode === "offline"
                  ? "Offline analysis mode"
                  : "Live tab audio capture foundation"
            }
          >
            {modeBadge}
          </span>
          <div className="ii-header-actions">
            {wide ? (
              <button
                type="button"
                className="ii-icon-btn"
                aria-label="Restore compact view"
                title="Restore compact view"
                onClick={setCompact}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <CompactIcon />
              </button>
            ) : (
              <button
                type="button"
                className="ii-icon-btn"
                aria-label="Expand view"
                title="Expand view"
                onClick={setWide}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <ExpandIcon />
              </button>
            )}
            <button
              type="button"
              className="ii-icon-btn"
              aria-label="Minimize Interview Integrity panel"
              title="Minimize"
              data-ii-autofocus
              onClick={minimize}
              onPointerDown={(event) => event.stopPropagation()}
            >
              <MinimizeIcon />
            </button>
            <button
              type="button"
              className="ii-icon-btn"
              aria-label="Close Interview Integrity overlay"
              title="Close"
              onClick={handleClose}
              onPointerDown={(event) => event.stopPropagation()}
            >
              <CloseIcon />
            </button>
          </div>
        </header>

        <div className="ii-body">
          <ModeSwitcher mode={mode} onChange={onModeChange} />

          {mode === "demo" ? (
            <>
              <SessionControls
                status={demo.state.status}
                scenarioTitle={demo.scenario.title}
                scenarioKind={demo.scenario.kind}
                onStart={demo.start}
                onPause={demo.pause}
                onResume={demo.resume}
                onReset={demo.reset}
                onNext={demo.nextScenario}
              />

              <CurrentQuestion
                question={demo.scenario.question}
                visible={demo.state.questionVisible}
                candidateResponding={demo.state.candidateResponding}
              />

              <LiveTranscript segments={demo.state.revealedSegments} expanded={wide} />

              <DetectionAnalysis
                detection={demo.state.detection}
                dataSource="demo"
                qualityWarnings={
                  demo.state.detection.kind === "available" ||
                  demo.state.detection.kind === "processing"
                    ? demo.scenario.qualityWarnings
                    : []
                }
              />

              <FollowUpQuestions
                followup={demo.scenario.followup}
                visible={demo.state.followupVisible}
              />

              <FullAnalysisLink />
            </>
          ) : mode === "offline" ? (
            <>
              <OfflineAnalysisControls
                form={offline.form}
                connection={offline.connection}
                healthNote={offline.healthNote}
                errorMessage={offline.errorMessage}
                onChange={offline.setForm}
                onCheckHealth={() => void offline.checkHealth()}
                onAnalyze={() => void offline.runAnalysis()}
                onReset={offline.reset}
              />
              {offline.panelModel ? (
                <OfflineAnalysisPanel model={offline.panelModel} expanded={wide} />
              ) : (
                <p className="ii-empty">
                  Run an explicit offline analysis request to display results from the
                  localhost API. This mode never captures Google Meet audio or video.
                </p>
              )}
            </>
          ) : (
            <>
              <LiveCaptureControls
                consentConfirmed={live.consentConfirmed}
                snapshot={live.snapshot}
                errorMessage={live.errorMessage}
                busy={live.busy}
                onConsentChange={live.setConsentConfirmed}
                onStart={() => void live.start()}
                onStop={() => void live.stop()}
              />
              <LiveResultsPanel snapshot={live.snapshot} expanded={wide} />
            </>
          )}
        </div>
      </section>
    </div>
  );
}
