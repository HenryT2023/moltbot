/**
 * 日志工具
 * 支持控制台输出和文件写入
 */

import { appendFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';

export interface Logger {
  info: (message: string, data?: Record<string, unknown>) => void;
  warn: (message: string, data?: Record<string, unknown>) => void;
  error: (message: string, data?: Record<string, unknown>) => void;
  debug: (message: string, data?: Record<string, unknown>) => void;
  setLogFile: (path: string) => void;
}

export function createLogger(): Logger {
  let logFilePath: string | null = null;

  function formatMessage(
    level: string,
    message: string,
    data?: Record<string, unknown>
  ): string {
    const timestamp = new Date().toISOString();
    const dataStr = data ? ` ${JSON.stringify(data)}` : '';
    return `[${timestamp}] [${level.toUpperCase()}] ${message}${dataStr}`;
  }

  function writeToFile(formatted: string) {
    if (logFilePath) {
      try {
        const dir = dirname(logFilePath);
        if (!existsSync(dir)) {
          mkdirSync(dir, { recursive: true });
        }
        appendFileSync(logFilePath, formatted + '\n');
      } catch {
        // 静默失败，避免日志写入错误影响主流程
      }
    }
  }

  return {
    info(message: string, data?: Record<string, unknown>) {
      const formatted = formatMessage('info', message, data);
      console.log(formatted);
      writeToFile(formatted);
    },

    warn(message: string, data?: Record<string, unknown>) {
      const formatted = formatMessage('warn', message, data);
      console.warn(formatted);
      writeToFile(formatted);
    },

    error(message: string, data?: Record<string, unknown>) {
      const formatted = formatMessage('error', message, data);
      console.error(formatted);
      writeToFile(formatted);
    },

    debug(message: string, data?: Record<string, unknown>) {
      if (process.env.DEBUG) {
        const formatted = formatMessage('debug', message, data);
        console.log(formatted);
        writeToFile(formatted);
      }
    },

    setLogFile(path: string) {
      logFilePath = path;
    },
  };
}
