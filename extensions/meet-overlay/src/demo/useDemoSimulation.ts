import { useCallback, useEffect, useRef, useState } from "react";
import { DEMO_SCENARIOS } from "../data/demoScenarios";
import type { DemoScenario } from "../types/session";
import {
  advanceDemoClock,
  createInitialDemoState,
  currentScenario,
  goToNextScenario,
  pauseDemo,
  resetDemo,
  resumeDemo,
  startDemo,
  type DemoViewState,
} from "./demoEngine";

const TICK_MS = 100;

/**
 * React binder for the pure demo engine.
 * Timers stop on pause/complete/unmount so updates never continue after close.
 */
export function useDemoSimulation(scenarios: DemoScenario[] = DEMO_SCENARIOS) {
  const [state, setState] = useState<DemoViewState>(() => createInitialDemoState(0));
  const stateRef = useRef(state);
  stateRef.current = state;
  const scenariosRef = useRef(scenarios);
  scenariosRef.current = scenarios;

  useEffect(() => {
    if (state.status !== "running") return;

    const id = window.setInterval(() => {
      const scenario = currentScenario(scenariosRef.current, stateRef.current);
      setState((prev) => advanceDemoClock(prev, scenario, TICK_MS));
    }, TICK_MS);

    return () => {
      window.clearInterval(id);
    };
  }, [state.status]);

  // Hard stop on unmount.
  useEffect(() => {
    return () => {
      stateRef.current = createInitialDemoState(0);
    };
  }, []);

  const scenario = currentScenario(scenarios, state);

  return {
    state,
    scenario,
    scenarios,
    start: useCallback(() => setState((s) => startDemo(s)), []),
    pause: useCallback(() => setState((s) => pauseDemo(s)), []),
    resume: useCallback(() => setState((s) => resumeDemo(s)), []),
    reset: useCallback(() => setState((s) => resetDemo(s)), []),
    nextScenario: useCallback(
      () => setState((s) => goToNextScenario(s, scenariosRef.current.length)),
      [],
    ),
  };
}
