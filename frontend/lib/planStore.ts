// In-flight planning runs, kept at module scope so a run survives navigating away from the
// project (which unmounts Workspace/PlanPanel) and the Plan panel can re-attach on return.
// Before this, the SSE stream + progress lived in component state and vanished on navigation.
//
// ponytail: in-memory, survives client-side nav but NOT a hard page reload — the underlying
// fetch dies with the page. The plan still persists server-side, so a reload just shows the
// finished storyboard (or, if mid-run, an idle Plan panel to re-plan). Upgrade path if reloads
// must resume: a server "planning" status + reconnectable stream.

import { PLAN_STREAM_PATH, type ClarifyAnswer } from "@/lib/api";
import { streamSSE } from "@/lib/sse";

export type StageStatus = "idle" | "running" | "done" | "error";
export type StageState = { status: StageStatus; detail?: string; index?: number; total?: number };

export type PlanRun = {
  running: boolean;
  finished: boolean; // server emitted the terminal `done` (plan is persisted)
  error: string | null;
  stages: Record<string, StageState>; // keyed by phase id (brief/script/looks/board)
};

const runs = new Map<string, PlanRun>();
const subs = new Map<string, Set<() => void>>();

function notify(id: string) {
  subs.get(id)?.forEach((fn) => fn());
}

export function getRun(id: string): PlanRun | undefined {
  return runs.get(id);
}

export function subscribe(id: string, fn: () => void): () => void {
  let set = subs.get(id);
  if (!set) subs.set(id, (set = new Set()));
  set.add(fn);
  return () => set!.delete(fn);
}

/** Drop a run once the panel has consumed its terminal state (so it doesn't re-fire). */
export function clearRun(id: string) {
  runs.delete(id);
  notify(id);
}

export async function startPlan(
  id: string,
  params: { brief: string; clarifications: ClarifyAnswer[]; seconds: number },
): Promise<void> {
  const existing = runs.get(id);
  if (existing?.running) return; // already streaming — don't double-start
  const run: PlanRun = { running: true, finished: false, error: null, stages: {} };
  runs.set(id, run);
  notify(id);

  let current = "brief";
  try {
    await streamSSE(PLAN_STREAM_PATH(id), {
      method: "POST",
      body: {
        raw_prompt: params.brief,
        clarifications: params.clarifications,
        target_duration_sec: params.seconds,
      },
      onEvent: (e) => {
        if (e.type === "stage") {
          current = (e.phase as string) ?? current;
          if (e.status === "running") run.stages[current] = { status: "running" };
          else if (e.status === "progress")
            run.stages[current] = {
              status: "running",
              detail: e.text as string | undefined,
              index: e.index as number | undefined,
              total: e.total as number | undefined,
            };
          else if (e.status === "done")
            run.stages[current] = { status: "done", detail: e.detail as string | undefined };
        } else if (e.type === "done") run.finished = true;
        else if (e.type === "error") run.error = (e.message as string) || "Planning failed.";
        notify(id);
      },
    });
    if (run.error) throw new Error(run.error);
    if (!run.finished) throw new Error("The planning stream ended early — please retry.");
  } catch (e) {
    run.stages[current] = { status: "error" };
    run.error = e instanceof Error ? e.message : String(e);
  } finally {
    run.running = false;
    notify(id);
  }
}
