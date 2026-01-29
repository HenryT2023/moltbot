/**
 * Slack 通知模块
 * 发送报表摘要和附件到 Slack 频道
 */

import { WebClient } from '@slack/web-api';
import { readFileSync, existsSync } from 'node:fs';
import type { Logger } from '../../utils/logger.js';

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

export async function sendSlackNotification(
  channel: string,
  message: string,
  attachmentPath: string | undefined,
  mentions: string[] | undefined,
  logger: Logger
): Promise<boolean> {
  // 检查 allowlist
  const allowlist = process.env.KPI_REPORTER_SLACK_ALLOWLIST;
  if (allowlist) {
    const allowed = allowlist.split(',').map((c) => c.trim().toLowerCase());
    if (!allowed.includes(channel.toLowerCase())) {
      logger.error('Channel not in allowlist', { channel, allowlist });
      throw new Error(
        `频道 ${channel} 不在允许列表中。允许的频道: ${allowlist}`
      );
    }
  }

  // 获取 Slack token
  const token = process.env.SLACK_BOT_TOKEN;
  if (!token) {
    logger.error('SLACK_BOT_TOKEN not set');
    throw new Error('未配置 SLACK_BOT_TOKEN 环境变量');
  }

  const client = new WebClient(token);

  // 构建消息
  let finalMessage = message;
  if (mentions && mentions.length > 0) {
    const mentionStr = mentions.join(' ');
    finalMessage = `${mentionStr}\n\n${message}`;
  }

  // 重试逻辑
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      // 发送消息
      const result = await client.chat.postMessage({
        channel,
        text: finalMessage,
        mrkdwn: true,
      });

      if (!result.ok) {
        throw new Error(`Slack API 返回错误: ${result.error}`);
      }

      logger.info('Slack message sent', {
        channel,
        ts: result.ts,
      });

      // 上传附件
      if (attachmentPath && existsSync(attachmentPath)) {
        const fileContent = readFileSync(attachmentPath);
        const fileName = attachmentPath.split('/').pop() || 'report.xlsx';

        // @ts-expect-error - Slack SDK 类型定义对 thread_ts 过于严格
        const uploadResult = await client.files.uploadV2({
          channel_id: channel,
          file: fileContent,
          filename: fileName,
          title: 'KPI 报表',
          thread_ts: result.ts,
        });

        if (!uploadResult.ok) {
          logger.warn('Failed to upload attachment', {
            error: uploadResult.error,
          });
        } else {
          logger.info('Attachment uploaded', { fileName });
        }
      }

      return true;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);

      if (attempt < MAX_RETRIES) {
        logger.warn('Slack send failed, retrying', {
          attempt,
          error: errorMessage,
        });
        await sleep(RETRY_DELAY_MS * Math.pow(2, attempt - 1));
      } else {
        logger.error('Slack send failed after all retries', {
          error: errorMessage,
        });
        throw new Error(`Slack 发送失败: ${errorMessage}`);
      }
    }
  }

  return false;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
