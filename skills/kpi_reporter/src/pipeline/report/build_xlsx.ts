/**
 * Excel 报表生成模块
 * 调用 Python 脚本生成 XLSX 文件
 */

import { spawn } from 'node:child_process';
import { join, dirname } from 'node:path';
import { writeFileSync } from 'node:fs';
import type { KpiResult } from '../transform/compute_kpis.js';
import type { StandardRecord } from '../transform/normalize.js';
import type { ResolvedTimeWindow } from '../../utils/time_window.js';
import { formatDate, formatDateRange } from '../../utils/time_window.js';
import { filterByDateRange, groupBySource } from '../transform/normalize.js';
import { ensureDir, getBaseDir } from '../../utils/io.js';
import type { Logger } from '../../utils/logger.js';

export interface ReportData {
  timeWindow: {
    label: string;
    start: string;
    end: string;
    previousStart: string;
    previousEnd: string;
  };
  kpis: {
    current: KpiResult[];
    previous: KpiResult[];
  };
  bySource: Record<string, { metric: string; value: number }[]>;
  rawPreview: StandardRecord[];
}

export async function buildXlsx(
  kpiResults: { current: KpiResult[]; previous: KpiResult[] },
  data: StandardRecord[],
  timeWindow: ResolvedTimeWindow,
  outputPath: string,
  logger: Logger
): Promise<void> {
  // 准备报表数据
  const currentStart = formatDate(timeWindow.start);
  const currentEnd = formatDate(timeWindow.end);
  const currentData = filterByDateRange(data, currentStart, currentEnd);

  // 按来源分组
  const bySourceMap = groupBySource(currentData);
  const bySource: Record<string, { metric: string; value: number }[]> = {};

  for (const [source, records] of bySourceMap) {
    const metricSums = new Map<string, number>();
    for (const r of records) {
      const current = metricSums.get(r.metric) || 0;
      metricSums.set(r.metric, current + r.value);
    }
    bySource[source] = Array.from(metricSums.entries()).map(([metric, value]) => ({
      metric,
      value,
    }));
  }

  // 原始数据预览（取前 100 条）
  const rawPreview = currentData.slice(0, 100);

  const reportData: ReportData = {
    timeWindow: {
      label: timeWindow.label,
      start: currentStart,
      end: currentEnd,
      previousStart: formatDate(timeWindow.previousStart),
      previousEnd: formatDate(timeWindow.previousEnd),
    },
    kpis: kpiResults,
    bySource,
    rawPreview,
  };

  // 写入临时 JSON 文件供 Python 读取
  const tempDataPath = join(dirname(outputPath), 'report_data.json');
  writeFileSync(tempDataPath, JSON.stringify(reportData, null, 2));

  // 调用 Python 脚本生成 XLSX
  const pythonScript = join(getBaseDir(), 'src', 'pipeline', 'report', 'build_xlsx.py');

  return new Promise((resolve, reject) => {
    const proc = spawn('python3', [pythonScript, tempDataPath, outputPath], {
      cwd: getBaseDir(),
    });

    let stderr = '';

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    proc.on('close', (code) => {
      if (code === 0) {
        logger.info('Python XLSX generator completed successfully');
        resolve();
      } else {
        logger.error('Python XLSX generator failed', { code, stderr });
        reject(new Error(`XLSX 生成失败 (exit code ${code}): ${stderr}`));
      }
    });

    proc.on('error', (err) => {
      logger.error('Failed to spawn Python process', { error: err.message });
      reject(new Error(`无法启动 Python 进程: ${err.message}`));
    });
  });
}
