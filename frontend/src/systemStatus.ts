import { useCallback, useMemo, useReducer } from "react";

export type IssueScope = "server" | "dashboard" | "database" | "risk" | "learning" | "ai" | "explanation" | "mode" | "reset" | "setup" | "engine" | "providers" | "storage" | "leaderboard" | "maintenance";

export interface SystemIssue {
  id: string;
  scope: IssueScope;
  title: string;
  detail: string;
  firstSeenAt: number;
  lastSeenAt: number;
  occurrences: number;
  resolvedAt: number | null;
}

export interface SystemStatusState {
  issues: SystemIssue[];
  activeByScope: Partial<Record<IssueScope, string>>;
  lastSuccessAt: number | null;
  sequence: number;
}

export type SystemStatusAction =
  | { type: "report"; scope: IssueScope; title: string; detail: string; at: number }
  | { type: "resolve"; scope: IssueScope; at: number; serverHealthy?: boolean }
  | { type: "clear-history" };

export const INITIAL_SYSTEM_STATUS: SystemStatusState = {
  issues: [],
  activeByScope: {},
  lastSuccessAt: null,
  sequence: 0,
};

const MAX_HISTORY = 20;

export function systemStatusReducer(
  state: SystemStatusState,
  action: SystemStatusAction,
): SystemStatusState {
  if (action.type === "clear-history") {
    return {
      ...state,
      issues: state.issues.filter((issue) => issue.resolvedAt === null),
    };
  }

  if (action.type === "resolve") {
    const scopes: IssueScope[] = action.serverHealthy
      ? ["server", "risk", "learning", "ai", "explanation", "mode", "reset", "setup", "engine", "maintenance"]
      : [action.scope];
    const activeIds = new Set(scopes.map((scope) => state.activeByScope[scope]).filter(Boolean));
    const activeByScope = { ...state.activeByScope };
    scopes.forEach((scope) => delete activeByScope[scope]);
    return {
      ...state,
      activeByScope,
      issues: activeIds.size
        ? state.issues.map((issue) =>
            activeIds.has(issue.id) && issue.resolvedAt === null
              ? { ...issue, resolvedAt: action.at }
              : issue,
          )
        : state.issues,
      lastSuccessAt: action.serverHealthy ? action.at : state.lastSuccessAt,
    };
  }

  const activeId = state.activeByScope[action.scope];
  const activeIssue = state.issues.find((issue) => issue.id === activeId);
  if (
    activeIssue &&
    activeIssue.title === action.title &&
    activeIssue.detail === action.detail
  ) {
    return {
      ...state,
      issues: state.issues.map((issue) =>
        issue.id === activeIssue.id
          ? { ...issue, lastSeenAt: action.at, occurrences: issue.occurrences + 1 }
          : issue,
      ),
    };
  }

  const sequence = state.sequence + 1;
  const issue: SystemIssue = {
    id: `${action.at}-${sequence}`,
    scope: action.scope,
    title: action.title,
    detail: action.detail,
    firstSeenAt: action.at,
    lastSeenAt: action.at,
    occurrences: 1,
    resolvedAt: null,
  };
  const closedPrevious = activeId
    ? state.issues.map((entry) =>
        entry.id === activeId && entry.resolvedAt === null
          ? { ...entry, resolvedAt: action.at }
          : entry,
      )
    : state.issues;

  return {
    ...state,
    sequence,
    activeByScope: { ...state.activeByScope, [action.scope]: issue.id },
    issues: [issue, ...closedPrevious].slice(0, MAX_HISTORY),
  };
}

export function friendlyError(cause: unknown): string {
  const fallback = "Something unexpected happened. Try again in a moment.";
  const raw = cause instanceof Error ? cause.message.trim() : "";
  if (!raw) return fallback;
  const lower = raw.toLowerCase();
  if (
    lower.includes("failed to fetch") ||
    lower.includes("networkerror") ||
    lower.includes("load failed") ||
    lower.includes("network request failed")
  ) {
    return "The app server is temporarily unreachable. Signal Arcade will keep retrying quietly.";
  }
  return raw.length > 280 ? `${raw.slice(0, 277)}…` : raw;
}

export function useSystemStatus() {
  const [state, dispatch] = useReducer(systemStatusReducer, INITIAL_SYSTEM_STATUS);

  const reportIssue = useCallback(
    (scope: IssueScope, title: string, cause: unknown) => {
      dispatch({
        type: "report",
        scope,
        title,
        detail: friendlyError(cause),
        at: Date.now(),
      });
    },
    [],
  );
  const resolveIssue = useCallback((scope: IssueScope, serverHealthy = false) => {
    dispatch({ type: "resolve", scope, at: Date.now(), serverHealthy });
  }, []);
  const clearHistory = useCallback(() => dispatch({ type: "clear-history" }), []);
  const activeIssues = useMemo(
    () =>
      state.issues
        .filter((issue) => issue.resolvedAt === null)
        .sort((left, right) => right.lastSeenAt - left.lastSeenAt),
    [state.issues],
  );

  return { state, activeIssues, reportIssue, resolveIssue, clearHistory };
}
