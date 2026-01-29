import { setGlobalDispatcher, ProxyAgent } from 'undici';

// 设置全局代理
const proxyUrl = process.env.HTTPS_PROXY || process.env.https_proxy || 'http://127.0.0.1:7890';
setGlobalDispatcher(new ProxyAgent(proxyUrl));

console.log(`[proxy] Using proxy: ${proxyUrl}`);

// 动态导入主入口
await import('./scripts/run-node.mjs');
