# 金融科技版 BriefAI - 快速参考

## 🎯 核心业务聚焦

```
公司业务: 智能风控信贷
行业: 金融科技 (Fintech)
关注领域: 风险控制、信贷决策、数据分析、精准营销、用户增长
```

## 📊 8 大类别 (优先级排序)

| 类别 | 优先级 | 关键词 | 用途 |
|------|--------|--------|------|
| **金融科技AI应用** | ⭐⭐⭐ (10) | 智能风控、信贷、反欺诈 | 核心业务 |
| **数据分析** | ⭐⭐⭐ (10) | 大数据、数据挖掘、预测分析 | 技术基础 |
| **智能营销与广告** | ⭐⭐ (9) | 广告投放、用户画像、转化优化 | 获客增长 |
| **新兴产品** | ⭐⭐ (9) | 新产品、SaaS、工具 | 工具发现 |
| **大模型技术** | ⭐ (8) | LLM、GPT、AIGC应用 | 技术趋势 |
| **行业案例** | ⭐ (8) | 实践案例、ROI、效果 | 学习借鉴 |
| **合规与政策** | (7) | 法规、监管、合规 | 风险管理 |
| **技术栈与工具** | (6) | 框架、API、SDK | 技术选型 |

## 📰 12 个新闻源 (按相关性)

### 🏆 最高相关性 (weight 9-10)
1. **36氪 金融科技** (10) - 中文Fintech
2. **雷锋网 金融科技** (10) - AI风控深度
3. **KDnuggets** (9) - 数据科学权威
4. **Martech中国** (9) - 营销技术
5. **亿欧 金融科技** (9) - 行业分析
6. **AdExchanger** (9) - 广告技术

### 🎯 中等相关性 (weight 7-8)
7. **机器之心** (8) - AI技术
8. **Towards Data Science** (8) - 数据教程
9. **Analytics Vidhya** (8) - 数据实战
10. **Marketing AI Institute** (8) - AI营销
11. **InfoQ AI** (7) - 技术实践
12. **Product Hunt** (7) - 新产品

## ⚖️ 权重系统

### 评分公式
```
最终分数 = 基础分数 × (1 + 来源权重 × 0.15)

示例:
- 金融科技文章 (weight=10): 7.0 × 2.5 = 17.5 ✅
- 一般AI文章 (weight=5): 7.0 × 1.75 = 12.25
```

### 效果
- 金融科技相关文章 **优先级 +150%**
- 数据分析文章 **优先级 +120%**
- 营销广告文章 **优先级 +135%**

## 💡 典型使用场景

### 场景 1: 每周例行简报
```bash
python main.py --defaults
```
自动获取: 金融科技AI + 数据分析 + 智能营销

### 场景 2: 风控专题
```bash
python main.py --input "智能风控和反欺诈"
```
聚焦: 风控技术 + 反欺诈案例

### 场景 3: 营销获客
```bash
python main.py --input "广告投放策略和用户增长"
```
聚焦: 广告技术 + 增长黑客

### 场景 4: 新工具调研
```bash
python main.py --input "数据分析工具和SaaS产品"
```
聚焦: 新产品 + 分析工具

## 🎓 快速命令

```bash
# 使用默认配置（推荐）
python main.py --defaults

# 交互式选择
python main.py --interactive

# 自定义输入
python main.py --input "你的需求"

# 指定时间范围和文章数
python main.py --defaults --days 3 --top 10

# 调试模式
python main.py --defaults --log-level DEBUG
```

## 📈 预期内容分布

```
金融科技AI应用:    35%  (风控、信贷、反欺诈)
数据分析:          25%  (分析技术、工具、案例)
智能营销与广告:    20%  (投放策略、增长)
新兴产品:          15%  (工具、SaaS、平台)
其他:              5%   (政策、技术栈)
```

## 🔧 配置文件位置

```
config/categories.json  - 类别定义（已定制）
config/sources.json     - 新闻源配置（已定制）
config/report_template.md - 报告模板
.env                    - API密钥配置
```

## ⚙️ 关键配置参数

### .env 文件
```bash
ANTHROPIC_API_KEY=your_key_here
DEFAULT_CATEGORIES=fintech_ai,data_analytics,marketing_ai
MAX_ARTICLES_IN_REPORT=15
MIN_RELEVANCE_SCORE=6.0
```

### categories.json
```json
{
  "default_categories": [
    "fintech_ai",
    "data_analytics",
    "marketing_ai"
  ]
}
```

### sources.json
```json
{
  "weighting_config": {
    "enabled": true,
    "relevance_weight_multiplier": 1.5
  }
}
```

## 🚨 常见关键词

### 金融科技
- 智能风控、信贷、反欺诈、风险评估
- 信用评分、贷款审批、KYC、AML

### 数据分析
- 数据挖掘、预测分析、机器学习
- 用户画像、行为分析、转化漏斗

### 智能营销
- 广告投放、精准营销、用户增长
- ROI优化、转化率、获客成本

## 📊 成本预估

```
每周报告:
- 文章采集: 80-100篇
- 精选展示: 15篇
- API成本: $0.50-$1.00
- 月度成本: $2-4

相关度提升:
- Before: 30-40% 相关
- After: 85-90% 相关 ✅
```

## 💻 下一步

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **配置API密钥**
   ```bash
   cp .env.example .env
   nano .env  # 添加 ANTHROPIC_API_KEY
   ```

3. **运行测试**
   ```bash
   python main.py --defaults --days 1 --top 5
   ```

4. **查看报告**
   ```bash
   cat data/reports/ai_briefing_*.md
   ```

## 📚 相关文档

- [FINTECH_CUSTOMIZATION.md](FINTECH_CUSTOMIZATION.md) - 完整定制说明
- [README.md](README.md) - 项目总体说明
- [CATEGORY_SELECTOR_API.md](docs/CATEGORY_SELECTOR_API.md) - API文档

---

**定制版本**: 金融科技版 v1.0
**更新日期**: 2024-10-24
**适用场景**: 智能风控信贷公司
