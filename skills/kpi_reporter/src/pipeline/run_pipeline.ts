/**
 * KPI 报表生成管线 - 统一编排器
 * 流程: fetch -> clean -> compute -> report -> notify
 */

import { join } from 'node:path';
import type { KpiReporterArgs } from '../index.js';
import type { Logger } from '../utils/logger.js';
import {
  resolveTimeWindow,
  formatDateRange,
  type TimeWindow,
} from '../utils/time_window.js';
import {
  ensureDir,
  writeJson,
  writeText,
  generateRunId,
  getRunsDir,
  getBaseDir,
} from '../utils/io.js';
import { fetchLocalFiles } from './adapters/local_files.js';
import { normalizeData, type StandardRecord } from './transform/normalize.js';
import { computeKpis, type KpiResult } from './transform/compute_kpis.js';
import { buildXlsx } from './report/build_xlsx.js';
import { sendSlackNotification } from './notify/slack.js';

export interface PipelineResult {
  success: boolean;
  runId: string;
  reportPath?: string;
  slackSent?: boolean;
  error?: string;
}

export interface RunMeta {
  runId: string;
  startTime: string;
  endTime?: string;
  timeWindow: {
    start: string;
    end: string;
    label: string;
  };
  datasource: string;
  success: boolean;
  error?: string;
  files: {
    raw: string[];
    processed: string;
    report?: string;
    slackMessage?: string;
  };
  durationMs?: number;
}

export async function runPipeline(
  args: KpiReporterArgs,
  logger: Logger
): Promise<PipelineResult> {
  const runId = generateRunId();
  const startTime = new Date();
  const runsDir = getRunsDir();
  const runDir = join(runsDir, runId);

  // 创建运行目录
  ensureDir(runDir);
  ensureDir(join(runDir, 'raw'));
  ensureDir(join(runDir, 'processed'));

  // 设置日志文件
  const logPath = join(runDir, 'run.log');
  logger.setLogFile(logPath);

  logger.info('Pipeline started', { runId, args: JSON.stringify(args) });

  const meta: RunMeta = {
    runId,
    startTime: startTime.toISOString(),
    timeWindow: { start: '', end: '', label: '' },
    datasource: args.datasource,
    success: false,
    files: {
      raw: [],
      processed: join(runDir, 'processed', 'data.json'),
    },
  };

  try {
    // 1. 解析时间窗口
    const timeWindow = resolveTimeWindow(args.time_window);
    meta.timeWindow = {
      start: timeWindow.start.toISOString().slice(0, 10),
      end: timeWindow.end.toISOString().slice(0, 10),
      label: timeWindow.label,
    };
    logger.info('Time window resolved', {
      label: timeWindow.label,
      range: formatDateRange(timeWindow.start, timeWindow.end),
    });

    // 2. 获取数据
    logger.info('Fetching data from datasource', { datasource: args.datasource });
    const dataDir = join(getBaseDir(), 'data');
    const rawData = await fetchLocalFiles(dataDir, timeWindow, logger);

    if (rawData.length === 0) {
      throw new Error('未找到任何数据文件或数据为空');
    }

    // 保存原始数据快照
    const rawPath = join(runDir, 'raw', 'raw_data.json');
    writeJson(rawPath, rawData);
    meta.files.raw.push(rawPath);
    logger.info('Raw data saved', { count: rawData.length, path: rawPath });

    // 3. 标准化数据
    logger.info('Normalizing data');
    const normalizedData = normalizeData(rawData);
    writeJson(meta.files.processed, normalizedData);
    logger.info('Data normalized', { count: normalizedData.length });

    // 4. 计算 KPI
    logger.info('Computing KPIs');
    const configPath = join(getBaseDir(), 'config', 'kpis.yaml');
    const kpiResults = await computeKpis(
      normalizedData,
      configPath,
      timeWindow,
      logger
    );
    logger.info('KPIs computed', { count: kpiResults.current.length });

    // 5. 生成报表
    if (args.output.xlsx) {
      logger.info('Building XLSX report');
      const reportPath = join(runDir, 'report.xlsx');
      await buildXlsx(
        kpiResults,
        normalizedData,
        timeWindow,
        reportPath,
        logger
      );
      meta.files.report = reportPath;
      logger.info('Report generated', { path: reportPath });
    }

    // 6. 生成 Slack 消息
    const slackMessage = generateSlackMessage(kpiResults, timeWindow);
    const slackMessagePath = join(runDir, 'slack_message.txt');
    writeText(slackMessagePath, slackMessage);
    meta.files.slackMessage = slackMessagePath;

    // 7. 发送 Slack 通知
    let slackSent = false;
    if (args.output.slack && args.slack?.channel && !args.dry_run) {
      logger.info('Sending Slack notification', { channel: args.slack.channel });
      slackSent = await sendSlackNotification(
        args.slack.channel,
        slackMessage,
        meta.files.report,
        args.slack.mention,
        logger
      );
      logger.info('Slack notification sent', { success: slackSent });
    } else if (args.dry_run) {
      logger.info('Dry run mode - skipping Slack notification');
    }

    // 完成
    const endTime = new Date();
    meta.endTime = endTime.toISOString();
    meta.durationMs = endTime.getTime() - startTime.getTime();
    meta.success = true;

    // 保存元信息
    writeJson(join(runDir, 'meta.json'), meta);

    logger.info('Pipeline completed successfully', {
      durationMs: meta.durationMs,
    });

    return {
      success: true,
      runId,
      reportPath: meta.files.report,
      slackSent,
    };
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : String(error);
    const errorStack = error instanceof Error ? error.stack : undefined;

    logger.error('Pipeline failed', { error: errorMessage, stack: errorStack });

    meta.success = false;
    meta.error = errorMessage;
    meta.endTime = new Date().toISOString();
    meta.durationMs = new Date().getTime() - startTime.getTime();

    writeJson(join(runDir, 'meta.json'), meta);

    return {
      success: false,
      runId,
      error: errorMessage,
    };
  }
}

function generateSlackMessage(
  kpiResults: { current: KpiResult[]; previous: KpiResult[] },
  timeWindow: ReturnType<typeof resolveTimeWindow>
): string {
  const lines: string[] = [];

  lines.push(`📊 *KPI 报表 - ${timeWindow.label}*`);
  lines.push(
    `📅 ${formatDateRange(timeWindow.start, timeWindow.end)}`
  );
  lines.push('');
  lines.push('*核心指标*');

  for (const kpi of kpiResults.current) {
    const prev = kpiResults.previous.find((p) => p.name === kpi.name);
    let changeStr = '';

    if (prev && prev.value !== 0) {
      const change = ((kpi.value - prev.value) / prev.value) * 100;
      const arrow = change >= 0 ? '📈' : '📉';
      const sign = change >= 0 ? '+' : '';
      changeStr = ` ${arrow} ${sign}${change.toFixed(1)}%`;
    }

    const valueStr =
      kpi.value % 1 === 0
        ? kpi.value.toLocaleString()
        : kpi.value.toFixed(2);

    lines.push(`• *${kpi.name}*: ${valueStr}${changeStr}`);
  }

  lines.push('');
  lines.push('_详细报表见附件_');

  return lines.join('\n');
}
