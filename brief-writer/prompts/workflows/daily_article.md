# Daily Article Workflow

每日写作流程。总耗时：8-15分钟。

---

## Step 0: Prep (1 min)

```
获取今日简报：
- briefAI daily_brief_YYYY-MM-DD.md
- 或者最新的 analyst_brief
```

---

## Step 1: Select Topic (2 min)

**Prompt:**
```
Read these files first:
- WRITER_IDENTITY.md
- prompts/1_select_topic.md

Then analyze this intelligence report:
[PASTE DAILY BRIEF]

Select ONE topic for today's article.
```

**Expected output:** Topic + Why It Matters + Hook + Angles

---

## Step 2: Find Angle (2 min)

**Prompt:**
```
Using prompts/2_angle.md, develop an opinionated angle for:

[PASTE SELECTED TOPIC]

Remember: You are not a journalist. You are an opinionated technical founder.
```

**Expected output:** Thesis + What Everyone Gets Wrong + Prediction + Evidence + So What

---

## Step 3: Write Draft (3 min)

**Prompt:**
```
Using:
- WRITER_IDENTITY.md (voice)
- STYLE_GUIDE.md (rules)
- HOOK_LIBRARY.md (opening inspiration)
- prompts/3_write.md (instructions)

Write the article based on this angle:
[PASTE ANGLE OUTPUT]
```

**Expected output:** 1500-2200字 draft

---

## Step 4: Polish (2 min)

**Prompt:**
```
Using prompts/4_polish.md, polish this article:

[PASTE DRAFT]

Remove AI tone. Add memorable lines. Keep the argument intact.
```

**Expected output:** Publishable article

---

## Step 5: Human Review (3 min)

你的工作：
- [ ] 开头抓人吗？
- [ ] 核心观点清晰吗？
- [ ] 有没有明显的"AI味"？
- [ ] 结尾有力吗？
- [ ] 标题吸引人吗？

改完直接发。

---

## One-Shot Mode (高级)

如果流程熟练了，可以用一个prompt跑完：

```
You are the editor-in-chief.

Read all files in brief-writer/ to understand voice and style.

Here is today's AI intelligence report:
[PASTE DAILY BRIEF]

Produce a publishable WeChat article:
1. Select the best topic
2. Develop an opinionated angle
3. Write the article (1500-2200字)
4. Polish to remove AI tone

Output the final article only.
```

---

## Output Archive

保存位置: `brief-writer/articles/YYYY-MM-DD.md`
