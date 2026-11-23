import type {
  DemoScenario,
  DemoTimelineEvent,
  DetectionResultState,
  TranscriptSegment,
} from "../types/session";

export type DemoPlayStatus = "idle" | "running" | "paused" | "completed";

export type DemoViewState = {
  status: DemoPlayStatus;
  scenarioIndex: number;
  elapsedMs: number;
  questionVisible: boolean;
  candidateResponding: boolean;
  revealedSegments: TranscriptSegment[];
  detection: DetectionResultState;
  followupVisible: boolean;
  appliedEventKeys: string[];
};

export function createInitialDemoState(scenarioIndex = 0): DemoViewState {
  return {
    status: "idle",
    scenarioIndex,
    elapsedMs: 0,
    questionVisible: false,
    candidateResponding: false,
    revealedSegments: [],
    detection: { kind: "no_result" },
    followupVisible: false,
    appliedEventKeys: [],
  };
}

function eventKey(event: DemoTimelineEvent, index: number): string {
  return `${event.atMs}:${event.type}:${index}`;
}

function applyEvent(
  state: DemoViewState,
  scenario: DemoScenario,
  event: DemoTimelineEvent,
): DemoViewState {
  switch (event.type) {
    case "show_question":
      return { ...state, questionVisible: true };
    case "candidate_responding":
      return { ...state, candidateResponding: true };
    case "transcript_segment": {
      const segment = scenario.transcript[event.segmentIndex];
      if (!segment) return state;
      if (state.revealedSegments.some((s) => s.id === segment.id)) return state;
      return {
        ...state,
        revealedSegments: [...state.revealedSegments, segment],
      };
    }
    case "analysis_processing":
      return {
        ...state,
        candidateResponding: false,
        detection: {
          kind: "processing",
          message: "Demo analysis running on synthetic transcript…",
        },
      };
    case "analysis_result":
      return { ...state, detection: scenario.detectionWhenReady };
    case "show_followup":
      return { ...state, followupVisible: true };
    case "scenario_complete":
      return { ...state, status: "completed", candidateResponding: false };
    default:
      return state;
  }
}

/** Apply all timeline events due at or before elapsedMs (idempotent via appliedEventKeys). */
export function syncTimeline(
  state: DemoViewState,
  scenario: DemoScenario,
): DemoViewState {
  let next = state;
  scenario.timeline.forEach((event, index) => {
    if (event.atMs > next.elapsedMs) return;
    const key = eventKey(event, index);
    if (next.appliedEventKeys.includes(key)) return;
    next = applyEvent(next, scenario, event);
    next = { ...next, appliedEventKeys: [...next.appliedEventKeys, key] };
  });
  return next;
}

export function startDemo(state: DemoViewState): DemoViewState {
  if (state.status === "running") return state;
  if (state.status === "paused") {
    return { ...state, status: "running" };
  }
  // Fresh start / restart current scenario from zero.
  const reset = createInitialDemoState(state.scenarioIndex);
  return { ...reset, status: "running" };
}

export function pauseDemo(state: DemoViewState): DemoViewState {
  if (state.status !== "running") return state;
  return { ...state, status: "paused" };
}

export function resumeDemo(state: DemoViewState): DemoViewState {
  if (state.status !== "paused") return state;
  return { ...state, status: "running" };
}

export function resetDemo(state: DemoViewState): DemoViewState {
  return createInitialDemoState(state.scenarioIndex);
}

export function advanceDemoClock(
  state: DemoViewState,
  scenario: DemoScenario,
  deltaMs: number,
): DemoViewState {
  if (state.status !== "running" || deltaMs <= 0) return state;
  const elapsedMs = state.elapsedMs + deltaMs;
  return syncTimeline({ ...state, elapsedMs }, scenario);
}

export function goToNextScenario(
  state: DemoViewState,
  scenarioCount: number,
): DemoViewState {
  const scenarioIndex = (state.scenarioIndex + 1) % Math.max(scenarioCount, 1);
  return createInitialDemoState(scenarioIndex);
}

export function currentScenario(
  scenarios: DemoScenario[],
  state: DemoViewState,
): DemoScenario {
  return scenarios[state.scenarioIndex] ?? scenarios[0];
}
