import path from "node:path";
import process from "node:process";

import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import { appendJsonl, createCandidateId, ensureDir } from "../utils/fs.js";

const commandDisplayNames: Record<string, string> = {
  bootstrap: "초기 설정",
  mutate: "변형 생성",
  evaluate: "후보 평가",
  repair: "컴파일 복구",
  iterate: "반복 실행",
  "run-tasks": "작업 배치 실행",
  "rebuild-indexes": "인덱스 재생성",
  "check-knowledge-tree": "지식 트리 감사",
  "migrate-state": "지식 구조 이관",
};

const eventDisplayNames: Record<string, string> = {
  "bootstrap.start": "초기화 시작",
  "bootstrap.smoke": "실행기 점검",
  "bootstrap.done": "초기화 완료",
  "mutate.start": "변형 시작",
  "mutation.request": "변형 요청",
  "mutation.response": "변형 응답",
  "mutation.parsed": "변형 해석",
  "mutation.brief": "변형 브리프",
  "mutation.preflight": "생성 사전 점검",
  "mutation.preflight_blocked": "생성 차단 감지",
  "mutation.preflight_repair": "생성 즉시 복구",
  "mutation.generation_failed": "생성 실패 기록",
  "mutate.done": "변형 완료",
  "evaluate.start": "평가 시작",
  "repair.start": "복구 준비",
  "repair.compile.start": "컴파일 복구 시작",
  "repair.compile.response": "복구 응답 수신",
  "repair.compile.parsed": "복구 응답 해석",
  "repair.persisted": "복구 후보 저장",
  "repair.compile.applied": "복구 소스 반영",
  "repair.compile": "복구 후 컴파일",
  "repair.compile.failed": "복구 시도 실패",
  "repair.done": "복구 완료",
  "iterate.start": "반복 실행 시작",
  "iterate.loop": "반복 진행",
  "iterate.done": "반복 실행 완료",
  "iteration.start": "반복 시작",
  "hypothesis.ready": "가설 준비",
  "candidate.persisted": "후보 저장",
  "runtime.updated": "실행 대상 갱신",
  "executor.chart_ready": "실행 표면 준비",
  "executor.source_updated": "Pine 소스 반영",
  "executor.compile": "컴파일",
  "executor.apply": "전략 적용",
  "executor.metrics": "백테스트 지표",
  "evaluation.objective": "목적 함수 평가",
  "evaluation.contributions": "조건 기여도 계산",
  "analysis.loss_zones": "손실 구간 분석",
  "task.batch_start": "배치 시작",
  "task.batch_update": "배치 진행",
  "task.batch_done": "배치 완료",
  "task.runtime_failure": "실행 오류 기록",
  "state.recorded": "상태 기록",
  "indexes.start": "인덱스 재생성 시작",
  "indexes.done": "인덱스 재생성 완료",
  "knowledge.audit": "지식 트리 감사",
  "knowledge.migrate": "지식 구조 이관",
};

const messageDisplayNames: Record<string, string> = {
  "Initializing workspace": "워크스페이스를 초기화합니다.",
  "Running Pine evaluation smoke check": "Pine 평가 실행기 연결을 점검합니다.",
  "Pine evaluation smoke check succeeded": "Pine 평가 실행기 연결 점검이 끝났습니다.",
  "Bootstrap command completed": "초기 설정 명령을 완료했습니다.",
  "Preparing mutation request": "변형 요청을 준비합니다.",
  "Mutation hypothesis prepared": "가설을 준비했습니다.",
  "Sending mutation request": "변형 생성을 요청합니다.",
  "Received mutation response": "변형 응답을 받았습니다.",
  "Parsed mutation response": "변형 응답을 해석했습니다.",
  "Parsed mutation payload": "변형 응답을 해석했습니다.",
  "Mutation preflight completed": "Pine 생성 사전 점검을 마쳤습니다.",
  "Blocking mutation preflight issues detected": "Pine 생성 사전 점검에서 차단 이슈를 발견했습니다.",
  "Attempting preflight repair": "생성 단계에서 즉시 복구를 시도합니다.",
  "Mutation generation failure recorded": "Pine 생성 실패를 기록했습니다.",
  "Mutation brief ready": "변형 브리프를 준비했습니다.",
  "Candidate artifact persisted": "후보 아티팩트를 저장했습니다.",
  "Starting candidate evaluation": "후보 평가를 시작합니다.",
  "Preparing compile repair": "컴파일 복구를 준비합니다.",
  "Starting compile repair": "컴파일 오류 복구를 시작합니다.",
  "Received compile repair response": "컴파일 복구 응답을 받았습니다.",
  "Parsed compile repair response": "컴파일 복구 응답을 해석했습니다.",
  "Repair candidate artifact persisted": "복구 후보 아티팩트를 저장했습니다.",
  "Repaired Pine source pushed": "복구된 Pine 소스를 반영했습니다.",
  "Compile finished after repair": "복구 후 컴파일을 마쳤습니다.",
  "Compile repair attempt failed": "컴파일 복구 시도가 실패했습니다.",
  "Compile repair attempts exhausted": "컴파일 복구 시도를 모두 사용했습니다.",
  "Compile repair completed": "컴파일 복구를 완료했습니다.",
  "Evaluation surface prepared": "평가 실행 표면 준비를 마쳤습니다.",
  "Pine source pushed": "Pine 소스를 반영했습니다.",
  "Compile finished": "컴파일을 마쳤습니다.",
  "Apply finished": "전략 적용을 마쳤습니다.",
  "Backtest metrics captured": "백테스트 지표를 수집했습니다.",
  "Objective evaluated": "목적 함수를 평가했습니다.",
  "Condition contributions computed": "조건별 기여도를 계산했습니다.",
  "Starting task batch": "작업 배치를 시작합니다.",
  "Task batch progress updated": "작업 배치 진행 상황을 갱신했습니다.",
  "Task batch completed": "작업 배치를 완료했습니다.",
  "Task runtime failure recorded": "작업 실행 오류를 기록했습니다.",
  "Experiment recorded and indexes rebuilt": "실험 기록과 인덱스 재생성을 마쳤습니다.",
  "Compile failure recorded": "컴파일 실패를 기록했습니다.",
  "Apply failure recorded": "전략 적용 실패를 기록했습니다.",
  "Empty backtest recorded": "무거래 결과를 기록했습니다.",
  "Starting iterate command": "반복 실행을 시작합니다.",
  "Running iteration": "반복 단계를 진행합니다.",
  "Starting iteration": "반복을 시작합니다.",
  "Hypothesis prepared": "가설을 준비했습니다.",
  "Runtime target updated": "실행 대상 Pine 파일을 갱신했습니다.",
  "Iterate command completed": "반복 실행을 마쳤습니다.",
  "Rebuilding derived indexes": "파생 인덱스를 재생성합니다.",
  "Derived indexes rebuilt": "파생 인덱스 재생성을 마쳤습니다.",
  "Knowledge tree audited": "지식 트리 감사를 마쳤습니다.",
  "Legacy knowledge migrated": "기존 지식 데이터를 새 구조로 옮겼습니다.",
};

const LOGGED_ERROR_FLAG = Symbol("af.monitorLoggedError");

export interface CliMonitor {
  readonly tracePath: string;
  setTask(taskNumber: number): Promise<void>;
  clearTask(): void;
  log(event: string, message: string, details?: Record<string, unknown>): Promise<void>;
  fail(error: unknown): Promise<void>;
  close(): Promise<void>;
}

interface CreateCliMonitorInput {
  workspaceRoot: string;
  stateRoot?: string;
  commandName: string;
  sink?: (line: string) => void;
}

type LoggedCliError = Error & { [LOGGED_ERROR_FLAG]: true };

export function isMonitorLoggedError(error: unknown): boolean {
  return (
    error instanceof Error &&
    LOGGED_ERROR_FLAG in error &&
    Boolean((error as Partial<LoggedCliError>)[LOGGED_ERROR_FLAG])
  );
}

export async function createCliMonitor(
  input: CreateCliMonitorInput,
): Promise<CliMonitor> {
  const effectiveStateRoot = path.resolve(
    input.stateRoot ??
      process.env.AF_STATE_ROOT ??
      path.join(input.workspaceRoot, "state", "pi-autoresearch"),
  );
  const tracesDir = resolveKnowledgePaths(effectiveStateRoot).tracesDir;
  await ensureDir(tracesDir);
  const tracePath = path.join(
    tracesDir,
    `${input.commandName}-${new Date().toISOString().replace(/[:.]/g, "-")}-${createCandidateId("trace")}.jsonl`,
  );
  const sink = input.sink ?? ((line: string) => process.stderr.write(`${line}\n`));
  let currentTaskNumber: number | null = null;

  return {
    tracePath,
    async setTask(taskNumber) {
      currentTaskNumber = taskNumber;
      const timestamp = new Date().toISOString();
      sink(`-------task ${formatTaskNumber(taskNumber)}----------`);
      await appendJsonl(tracePath, {
        timestamp,
        command: input.commandName,
        event: "task.start",
        message: "Task started",
        details: { taskNumber },
      });
    },
    clearTask() {
      currentTaskNumber = null;
    },
    async log(event, message, details = {}) {
      const timestamp = new Date().toISOString();
      const taskLabel =
        currentTaskNumber === null ? "" : ` task ${formatTaskNumber(currentTaskNumber)}`;
      sink(
        `[${translateEvent(event)}] ${translateCommand(input.commandName)}${taskLabel} | ${buildUserContent(event, message, details)} | ${timestamp}`,
      );
      await appendJsonl(tracePath, {
        timestamp,
        command: input.commandName,
        event,
        message,
        details,
        taskNumber: currentTaskNumber,
      });
    },
    async fail(error) {
      const timestamp = new Date().toISOString();
      const taskLabel =
        currentTaskNumber === null ? "" : ` task ${formatTaskNumber(currentTaskNumber)}`;
      sink(
        `[실행 오류] ${translateCommand(input.commandName)}${taskLabel} | ${buildUserFacingError(error)} 시스템 로그: ${tracePath} | ${timestamp}`,
      );
      await appendJsonl(tracePath, {
        timestamp,
        command: input.commandName,
        event: "command.error",
        message: extractErrorMessage(error),
        details: {
          message: extractErrorMessage(error),
          stack: error instanceof Error ? error.stack ?? null : null,
        },
        taskNumber: currentTaskNumber,
      });
    },
    async close() {
      return;
    },
  };
}

function buildUserContent(
  event: string,
  message: string,
  details: Record<string, unknown>,
): string {
  const translatedMessage = translateMessage(message);
  const summary = summarizeDetails(event, details);
  return summary ? `${translatedMessage} ${summary}` : translatedMessage;
}

function summarizeDetails(
  event: string,
  details: Record<string, unknown>,
): string | null {
  switch (event) {
    case "bootstrap.start":
      return maybeJoin([valueLabel("workspace", details.workspaceRoot)]);
    case "bootstrap.done":
      return maybeJoin([
        valueLabel("실행기", details.evaluationExecutor),
        valueLabel("실행표면 준비", formatBoolean(details.executionSurfaceConfigured)),
        valueLabel("OpenAI", formatOpenAiStatus(details.openAiReachable, details.openAiStatus)),
      ]);
    case "iterate.start":
      return maybeJoin([
        valueLabel("횟수", formatCount(details.count)),
        valueLabel("runId", details.runId),
      ]);
    case "iterate.loop":
      return maybeJoin([
        valueLabel("진행", `${details.currentIteration ?? "?"}/${details.totalIterations ?? "?"}`),
      ]);
    case "iteration.start":
      return maybeJoin([
        valueLabel("iteration", details.iteration),
        valueLabel("기준 후보", details.acceptedHeadCandidateId ?? "seed"),
        valueLabel("기준 점수", formatScore(details.acceptedHeadScore)),
      ]);
    case "hypothesis.ready":
      return maybeJoin([
        valueLabel("다음 방향", details.nextMutationDirection),
      ]);
    case "mutation.brief":
      return maybeJoin([
        valueLabel("최근 실패", formatList(details.recentFailures, 3)),
        valueLabel("손실 구간", formatList(details.lossHotZones, 3)),
      ]);
    case "mutation.response":
    case "repair.compile.response":
      return maybeJoin([valueLabel("응답 길이", formatChars(details.responseLength))]);
    case "mutation.parsed":
    case "repair.compile.parsed":
      return maybeJoin([
        valueLabel("조건 수", formatCount(details.conditionCount)),
        valueLabel("요약", truncate(details.candidateSummary, 90)),
      ]);
    case "mutation.preflight":
      return maybeJoin([
        valueLabel("문제", formatCount(details.issueCount)),
        valueLabel("차단", formatCount(details.blockingIssueCount)),
      ]);
    case "mutation.preflight_blocked":
      return maybeJoin([
        valueLabel("차단 코드", formatList(details.issueCodes, 4)),
      ]);
    case "mutation.generation_failed":
      return maybeJoin([
        valueLabel("종류", details.incidentType),
      ]);
    case "candidate.persisted":
    case "mutate.done":
    case "repair.persisted":
      return maybeJoin([
        valueLabel("후보", details.candidateId),
        valueLabel("기준", details.parentCandidateId),
      ]);
    case "runtime.updated":
      return maybeJoin([
        valueLabel("study", truncate(details.studyTitle, 60)),
      ]);
    case "executor.chart_ready":
      return maybeJoin([
        valueLabel("대상", formatChartTarget(details.symbol, details.timeframe, details.chartType)),
      ]);
    case "executor.compile":
    case "repair.compile":
      return details.ok === true
        ? "성공"
        : maybeJoin([
            "실패",
            valueLabel("오류 수", formatCount(Array.isArray(details.errors) ? details.errors.length : 0)),
          ]);
    case "executor.apply":
      return details.ok === true
        ? maybeJoin([
            "성공",
            valueLabel("study", truncate(details.detectedStudyTitle, 60)),
          ])
        : maybeJoin(["실패", valueLabel("사유", truncate(details.message, 80))]);
    case "executor.metrics":
      return maybeJoin([
        valueLabel("거래", formatCount(details.totalTrades)),
        valueLabel("순이익", formatPercent(details.netProfitPercent)),
        valueLabel("수수료후", formatPercent(details.postFeeNetProfitPercent)),
      ]);
    case "analysis.loss_zones":
      return maybeJoin([
        valueLabel("요약", truncate(details.summary, 80)),
        valueLabel("우선 조치", formatList(details.repairPriorities, 2)),
      ]);
    case "evaluation.objective":
      return maybeJoin([
        valueLabel("결정", details.decision),
        valueLabel("점수", formatScore(details.score)),
      ]);
    case "evaluation.contributions":
      return maybeJoin([valueLabel("계산 수", formatCount(details.contributionCount))]);
    case "state.recorded":
      return maybeJoin([
        valueLabel("후보", details.candidateId),
        valueLabel("결정", details.decision),
        valueLabel("점수", formatScore(details.score)),
      ]);
    case "task.batch_start":
      return maybeJoin([
        valueLabel("batch", details.batchId),
        valueLabel("목표", formatCount(details.taskCount)),
      ]);
    case "task.batch_update":
      return maybeJoin([
        valueLabel("완료", formatCount(details.completedTaskCount)),
        valueLabel("최근 결정", details.lastDecision),
        valueLabel("런타임 실패", formatCount(details.runtimeFailureCount)),
      ]);
    case "task.batch_done":
      return maybeJoin([
        valueLabel("상태", details.status),
        valueLabel("완료", formatCount(details.completedTaskCount)),
        valueLabel("런타임 실패", formatCount(details.runtimeFailureCount)),
        valueLabel("사유", details.stopReason),
      ]);
    case "task.runtime_failure":
      return maybeJoin([
        valueLabel("task", formatCount(details.taskNumber)),
        valueLabel("사유", truncate(details.detail, 90)),
      ]);
    case "indexes.start":
    case "indexes.done":
      return maybeJoin([valueLabel("state", details.stateRoot)]);
    case "knowledge.audit":
      return maybeJoin([
        valueLabel("누락", formatCount(details.missingEntries)),
        valueLabel("legacy", formatCount(details.legacyRootArtifacts)),
      ]);
    default:
      return null;
  }
}

function translateCommand(commandName: string): string {
  return commandDisplayNames[commandName] ?? commandName;
}

function translateEvent(event: string): string {
  return eventDisplayNames[event] ?? event;
}

function translateMessage(message: string): string {
  return messageDisplayNames[message] ?? message;
}

function formatTaskNumber(taskNumber: number): string {
  return String(taskNumber).padStart(2, "0");
}

function maybeJoin(parts: Array<string | null | undefined>): string | null {
  const normalized = parts
    .map((part) => (typeof part === "string" ? part.trim() : ""))
    .filter(Boolean);
  return normalized.length > 0 ? normalized.join(", ") : null;
}

function valueLabel(label: string, value: unknown): string | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  return `${label}: ${String(value)}`;
}

function formatCount(value: unknown): string | null {
  return typeof value === "number" ? `${value}` : valueLabel("", value)?.replace(/^: /, "") ?? null;
}

function formatChars(value: unknown): string | null {
  return typeof value === "number" ? `${value}자` : null;
}

function formatPercent(value: unknown): string | null {
  return typeof value === "number" ? `${value.toFixed(3)}%` : null;
}

function formatScore(value: unknown): string | null {
  return typeof value === "number" ? value.toFixed(4) : null;
}

function formatBoolean(value: unknown): string | null {
  return typeof value === "boolean" ? (value ? "예" : "아니오") : null;
}

function formatOpenAiStatus(reachable: unknown, status: unknown): string | null {
  if (reachable === true && typeof status === "number") {
    return `정상(${status})`;
  }
  if (reachable === false && typeof status === "number") {
    return `오류(${status})`;
  }
  if (reachable === false) {
    return "연결 실패";
  }
  return null;
}

function formatChartTarget(symbol: unknown, timeframe: unknown, chartType: unknown): string | null {
  const parts = [symbol, timeframe, chartType].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : null;
}

function formatList(value: unknown, maxItems: number): string | null {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }
  return value
    .slice(0, maxItems)
    .map((item) => truncate(item, 40))
    .filter(Boolean)
    .join(" · ");
}

function truncate(value: unknown, maxLength: number): string | null {
  if (typeof value !== "string" || value.length === 0) {
    return null;
  }
  return value.length <= maxLength ? value : `${value.slice(0, maxLength - 1)}…`;
}

function extractErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function buildUserFacingError(error: unknown): string {
  const message = extractErrorMessage(error);

  if (message.includes("CDP did not become reachable")) {
    return "TradingView Desktop는 실행됐지만 CDP 연결이 열리지 않았습니다. 원격 디버깅 포트와 실행 옵션을 확인하세요.";
  }

  if (message.includes("Failed to reach OpenAI-compatible endpoint")) {
    return "OpenAI 인증 프록시에 연결하지 못했습니다. OAuth 프록시와 인증 상태를 다시 확인하세요.";
  }

  if (message.includes("openai-oauth proxy did not become ready")) {
    return "OpenAI OAuth 프록시가 준비되지 않았습니다. 인증을 다시 확인하세요.";
  }

  return `작업 중 오류가 발생했습니다. ${truncate(message, 120) ?? ""}`.trim();
}

export async function withCliMonitor<T>(
  input: CreateCliMonitorInput,
  action: (monitor: CliMonitor) => Promise<T>,
): Promise<T> {
  const monitor = await createCliMonitor(input);
  try {
    return await action(monitor);
  } catch (error) {
    await monitor.fail(error);
    const loggedError = new Error(extractErrorMessage(error)) as LoggedCliError;
    loggedError[LOGGED_ERROR_FLAG] = true;
    throw loggedError;
  } finally {
    await monitor.close();
  }
}
