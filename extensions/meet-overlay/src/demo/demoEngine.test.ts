import { describe, expect, it } from "vitest";
import { DEMO_SCENARIOS } from "../data/demoScenarios";
import {
  advanceDemoClock,
  createInitialDemoState,
  goToNextScenario,
  pauseDemo,
  resetDemo,
  resumeDemo,
  startDemo,
  syncTimeline,
} from "./demoEngine";

const [ordinary, possibleAi] = DEMO_SCENARIOS;

describe("demoEngine", () => {
  it("starts, pauses, resumes, and resets", () => {
    let state = createInitialDemoState(0);
    state = startDemo(state);
    expect(state.status).toBe("running");
    state = pauseDemo(state);
    expect(state.status).toBe("paused");
    state = resumeDemo(state);
    expect(state.status).toBe("running");
    state = resetDemo(state);
    expect(state.status).toBe("idle");
    expect(state.elapsedMs).toBe(0);
    expect(state.revealedSegments).toEqual([]);
    expect(state.detection.kind).toBe("no_result");
  });

  it("reveals question → transcript → processing → result → follow-up in order", () => {
    let state = startDemo(createInitialDemoState(0));
    state = advanceDemoClock(state, ordinary, 700);
    expect(state.questionVisible).toBe(true);

    state = advanceDemoClock(state, ordinary, 800);
    expect(state.candidateResponding).toBe(true);
    expect(state.revealedSegments.length).toBeGreaterThanOrEqual(1);

    state = advanceDemoClock(state, ordinary, 4500);
    expect(state.detection.kind).toBe("processing");

    state = advanceDemoClock(state, ordinary, 2000);
    expect(state.detection.kind).toBe("available");
    if (state.detection.kind === "available") {
      expect(state.detection.prediction.confidence.status).toBe("unavailable");
      expect(state.detection.prediction.rawScore).toBeNull();
    }

    state = advanceDemoClock(state, ordinary, 800);
    expect(state.followupVisible).toBe(true);

    state = advanceDemoClock(state, ordinary, 800);
    expect(state.status).toBe("completed");
  });

  it("supports the contrasting AI-indicator scenario without inventing calibrated confidence", () => {
    let state = startDemo(createInitialDemoState(1));
    state = syncTimeline({ ...state, elapsedMs: 9000 }, possibleAi);
    expect(state.detection.kind).toBe("available");
    if (state.detection.kind === "available") {
      expect(state.detection.prediction.reviewStatus).toBe("Requires review");
      expect(state.detection.prediction.confidence.status).toBe("unavailable");
      expect(
        state.detection.prediction.evidence.some((e) => e.category === "detection"),
      ).toBe(true);
    }
    expect(state.followupVisible).toBe(true);
  });

  it("switches to the next synthetic scenario and clears progress", () => {
    let state = startDemo(createInitialDemoState(0));
    state = advanceDemoClock(state, ordinary, 5000);
    state = goToNextScenario(state, DEMO_SCENARIOS.length);
    expect(state.scenarioIndex).toBe(1);
    expect(state.status).toBe("idle");
    expect(state.revealedSegments).toEqual([]);
    expect(state.detection.kind).toBe("no_result");
  });

  it("does not advance while paused", () => {
    let state = startDemo(createInitialDemoState(0));
    state = advanceDemoClock(state, ordinary, 2000);
    const segments = state.revealedSegments.length;
    state = pauseDemo(state);
    state = advanceDemoClock(state, ordinary, 5000);
    expect(state.revealedSegments.length).toBe(segments);
    expect(state.status).toBe("paused");
  });
});
