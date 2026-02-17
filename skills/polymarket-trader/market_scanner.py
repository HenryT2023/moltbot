"""
Polymarket 活跃市场扫描器
使用 Gamma API 获取真正活跃的市场
"""

import random
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

import config

# ================= 配置 =================
# Polymarket Gamma API (公开 API，返回活跃市场)
GAMMA_API_URL = "https://gamma-api.polymarket.com"

# 代理配置
PROXIES = {
    'http': 'http://127.0.0.1:7890',
    'https': 'http://127.0.0.1:7890'
}

# 过滤参数
MIN_VOLUME = 1000        # 最小交易量 $1000
MIN_LIQUIDITY = 200      # 最小流动性 $200（捕获更多中型市场）
EXCLUDE_SPORTS = True    # 排除体育博彩

# 优先关注的市场分类 (信息差套利机会更高)
PRIORITY_TAGS = [
    "breaking-news",      # 突发新闻 - 最高优先级
    "new",                # 最新市场 - 价格还未稳定
    "politics",           # 政治
    "crypto",             # 加密货币
    "ai",                 # AI 相关
    "tech",               # 科技
    "economy",            # 经济
    "finance",            # 金融
    "entertainment",      # 娱乐
    "science",            # 科学
    "world",              # 国际
    "culture",            # 文化
]
# ========================================


def fetch_active_markets(limit: int = 100, offset: int = 0, tag: str = None) -> List[dict]:
    """
    从 Gamma API 获取活跃市场
    
    Args:
        limit: 返回数量限制
        offset: 偏移量
        tag: 可选的市场分类标签 (如 breaking-news, politics, crypto)
    """
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": limit,
        "offset": offset,
        "active": "true",
        "closed": "false"
    }
    
    if tag:
        params["tag"] = tag
    
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"⚠️ 请求失败，尝试不使用代理...")
        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as e2:
            print(f"❌ 获取市场失败: {e2}")
            return []


def fetch_breaking_news_markets(limit: int = 50) -> List[dict]:
    """
    专门获取 Breaking News 市场 - 信息差套利的最佳来源
    """
    print("🔥 获取 Breaking News 市场...")
    return fetch_active_markets(limit=limit, tag="breaking-news")


def fetch_newest_markets(limit: int = 50) -> List[dict]:
    """
    获取最新创建的市场 - 价格还未稳定，套利机会大
    按创建时间降序排列
    """
    print("🆕 获取最新市场...")
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": limit,
        "active": "true",
        "closed": "false",
        "order": "createdAt",
        "ascending": "false"
    }
    
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ 获取最新市场失败: {e}")
        return []


def fetch_by_liquidity(limit: int = 30) -> List[dict]:
    """
    按流动性排序获取市场 - 高流动性意味着更容易成交
    """
    print("💧 获取高流动性市场...")
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": limit,
        "active": "true",
        "closed": "false",
        "order": "liquidityNum",
        "ascending": "false"
    }
    
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ 获取高流动性市场失败: {e}")
        return []


def fetch_by_volume(limit: int = 30) -> List[dict]:
    """
    按总交易量排序获取市场 - 高交易量说明市场活跃
    """
    print("📊 获取高交易量市场...")
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": limit,
        "active": "true",
        "closed": "false",
        "order": "volumeNum",
        "ascending": "false"
    }
    
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ 获取高交易量市场失败: {e}")
        return []


def fetch_by_24h_volume(limit: int = 30) -> List[dict]:
    """
    按24小时交易量排序 - 当前最热门的市场
    """
    print("🔥 获取24小时热门市场...")
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": limit,
        "active": "true",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false"
    }
    
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ 获取24小时热门市场失败: {e}")
        return []


def fetch_ending_soon(limit: int = 30) -> List[dict]:
    """
    获取即将结束的市场 - 价格波动可能更大
    按结束日期升序排列
    """
    print("⏰ 获取即将结束市场...")
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": limit,
        "active": "true",
        "closed": "false",
        "order": "endDate",
        "ascending": "true"
    }
    
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ 获取即将结束市场失败: {e}")
        return []


def fetch_competitive(limit: int = 30) -> List[dict]:
    """
    获取竞争激烈的市场 - 价格接近50/50，不确定性高
    """
    print("⚔️ 获取竞争激烈市场...")
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": limit,
        "active": "true",
        "closed": "false",
        "order": "competitive",
        "ascending": "false"
    }
    
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ 获取竞争激烈市场失败: {e}")
        return []


def fetch_all_sorted_markets(limit_per_sort: int = 20) -> List[dict]:
    """
    获取所有排序方式的市场并合并去重
    优先级: Breaking News > 最新 > 24h热门 > 高流动性 > 即将结束 > 竞争激烈
    每次调用时对部分维度施加随机偏移，避免总看同一批市场
    """
    all_markets = []
    seen_ids = set()
    
    # 随机偏移：对流动性/交易量/竞争维度施加 0~80 的偏移，探索更多市场
    rand_offset = random.randint(0, 80)
    
    # 按优先级获取各类市场
    sources = [
        ("breaking-news", fetch_breaking_news_markets(limit_per_sort)),
        ("newest", fetch_newest_markets(limit_per_sort)),
        ("24h-volume", fetch_by_24h_volume(limit_per_sort)),
        ("liquidity", fetch_by_liquidity(limit_per_sort)),
        ("ending-soon", fetch_ending_soon(limit_per_sort)),
        ("competitive", fetch_competitive(limit_per_sort)),
        ("liquidity-deep", fetch_active_markets(limit=limit_per_sort, offset=rand_offset)),
        ("volume-deep", fetch_by_volume(limit_per_sort)),
    ]
    
    for source_name, markets in sources:
        for m in markets:
            market_id = m.get('id') or m.get('conditionId')
            if market_id and market_id not in seen_ids:
                seen_ids.add(market_id)
                m['_source'] = source_name
                all_markets.append(m)
    
    print(f"✅ 共获取 {len(all_markets)} 个市场 (多维度去重后)")
    return all_markets


def fetch_priority_markets(limit_per_tag: int = 30) -> List[dict]:
    """
    获取所有优先分类的市场
    按优先级顺序获取，去重后返回
    """
    all_markets = []
    seen_ids = set()
    
    for tag in PRIORITY_TAGS:
        print(f"📡 获取 [{tag}] 市场...")
        markets = fetch_active_markets(limit=limit_per_tag, tag=tag)
        
        for m in markets:
            market_id = m.get('id') or m.get('conditionId')
            if market_id and market_id not in seen_ids:
                seen_ids.add(market_id)
                m['_priority_tag'] = tag  # 标记来源分类
                all_markets.append(m)
    
    print(f"✅ 共获取 {len(all_markets)} 个优先市场 (去重后)")
    return all_markets


def fetch_market_by_slug(slug: str) -> Optional[dict]:
    """
    通过 slug 获取单个市场详情
    """
    url = f"{GAMMA_API_URL}/markets/{slug}"
    
    try:
        resp = requests.get(url, proxies=PROXIES, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"❌ 获取市场详情失败: {e}")
        return None


def filter_markets(markets: List[dict]) -> List[dict]:
    """
    应用新鲜度过滤器
    Gamma API 字段名：
    - active, closed, acceptingOrders
    - volumeNum, liquidityNum
    - endDateIso, endDate
    """
    filtered = []
    now = datetime.now(timezone.utc)
    
    for m in markets:
        # 1. 必须是活跃状态
        if not m.get('active', False):
            continue
        
        # 2. 必须未关闭
        if m.get('closed', True):
            continue
        
        # 3. 必须接受订单
        if not m.get('acceptingOrders', False):
            continue
        
        # 4. 检查结束日期 (必须在未来)
        end_date_str = m.get('endDate') or m.get('endDateIso')
        if end_date_str:
            try:
                # 处理不同格式
                if 'T' in end_date_str:
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                else:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                if end_date < now:
                    continue
            except:
                pass
        
        # 5. 检查交易量 (使用 volumeNum 或 volume)
        volume = float(m.get('volumeNum', 0) or m.get('volume', 0) or 0)
        if volume < MIN_VOLUME:
            continue
        
        # 6. 检查流动性 (使用 liquidityNum 或 liquidity)
        liquidity = float(m.get('liquidityNum', 0) or m.get('liquidity', 0) or 0)
        if liquidity < MIN_LIQUIDITY:
            continue
        
        # 7. 排除体育博彩 (可选)
        if EXCLUDE_SPORTS:
            question = m.get('question', '').lower()
            tags = m.get('tags', []) or []
            
            sports_keywords = ['nba', 'nfl', 'mlb', 'nhl', 'ncaa', 'soccer', 
                             'football', 'basketball', 'baseball', 'hockey',
                             'tennis', 'golf', 'ufc', 'boxing', 'f1', 'nascar',
                             'premier league', 'la liga', 'bundesliga']
            
            is_sports = any(kw in question for kw in sports_keywords)
            is_sports = is_sports or any('sport' in str(t).lower() for t in tags)
            
            if is_sports:
                continue
        
        filtered.append(m)
    
    return filtered


def get_market_prices(market: dict) -> Dict[str, float]:
    """
    获取市场价格
    Gamma API 返回的 outcomePrices 可能是字符串数组或 JSON 字符串
    outcomes 可能是 ["Yes", "No"] 或 JSON 字符串
    """
    import json
    
    outcomes = market.get('outcomes', [])
    prices = market.get('outcomePrices', [])
    
    # 处理 JSON 字符串格式
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except:
            outcomes = []
    
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except:
            prices = []
    
    result = {}
    
    # 如果有 outcomes，按 outcomes 映射
    if outcomes and prices:
        for i, outcome in enumerate(outcomes):
            if i < len(prices):
                try:
                    result[outcome] = float(prices[i])
                except:
                    result[outcome] = 0.5
    
    # 如果没有 outcomes 但有 prices，假设是 [Yes, No] 顺序
    if not result and prices and len(prices) >= 2:
        try:
            result['Yes'] = float(prices[0])
            result['No'] = float(prices[1])
        except:
            pass
    
    # 如果还是没有，尝试从其他字段获取
    if not result:
        best_bid = market.get('bestBid')
        best_ask = market.get('bestAsk')
        if best_bid is not None:
            result['Yes'] = float(best_bid)
            result['No'] = 1.0 - float(best_bid)
        elif best_ask is not None:
            result['Yes'] = float(best_ask)
            result['No'] = 1.0 - float(best_ask)
    
    return result


def scan_opportunities(markets: List[dict]) -> List[dict]:
    """
    扫描套利机会
    """
    opportunities = []
    
    for m in markets:
        prices = get_market_prices(m)
        
        if len(prices) >= 2:
            yes_price = prices.get('Yes', 0.5)
            no_price = prices.get('No', 0.5)
            
            # 检查套利机会 (Yes + No < 1)
            total = yes_price + no_price
            if total < 0.98:
                edge = 1.0 - total
                opportunities.append({
                    'type': 'ARBITRAGE',
                    'market': m,
                    'question': m.get('question', ''),
                    'yes_price': yes_price,
                    'no_price': no_price,
                    'edge': edge
                })
            
            # 检查清洁工机会 (No 价格 > 0.94)
            if no_price >= 0.94:
                edge = 1.0 - no_price
                opportunities.append({
                    'type': 'CLEANER',
                    'market': m,
                    'question': m.get('question', ''),
                    'no_price': no_price,
                    'edge': edge
                })
    
    return opportunities


def print_market_summary(markets: List[dict]):
    """
    打印市场摘要
    """
    print(f"\n{'='*60}")
    print(f"📊 活跃市场扫描结果")
    print(f"{'='*60}")
    print(f"   总计: {len(markets)} 个活跃市场")
    print(f"   过滤条件: 交易量>${MIN_VOLUME}, 流动性>${MIN_LIQUIDITY}")
    print(f"   排除体育: {'是' if EXCLUDE_SPORTS else '否'}")
    print(f"{'='*60}\n")
    
    for i, m in enumerate(markets[:10], 1):
        question = m.get('question', '')[:50]
        volume = float(m.get('volume', 0) or m.get('volumeNum', 0) or 0)
        liquidity = float(m.get('liquidity', 0) or m.get('liquidityNum', 0) or 0)
        end_date = m.get('endDate', m.get('end_date_iso', 'N/A'))[:10]
        
        prices = get_market_prices(m)
        yes_price = prices.get('Yes', 0)
        no_price = prices.get('No', 0)
        
        print(f"[{i}] {question}...")
        print(f"    结束: {end_date} | Vol: ${volume:,.0f} | Liq: ${liquidity:,.0f}")
        print(f"    Yes: ${yes_price:.2f} | No: ${no_price:.2f}")
        print()


def fetch_clob_markets(client, max_pages: int = 3, sports_filter: bool = True) -> List[dict]:
    """
    CLOB-First 市场发现：从 Polymarket CLOB API 获取所有活跃市场
    
    优势：
    - 一次获取 1000 个市场（vs Gamma 的 ~50 个去重后）
    - 每个市场自带 tokens[].price 中间价，无需额外 order book 调用
    - 覆盖 3100+ 市场 vs Gamma 的 ~100 个
    
    返回的市场格式与 Gamma 兼容（添加必要字段映射）
    """
    all_markets = []
    seen_ids = set()
    cursor = None
    
    sports_keywords = ['nba', 'nfl', 'mlb', 'nhl', 'ncaa', 'soccer', 
                       'football', 'basketball', 'baseball', 'hockey',
                       'tennis', 'golf', 'ufc', 'boxing', 'f1', 'nascar',
                       'premier league', 'la liga', 'bundesliga',
                       'serie a', 'ligue 1', 'mls', 'epl',
                       'bucks', 'lakers', 'celtics', 'warriors', 'nuggets',
                       'chiefs', 'eagles', 'cowboys', 'ravens', '49ers',
                       'mavericks', 'trail blazers', 'jazz', 'thunder',
                       'fluminense', 'palmeiras', 'corinthians']
    
    for page in range(max_pages):
        try:
            if cursor:
                sm = client.get_sampling_markets(next_cursor=cursor)
            else:
                sm = client.get_sampling_markets()
            
            data = sm.get('data', [])
            if not data:
                break
            
            for m in data:
                cid = m.get('condition_id', '')
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                
                # 基本过滤
                if not m.get('active') or m.get('closed') or not m.get('accepting_orders'):
                    continue
                
                tokens = m.get('tokens', [])
                if len(tokens) != 2:
                    continue
                
                # 体育过滤
                if sports_filter:
                    q_lower = m.get('question', '').lower()
                    tags = [str(t).lower() for t in (m.get('tags', []) or [])]
                    is_sport = any(kw in q_lower for kw in sports_keywords)
                    is_sport = is_sport or any('sport' in t for t in tags)
                    if is_sport:
                        continue
                
                # 转换为兼容 Gamma 格式（polymarket_cron.py 依赖这些字段）
                yes_tok = tokens[0]
                no_tok = tokens[1]
                yes_price = float(yes_tok.get('price', 0.5))
                no_price = float(no_tok.get('price', 0.5))
                
                compatible = {
                    # Gamma 兼容字段
                    'id': cid,
                    'conditionId': cid,
                    'question': m.get('question', ''),
                    'description': m.get('description', ''),
                    'active': True,
                    'closed': False,
                    'acceptingOrders': True,
                    'endDate': m.get('end_date_iso', ''),
                    'endDateIso': m.get('end_date_iso', ''),
                    'clobTokenIds': [yes_tok['token_id'], no_tok['token_id']],
                    'outcomePrices': [str(yes_price), str(no_price)],
                    'outcomes': ['Yes', 'No'],
                    'tokens': tokens,
                    'tags': m.get('tags', []),
                    'neg_risk': m.get('neg_risk', False),
                    # 额外 CLOB 元数据
                    '_source': 'clob',
                    '_yes_mid': yes_price,
                    '_no_mid': no_price,
                    'market_slug': m.get('market_slug', ''),
                }
                all_markets.append(compatible)
            
            cursor = sm.get('next_cursor')
            if not cursor or cursor == 'LTE=':
                break
                
        except Exception as e:
            print(f"   ⚠️ CLOB 第{page+1}页获取失败: {e}")
            break
    
    print(f"   📡 CLOB 扫描: {len(all_markets)} 个活跃非体育市场 (共 {len(seen_ids)} 个)")
    return all_markets


def filter_clob_markets(markets: List[dict], 
                        min_yes: float = 0.03, 
                        max_yes: float = 0.97) -> List[dict]:
    """
    过滤 CLOB 市场：去掉已基本确定结果的极端市场
    保留中间价在 [min_yes, max_yes] 范围内的市场
    """
    filtered = []
    for m in markets:
        yes_mid = m.get('_yes_mid', 0.5)
        if min_yes <= yes_mid <= max_yes:
            filtered.append(m)
    return filtered


# ================= 主程序 =================
if __name__ == "__main__":
    print("🔍 正在扫描 Polymarket 活跃市场...")
    
    # 获取市场
    raw_markets = fetch_active_markets(limit=200)
    print(f"📥 原始数据: {len(raw_markets)} 个市场")
    
    # 过滤
    active_markets = filter_markets(raw_markets)
    print(f"✅ 过滤后: {len(active_markets)} 个活跃市场")
    
    # 打印摘要
    print_market_summary(active_markets)
    
    # 扫描机会
    opportunities = scan_opportunities(active_markets)
    
    if opportunities:
        print(f"\n{'='*60}")
        print(f"💰 发现 {len(opportunities)} 个潜在机会")
        print(f"{'='*60}")
        
        for opp in opportunities[:5]:
            print(f"\n[{opp['type']}] {opp['question'][:40]}...")
            print(f"   Edge: {opp['edge']:.2%}")
    else:
        print("\n⏸️ 暂无明显套利机会")
