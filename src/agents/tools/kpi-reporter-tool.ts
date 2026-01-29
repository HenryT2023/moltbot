import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";

import { Type } from "@sinclair/typebox";

import type { MoltbotConfig } from "../../config/config.js";
import { resolveUserPath } from "../../utils.js";
import { type AnyAgentTool, jsonResult, readStringParam } from "./common.js";

const KpiReporterToolSchema = Type.Object({
  action: Type.Optional(Type.Union([Type.Literal("run"), Type.Literal("status")])),
  time_window: Type.Optional(
    Type.Union([
      Type.String({ description: "Preset: yesterday, last_7_days, last_week, this_month" }),
      Type.Object({
        start: Type.String({ description: "Start date (YYYY-MM-DD)" }),
        end: Type.String({ description: "End date (YYYY-MM-DD)" }),
      }),
    ]),
  ),
  slack_channel: Type.Optional(Type.String({ description: "Slack channel to send report" })),
  dry_run: Type.Optional(Type.Boolean({ description: "If true, do not send to Slack" })),
});

type KpiReporterToolOptions = {
  config?: MoltbotConfig;
  workspaceDir?: string;
};

function resolveSkillDir(workspaceDir?: string): string {
  if (workspaceDir) {
    const wsSkillDir = path.join(workspaceDir, "skills", "kpi_reporter");
    if (fs.existsSync(wsSkillDir)) return wsSkillDir;
  }
  // Fallback to user home
  const homeSkillDir = resolveUserPath("~/skills/kpi_reporter");
  if (fs.existsSync(homeSkillDir)) return homeSkillDir;
  throw new Error("KPI Reporter skill not found. Please install it first.");
}

function buildCliArgs(params: Record<string, unknown>): string[] {
  const args: string[] = [];

  // Time window
  const timeWindow = params.time_window;
  if (timeWindow) {
    if (typeof timeWindow === "string") {
      args.push("--time_window", timeWindow);
    } else if (typeof timeWindow === "object" && timeWindow !== null) {
      const tw = timeWindow as { start?: string; end?: string };
      if (tw.start && tw.end) {
        args.push("--time_window", `${tw.start}:${tw.end}`);
      }
    }
  }

  // Slack channel
  const slackChannel = readStringParam(params, "slack_channel");
  if (slackChannel) {
    args.push("--slack_channel", slackChannel);
  }

  // Dry run
  if (params.dry_run === true) {
    args.push("--dry_run");
  }

  return args;
}

async function runKpiReporter(
  skillDir: string,
  args: string[],
): Promise<{ ok: boolean; output: string; error?: string; reportPath?: string }> {
  return new Promise((resolve) => {
    const scriptPath = path.join(skillDir, "scripts", "run.sh");
    const proc = spawn("bash", [scriptPath, ...args], {
      cwd: skillDir,
      env: { ...process.env },
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
      const ok = code === 0;
      // Extract report path from output
      const reportMatch = stdout.match(/报表路径:\s*(.+\.xlsx)/);
      const reportPath = reportMatch?.[1]?.trim();

      resolve({
        ok,
        output: stdout.trim(),
        error: ok ? undefined : stderr.trim() || "Unknown error",
        reportPath,
      });
    });

    proc.on("error", (err) => {
      resolve({
        ok: false,
        output: "",
        error: err.message,
      });
    });

    // Timeout after 5 minutes
    setTimeout(
      () => {
        proc.kill("SIGTERM");
        resolve({
          ok: false,
          output: stdout.trim(),
          error: "Timeout: KPI report generation took too long",
        });
      },
      5 * 60 * 1000,
    );
  });
}

function getSkillStatus(skillDir: string): { installed: boolean; path: string; hasData: boolean } {
  const dataDir = path.join(skillDir, "data");
  const hasData = fs.existsSync(dataDir) && fs.readdirSync(dataDir).some((f) => f.endsWith(".csv"));
  return {
    installed: true,
    path: skillDir,
    hasData,
  };
}

export function createKpiReporterTool(opts?: KpiReporterToolOptions): AnyAgentTool {
  return {
    label: "KPI Reporter",
    name: "kpi_reporter",
    description: `Generate KPI reports from local data sources.

ACTIONS:
- run: Generate a KPI report (default action)
- status: Check if KPI Reporter skill is installed

PARAMETERS:
- time_window: Time period for the report
  - Presets: "yesterday", "last_7_days", "last_week", "this_month"
  - Custom: { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" }
- slack_channel: Slack channel to send the report (e.g., "#growth")
- dry_run: If true, generate report but don't send to Slack

EXAMPLES:
1. Generate yesterday's report:
   { "time_window": "yesterday" }

2. Generate last week's report and send to Slack:
   { "time_window": "last_week", "slack_channel": "#growth" }

3. Generate custom date range report (dry run):
   { "time_window": { "start": "2024-01-01", "end": "2024-01-15" }, "dry_run": true }

OUTPUT:
Returns the generated report path and summary. The report includes:
- Summary sheet with KPIs and period-over-period comparison
- BySource sheet with metrics by data source
- RawPreview sheet with sample data`,
    parameters: KpiReporterToolSchema,
    execute: async (_toolCallId, args) => {
      const params = args as Record<string, unknown>;
      const action = readStringParam(params, "action") ?? "run";

      let skillDir: string;
      try {
        skillDir = resolveSkillDir(opts?.workspaceDir);
      } catch (err) {
        return jsonResult({
          ok: false,
          error: err instanceof Error ? err.message : "KPI Reporter skill not found",
        });
      }

      if (action === "status") {
        const status = getSkillStatus(skillDir);
        return jsonResult(status);
      }

      // Default: run
      const cliArgs = buildCliArgs(params);
      const result = await runKpiReporter(skillDir, cliArgs);
      return jsonResult(result);
    },
  };
}
