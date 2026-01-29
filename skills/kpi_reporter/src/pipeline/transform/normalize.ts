/**
 * 数据标准化模块
 * 将不同来源的数据转换为统一的标准 schema
 */

import type { RawRecord } from '../adapters/local_files.js';

export interface StandardRecord {
  date: string; // YYYY-MM-DD
  source: string; // crm, ads, web, orders
  metric: string; // 指标名
  value: number; // 指标值
  dims: Record<string, string>; // 可选维度
}

export function normalizeData(rawRecords: RawRecord[]): StandardRecord[] {
  return rawRecords.map((raw) => {
    const dims: Record<string, string> = {};

    // 提取维度字段
    for (const [key, value] of Object.entries(raw)) {
      if (
        !['date', 'metric_name', 'metric_value', 'source'].includes(key) &&
        typeof value === 'string' &&
        value.trim() !== ''
      ) {
        dims[key] = value;
      }
    }

    return {
      date: raw.date,
      source: raw.source,
      metric: raw.metric_name.toLowerCase(),
      value: raw.metric_value,
      dims,
    };
  });
}

export function filterByDateRange(
  records: StandardRecord[],
  startDate: string,
  endDate: string
): StandardRecord[] {
  return records.filter((r) => r.date >= startDate && r.date <= endDate);
}

export function groupBySource(
  records: StandardRecord[]
): Map<string, StandardRecord[]> {
  const groups = new Map<string, StandardRecord[]>();

  for (const record of records) {
    const existing = groups.get(record.source) || [];
    existing.push(record);
    groups.set(record.source, existing);
  }

  return groups;
}

export function groupByMetric(
  records: StandardRecord[]
): Map<string, StandardRecord[]> {
  const groups = new Map<string, StandardRecord[]>();

  for (const record of records) {
    const existing = groups.get(record.metric) || [];
    existing.push(record);
    groups.set(record.metric, existing);
  }

  return groups;
}

export function aggregateByDate(
  records: StandardRecord[]
): Map<string, number> {
  const result = new Map<string, number>();

  for (const record of records) {
    const current = result.get(record.date) || 0;
    result.set(record.date, current + record.value);
  }

  return result;
}
