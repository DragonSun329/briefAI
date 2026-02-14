# brief-writer

briefAI → 公众号文章 的内容生产系统。

## 核心理念

```
briefAI = 情报员（intelligence）
Editor Agent = 主编（narrative + opinion）
你 = 总编（审核3分钟）
```

直接让AI"根据新闻写文章" = 资讯站味道
用这套系统 = 有观点的作者

## 文件说明

| 文件 | 作用 |
|------|------|
| `WRITER_IDENTITY.md` | 作者人格（占效果70%）|
| `STYLE_GUIDE.md` | 风格规范 + 反AI味checklist |
| `ARTICLE_TEMPLATE.md` | 结构参考 |
| `HOOK_LIBRARY.md` | 开头模板库 |
| `prompts/1_select_topic.md` | 选题 |
| `prompts/2_angle.md` | 找角度（最关键）|
| `prompts/3_write.md` | 写初稿 |
| `prompts/4_polish.md` | 去AI味 |
| `prompts/workflows/daily_article.md` | 每日流程 |

## 快速开始

```
1. 获取 briefAI 每日简报
2. 跑 1_select_topic → 选一个话题
3. 跑 2_angle → 找到观点角度
4. 跑 3_write → 出初稿
5. 跑 4_polish → 去AI味
6. 你改3分钟 → 发
```

总耗时：8-15分钟

## 关键原则

- **情报 ≠ 文章**：简报是素材，不是正文
- **观点 > 信息**：解释新闻意味着什么，不是报道新闻
- **角度 = 灵魂**：Step 2 决定文章成败
- **人格先行**：没有WRITER_IDENTITY，永远写不出人味

## 输出存档

`articles/YYYY-MM-DD.md`
