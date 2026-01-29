/**
 * KPI 计算模块
 * 根据 kpis.yaml 配置计算各项指标
 */

import { readYaml } from '../../utils/io.js';
import { formatDate, type ResolvedTimeWindow } from '../../utils/time_window.js';
import type { StandardRecord } from './normalize.js';
import { filterByDateRange } from './normalize.js';
import type { Logger } from '../../utils/logger.js';

export interface KpiConfig {
  kpis: KpiDefinition[];
  comparison?: {
    enabled: boolean;
    type: string;
  };
}

export interface KpiDefinition {
  name: string;
  expr: 'sum' | 'count' | 'avg' | 'ratio';
  filter?: {
    metric?: string;
    source?: string;
  };
  numerator?: string; // for ratio
  denominator?: string; // for ratio
  description?: string;
}

export interface KpiResult {
  name: string;
  value: number;
  description?: string;
}

export async function computeKpis(
  data: StandardRecord[],
  configPath: string,
  timeWindow: ResolvedTimeWindow,
  logger: Logger
): Promise<{ current: KpiResult[]; previous: KpiResult[] }> {
  const config = readYaml<KpiConfig>(configPath);

  const currentStart = formatDate(timeWindow.start);
  const currentEnd = formatDate(timeWindow.end);
  const previousStart = formatDate(timeWindow.previousStart);
  const previousEnd = formatDate(timeWindow.previousEnd);

  const currentData = filterByDateRange(data, currentStart, currentEnd);
  const previousData = filterByDateRange(data, previousStart, previousEnd);

  logger.info('Computing KPIs for periods', {
    current: `${currentStart} ~ ${currentEnd}`,
    previous: `${previousStart} ~ ${previousEnd}`,
    currentCount: currentData.length,
    previousCount: previousData.length,
  });

  const currentResults = computeKpisForPeriod(config.kpis, currentData, logger);
  const previousResults = computeKpisForPeriod(
    config.kpis,
    previousData,
    logger
  );

  return {
    current: currentResults,
    previous: previousResults,
  };
}

function computeKpisForPeriod(
  kpiDefs: KpiDefinition[],
  data: StandardRecord[],
  logger: Logger
): KpiResult[] {
  const results: KpiResult[] = [];
  const computedValues = new Map<string, number>();

  // 第一遍：计算基础指标（非 ratio）
  for (const def of kpiDefs) {
    if (def.expr === 'ratio') {
      continue;
    }

    const value = computeSingleKpi(def, data);
    computedValues.set(def.name, value);

    results.push({
      name: def.name,
      value,
      description: def.description,
    });
  }

  // 第二遍：计算 ratio 指标
  for (const def of kpiDefs) {
    if (def.expr !== 'ratio') {
      continue;
    }

    const numerator = computedValues.get(def.numerator || '') || 0;
    const denominator = computedValues.get(def.denominator || '') || 0;

    const value = denominator !== 0 ? numerator / denominator : 0;
    computedValues.set(def.name, value);

    results.push({
      name: def.name,
      value,
      description: def.description,
    });
  }

  return results;
}

function computeSingleKpi(def: KpiDefinition, data: StandardRecord[]): number {
  // 过滤数据
  let filtered = data;

  if (def.filter?.metric) {
    filtered = filtered.filter((r) => r.metric === def.filter!.metric);
  }

  if (def.filter?.source) {
    filtered = filtered.filter((r) => r.source === def.filter!.source);
  }

  if (filtered.length === 0) {
    return 0;
  }

  switch (def.expr) {
    case 'sum':
      return filtered.reduce((acc, r) => acc + r.value, 0);

    case 'count':
      return filtered.length;

    case 'avg':
      return filtered.reduce((acc, r) => acc + r.value, 0) / filtered.length;

    default:
      return 0;
  }
}

export function computeChange(
  current: number,
  previous: number
): { absolute: number; percentage: number } {
  const absolute = current - previous;
  const percentage = previous !== 0 ? (absolute / previous) * 100 : 0;

  return { absolute, percentage };
}
