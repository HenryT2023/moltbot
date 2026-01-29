/**
 * 本地文件数据适配器
 * 从 data/ 目录读取 CSV 文件并解析
 */

import { readFileSync } from 'node:fs';
import { parse as parseCsv } from 'csv-parse/sync';
import { listFiles } from '../../utils/io.js';
import { formatDate, type ResolvedTimeWindow } from '../../utils/time_window.js';
import type { Logger } from '../../utils/logger.js';

export interface RawRecord {
  date: string;
  metric_name: string;
  metric_value: number;
  source: string;
  [key: string]: string | number;
}

export async function fetchLocalFiles(
  dataDir: string,
  timeWindow: ResolvedTimeWindow,
  logger: Logger
): Promise<RawRecord[]> {
  const csvFiles = listFiles(dataDir, /\.csv$/i);

  if (csvFiles.length === 0) {
    logger.warn('No CSV files found in data directory', { dataDir });
    return [];
  }

  logger.info('Found CSV files', { count: csvFiles.length, files: csvFiles });

  const allRecords: RawRecord[] = [];
  const startStr = formatDate(timeWindow.start);
  const endStr = formatDate(timeWindow.end);
  const prevStartStr = formatDate(timeWindow.previousStart);

  for (const filePath of csvFiles) {
    try {
      const source = extractSource(filePath);
      const content = readFileSync(filePath, 'utf-8');

      const records = parseCsv(content, {
        columns: true,
        skip_empty_lines: true,
        trim: true,
      }) as Record<string, string>[];

      for (const record of records) {
        const date = record.date || record.Date || record.DATE;
        if (!date) {
          logger.warn('Record missing date field', { file: filePath, record });
          continue;
        }

        // 过滤时间范围（包含当前周期和上一周期用于环比）
        if (date < prevStartStr || date > endStr) {
          continue;
        }

        const metricName =
          record.metric_name ||
          record.metric ||
          record.Metric ||
          record.METRIC;
        const metricValue = parseFloat(
          record.metric_value ||
            record.value ||
            record.Value ||
            record.VALUE ||
            '0'
        );

        if (!metricName || isNaN(metricValue)) {
          logger.warn('Invalid record', { file: filePath, record });
          continue;
        }

        const rawRecord: RawRecord = {
          date,
          metric_name: metricName,
          metric_value: metricValue,
          source,
        };

        // 保留额外的维度字段
        for (const [key, value] of Object.entries(record)) {
          if (
            !['date', 'Date', 'DATE', 'metric_name', 'metric', 'Metric', 'METRIC', 'metric_value', 'value', 'Value', 'VALUE'].includes(key)
          ) {
            rawRecord[key] = value;
          }
        }

        allRecords.push(rawRecord);
      }

      logger.info('Parsed CSV file', {
        file: filePath,
        source,
        recordCount: records.length,
      });
    } catch (error) {
      logger.error('Failed to parse CSV file', {
        file: filePath,
        error: error instanceof Error ? error.message : String(error),
      });
      throw new Error(
        `解析文件失败: ${filePath} - ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  logger.info('Total records fetched', { count: allRecords.length });
  return allRecords;
}

function extractSource(filePath: string): string {
  const fileName = filePath.split('/').pop() || '';
  // sample_crm.csv -> crm
  // sample_ads.csv -> ads
  const match = fileName.match(/sample_(\w+)\.csv/i);
  if (match) {
    return match[1].toLowerCase();
  }
  // 默认使用文件名（去掉扩展名）
  return fileName.replace(/\.csv$/i, '').toLowerCase();
}
