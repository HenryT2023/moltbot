/**
 * KPI Reporter - Moltbot Skill 入口
 * 解析参数并调用报表生成管线
 */

import { parseArgs } from 'node:util';
import { runPipeline } from './pipeline/run_pipeline.js';
import { parseTimeWindow, type TimeWindow } from './utils/time_window.js';
import { createLogger } from './utils/logger.js';

export interface KpiReporterArgs {
  time_window: TimeWindow;
  datasource: string;
  output: {
    xlsx: boolean;
    html: boolean;
    slack: boolean;
  };
  slack?: {
    channel: string;
    mention?: string[];
    thread_ts?: string;
  };
  dry_run: boolean;
}

const defaultArgs: KpiReporterArgs = {
  time_window: 'yesterday',
  datasource: 'local_files',
  output: {
    xlsx: true,
    html: false,
    slack: true,
  },
  dry_run: false,
};

async function main() {
  const { values } = parseArgs({
    options: {
      time_window: { type: 'string', short: 't', default: 'yesterday' },
      datasource: { type: 'string', short: 'd', default: 'local_files' },
      slack_channel: { type: 'string', short: 'c' },
      slack_mention: { type: 'string', short: 'm' },
      dry_run: { type: 'boolean', default: false },
      no_slack: { type: 'boolean', default: false },
      help: { type: 'boolean', short: 'h', default: false },
    },
  });

  if (values.help) {
    console.log(`
KPI Reporter - 自动化 KPI 报表生成工具

用法:
  npx tsx src/index.ts [选项]

选项:
  -t, --time_window <window>   时间窗口: yesterday, last_7_days, last_week, this_month
                               或自定义格式: 2024-01-01:2024-01-15
  -d, --datasource <source>    数据源 (默认: local_files)
  -c, --slack_channel <chan>   Slack 频道 (如: #growth)
  -m, --slack_mention <users>  @提醒用户 (逗号分隔)
  --dry_run                    试运行模式，不实际发送
  --no_slack                   不发送 Slack 消息
  -h, --help                   显示帮助信息

示例:
  npx tsx src/index.ts --time_window yesterday --slack_channel "#growth"
  npx tsx src/index.ts -t last_week --dry_run
  npx tsx src/index.ts -t 2024-01-01:2024-01-15 -c "#ops" -m "@peter,@alice"
`);
    process.exit(0);
  }

  const logger = createLogger();

  try {
    const timeWindow = parseTimeWindow(values.time_window as string);

    const args: KpiReporterArgs = {
      ...defaultArgs,
      time_window: timeWindow,
      datasource: values.datasource as string,
      output: {
        xlsx: true,
        html: false,
        slack: !values.no_slack,
      },
      dry_run: values.dry_run ?? false,
    };

    if (values.slack_channel) {
      args.slack = {
        channel: values.slack_channel as string,
        mention: values.slack_mention
          ? (values.slack_mention as string).split(',').map((s) => s.trim())
          : undefined,
      };
    }

    logger.info('Starting KPI Reporter', { args });

    const result = await runPipeline(args, logger);

    if (result.success) {
      logger.info('Pipeline completed successfully', {
        runId: result.runId,
        reportPath: result.reportPath,
      });
      console.log(`\n✅ 报表生成成功！`);
      console.log(`   Run ID: ${result.runId}`);
      console.log(`   报表路径: ${result.reportPath}`);
      if (result.slackSent) {
        console.log(`   Slack 已发送到: ${args.slack?.channel}`);
      }
    } else {
      logger.error('Pipeline failed', { error: result.error });
      console.error(`\n❌ 报表生成失败: ${result.error}`);
      process.exit(1);
    }
  } catch (error) {
    logger.error('Unexpected error', { error });
    console.error('❌ 发生错误:', error);
    process.exit(1);
  }
}

// Moltbot skill 导出接口
export async function run(args: Partial<KpiReporterArgs>) {
  const logger = createLogger();
  const fullArgs: KpiReporterArgs = {
    ...defaultArgs,
    ...args,
    output: { ...defaultArgs.output, ...args.output },
  };

  return runPipeline(fullArgs, logger);
}

// CLI 入口
main().catch(console.error);
