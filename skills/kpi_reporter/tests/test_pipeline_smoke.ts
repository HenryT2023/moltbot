/**
 * KPI Reporter 冒烟测试
 * 验证完整管线能够正常运行
 */

import { join } from 'node:path';
import { existsSync, rmSync } from 'node:fs';
import { runPipeline } from '../src/pipeline/run_pipeline.js';
import { createLogger } from '../src/utils/logger.js';
import { getRunsDir, getBaseDir, readJson } from '../src/utils/io.js';

async function runSmokeTest() {
  console.log('🧪 KPI Reporter 冒烟测试\n');

  const logger = createLogger();
  // 使用样例数据的日期范围（2024-01-08 ~ 2024-01-21）
  const testCases = [
    {
      name: 'custom_range_7_days',
      time_window: { start: '2024-01-15', end: '2024-01-21' },
    },
    {
      name: 'custom_range_full',
      time_window: { start: '2024-01-08', end: '2024-01-21' },
    },
  ];

  let passed = 0;
  let failed = 0;

  for (const testCase of testCases) {
    console.log(`\n📋 测试: ${testCase.name}`);
    console.log('─'.repeat(40));

    try {
      const result = await runPipeline(
        {
          time_window: testCase.time_window,
          datasource: 'local_files',
          output: {
            xlsx: true,
            html: false,
            slack: false, // 不实际发送 Slack
          },
          dry_run: true,
        },
        logger
      );

      if (!result.success) {
        throw new Error(result.error || '未知错误');
      }

      // 验证产物
      const runDir = join(getRunsDir(), result.runId);

      // 检查 meta.json
      const metaPath = join(runDir, 'meta.json');
      if (!existsSync(metaPath)) {
        throw new Error('meta.json 不存在');
      }
      const meta = readJson<{ success: boolean }>(metaPath);
      if (!meta.success) {
        throw new Error('meta.json 显示运行失败');
      }

      // 检查 report.xlsx
      const reportPath = join(runDir, 'report.xlsx');
      if (!existsSync(reportPath)) {
        throw new Error('report.xlsx 不存在');
      }

      // 检查 run.log
      const logPath = join(runDir, 'run.log');
      if (!existsSync(logPath)) {
        throw new Error('run.log 不存在');
      }

      // 检查 raw 数据
      const rawPath = join(runDir, 'raw', 'raw_data.json');
      if (!existsSync(rawPath)) {
        throw new Error('raw_data.json 不存在');
      }

      // 检查 processed 数据
      const processedPath = join(runDir, 'processed', 'data.json');
      if (!existsSync(processedPath)) {
        throw new Error('processed/data.json 不存在');
      }

      // 检查 slack_message.txt
      const slackPath = join(runDir, 'slack_message.txt');
      if (!existsSync(slackPath)) {
        throw new Error('slack_message.txt 不存在');
      }

      console.log(`✅ 通过 - Run ID: ${result.runId}`);
      console.log(`   报表: ${result.reportPath}`);
      passed++;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      console.log(`❌ 失败: ${errorMessage}`);
      failed++;
    }
  }

  // 汇总
  console.log('\n' + '═'.repeat(40));
  console.log(`📊 测试结果: ${passed} 通过, ${failed} 失败`);

  if (failed > 0) {
    process.exit(1);
  }

  console.log('\n✅ 所有测试通过！');
}

// 运行测试
runSmokeTest().catch((error) => {
  console.error('测试运行失败:', error);
  process.exit(1);
});
