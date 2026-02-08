import { setGlobalDispatcher, ProxyAgent } from 'undici';

// 设置全局代理 - 必须在任何 fetch 调用之前
const proxyUrl = process.env.HTTPS_PROXY || process.env.https_proxy || 'http://127.0.0.1:7890';
setGlobalDispatcher(new ProxyAgent(proxyUrl));

// 设置 Polymarket 环境变量
process.env.POLYMARKET_KEY = process.env.POLYMARKET_KEY || '0x304a4bc8c75a268b7518960eb991ec679960b0134917a39f158ee9d12d80c862';

console.log(`[proxy] Using proxy: ${proxyUrl}`);
console.log(`[polymarket] POLYMARKET_KEY configured`);

// 直接导入编译后的入口文件，这样代理设置会在同一进程中生效
await import('./dist/entry.js');
