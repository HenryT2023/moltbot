/**
 * 时间窗口解析与计算工具
 */

import {
  subDays,
  startOfWeek,
  endOfWeek,
  startOfMonth,
  endOfMonth,
  format,
  parse,
  isValid,
  subWeeks,
} from 'date-fns';

export type TimeWindowPreset =
  | 'yesterday'
  | 'last_7_days'
  | 'last_week'
  | 'this_month';

export interface TimeWindowCustom {
  start: string; // YYYY-MM-DD
  end: string; // YYYY-MM-DD
}

export type TimeWindow = TimeWindowPreset | TimeWindowCustom;

export interface ResolvedTimeWindow {
  start: Date;
  end: Date;
  label: string;
  previousStart: Date;
  previousEnd: Date;
}

export function parseTimeWindow(input: string): TimeWindow {
  const presets: TimeWindowPreset[] = [
    'yesterday',
    'last_7_days',
    'last_week',
    'this_month',
  ];

  if (presets.includes(input as TimeWindowPreset)) {
    return input as TimeWindowPreset;
  }

  // 尝试解析自定义格式: YYYY-MM-DD:YYYY-MM-DD
  if (input.includes(':')) {
    const [start, end] = input.split(':');
    const startDate = parse(start, 'yyyy-MM-dd', new Date());
    const endDate = parse(end, 'yyyy-MM-dd', new Date());

    if (isValid(startDate) && isValid(endDate)) {
      return { start, end };
    }
  }

  throw new Error(
    `无效的时间窗口: ${input}。支持: yesterday, last_7_days, last_week, this_month, 或 YYYY-MM-DD:YYYY-MM-DD`
  );
}

export function resolveTimeWindow(window: TimeWindow): ResolvedTimeWindow {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  let start: Date;
  let end: Date;
  let label: string;

  if (typeof window === 'string') {
    switch (window) {
      case 'yesterday': {
        start = subDays(today, 1);
        end = subDays(today, 1);
        label = '昨日';
        break;
      }
      case 'last_7_days': {
        start = subDays(today, 7);
        end = subDays(today, 1);
        label = '近7天';
        break;
      }
      case 'last_week': {
        const lastWeekStart = startOfWeek(subWeeks(today, 1), {
          weekStartsOn: 1,
        });
        start = lastWeekStart;
        end = endOfWeek(lastWeekStart, { weekStartsOn: 1 });
        label = '上周';
        break;
      }
      case 'this_month': {
        start = startOfMonth(today);
        end = subDays(today, 1);
        label = '本月';
        break;
      }
      default:
        throw new Error(`未知的时间窗口预设: ${window}`);
    }
  } else {
    start = parse(window.start, 'yyyy-MM-dd', new Date());
    end = parse(window.end, 'yyyy-MM-dd', new Date());
    label = `${window.start} 至 ${window.end}`;
  }

  // 计算环比时间段（上一个同等长度的时间段）
  const duration = end.getTime() - start.getTime();
  const previousEnd = subDays(start, 1);
  const previousStart = new Date(previousEnd.getTime() - duration);

  return {
    start,
    end,
    label,
    previousStart,
    previousEnd,
  };
}

export function formatDate(date: Date): string {
  return format(date, 'yyyy-MM-dd');
}

export function formatDateRange(start: Date, end: Date): string {
  return `${formatDate(start)} ~ ${formatDate(end)}`;
}
