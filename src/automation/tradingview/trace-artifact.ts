import {
  traceEventV1Schema,
  tvTraceArtifactSchema,
  type TraceEventV1,
  type TvTraceArtifact,
} from "../../contracts/types.js";

export const AF_TRACE_PREFIX = "AFTRACE|v1|";

export function formatAfTracePayload(input: TraceEventV1): string {
  const event = traceEventV1Schema.parse(input);
  const fields = {
    barIndex: event.barIndex,
    time: event.time,
    orderAction: event.orderAction,
    finalBullEvent: event.finalBullEvent,
    finalBearEvent: event.finalBearEvent,
    entryPass: event.entryPass ? 1 : 0,
    entryRank: event.entryRank,
    exitReason: event.exitReason ?? "none",
    slotCount: event.slotCount,
  };
  return `${AF_TRACE_PREFIX}${Object.entries(fields)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(";")}`;
}

export function parseAfTracePayload(value: string | null | undefined): TraceEventV1 | null {
  if (typeof value !== "string") {
    return null;
  }
  const prefixIndex = value.indexOf(AF_TRACE_PREFIX);
  if (prefixIndex < 0) {
    return null;
  }

  const payload = value.slice(prefixIndex + AF_TRACE_PREFIX.length).trim();
  if (!payload) {
    return null;
  }

  const parsed = payload.startsWith("{")
    ? parseJsonPayload(payload)
    : parseKeyValuePayload(payload);
  return normalizeTraceEvent(parsed);
}

export function normalizeTraceEventForParity(
  value: Record<string, unknown>,
): TraceEventV1 | null {
  return normalizeTraceEvent(value);
}

export function isOrderBearingTraceEvent(event: TraceEventV1): boolean {
  return event.orderAction !== "none";
}

export function buildTvTraceArtifact(events: TraceEventV1[]): TvTraceArtifact {
  return tvTraceArtifactSchema.parse({
    schemaVersion: "tv-trace-artifact/v1",
    source: "tradingview-report",
    tracePrefix: AF_TRACE_PREFIX,
    events,
    missingReason: events.length === 0 ? "aftrace_comments_missing" : null,
  });
}

export function extractTraceEventsFromUnknownReportData(
  reportData: unknown,
  maxEvents = 200,
): TraceEventV1[] {
  const comments = collectComments(reportData);
  const events: TraceEventV1[] = [];
  for (const comment of comments) {
    const event = parseAfTracePayload(comment);
    if (!event) {
      continue;
    }
    events.push(event);
    if (events.length >= maxEvents) {
      break;
    }
  }
  return events;
}

function parseJsonPayload(payload: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(payload) as unknown;
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function parseKeyValuePayload(payload: string): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  for (const part of payload.split(/[;|]/)) {
    const separatorIndex = part.indexOf("=");
    if (separatorIndex <= 0) {
      continue;
    }
    const key = part.slice(0, separatorIndex).trim();
    const value = part.slice(separatorIndex + 1).trim();
    if (key) {
      fields[key] = value;
    }
  }
  return fields;
}

function normalizeTraceEvent(value: Record<string, unknown>): TraceEventV1 | null {
  const event = traceEventV1Schema.safeParse({
    barIndex: toInteger(value.barIndex),
    time: normalizeTimeValue(value.time),
    orderAction: normalizeOrderAction(value.orderAction),
    finalBullEvent: toInteger(value.finalBullEvent),
    finalBearEvent: toInteger(value.finalBearEvent),
    entryPass: toBoolean(value.entryPass),
    entryRank: toNumber(value.entryRank),
    exitReason: normalizeExitReason(value.exitReason),
    slotCount: toInteger(value.slotCount),
  });
  return event.success ? event.data : null;
}

function collectComments(value: unknown): string[] {
  const comments: string[] = [];
  const visit = (entry: unknown): void => {
    if (typeof entry === "string") {
      if (entry.includes(AF_TRACE_PREFIX)) {
        comments.push(entry);
      }
      return;
    }
    if (Array.isArray(entry)) {
      for (const item of entry) {
        visit(item);
      }
      return;
    }
    if (typeof entry !== "object" || entry === null) {
      return;
    }
    for (const [key, child] of Object.entries(entry)) {
      if ((key === "c" || key.toLowerCase().includes("comment")) && typeof child === "string") {
        visit(child);
      } else if (typeof child === "object" && child !== null) {
        visit(child);
      }
    }
  };
  visit(value);
  return comments;
}

function toInteger(value: unknown): number {
  const numeric = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(numeric) ? Math.max(0, Math.trunc(numeric)) : 0;
}

function toNumber(value: unknown): number {
  const numeric = typeof value === "number" ? value : Number.parseFloat(String(value ?? ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function toBoolean(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  const normalized = String(value ?? "").trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

function normalizeTimeValue(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(Math.trunc(value));
  }
  const text = String(value ?? "").trim();
  return text.length > 0 ? text : "unknown";
}

function normalizeOrderAction(value: unknown): TraceEventV1["orderAction"] {
  const normalized = String(value ?? "none").trim();
  switch (normalized) {
    case "entry":
    case "exit":
    case "replace":
    case "entry_exit":
    case "none":
      return normalized;
    default:
      return "none";
  }
}

function normalizeExitReason(value: unknown): string | null {
  const normalized = String(value ?? "").trim();
  if (
    normalized.length === 0 ||
    normalized === "none" ||
    normalized === "null" ||
    normalized === "na"
  ) {
    return null;
  }
  return normalized;
}
