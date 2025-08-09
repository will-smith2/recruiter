# 智能求职经纪人：上下文管理（详细设计）

对于一个需要长时间、多步骤与网页交互的 AI 智能体来说，拥有一个强大而高效的“记忆”系统至关重要。这个“记忆”就是它每次与 LLM 通信时所使用的上下文（Context）。`ContextManager`（上下文管理器）负责为求职经纪人动态构建这个上下文。

## 1. `ContextManager` 伪代码

`ContextManager` 的核心职责是根据当前任务状态，动态地构建和管理发送给 LLM 的提示词。

```typescript
class ContextManager {
  private systemPrompt: string;
  private userProfile: object;
  private worldKnowledge: object;
  private maxPromptTokens: number = 150000; // 假设上下文窗口为 200k，留出余量

  constructor(systemPrompt, userProfile, worldKnowledge) {
    this.systemPrompt = systemPrompt;
    this.userProfile = userProfile;
    this.worldKnowledge = worldKnowledge;
  }

  buildPrompt(history: Step[], scratchpadContent: any): string {
    const sections = {
      system_prompt: this.systemPrompt,
      user_profile: this.userProfile,
      world_knowledge: this.worldKnowledge,
      scratchpad: this._formatScratchpad(scratchpadContent),
      history: this._formatHistory(history),
      available_tools: this._getToolSignatures()
    };

    let prompt = '';
    for (const [tag, content] of Object.entries(sections)) {
        if (content) {
            prompt += `<${tag}>\n${content}\n</${tag}>\n\n`;
        }
    }

    // 检查并压缩 token
    while (this.countTokens(prompt) > this.maxPromptTokens) {
        // 优先压缩历史记录
        if (history.length > 2) {
            const summarizedHistory = this._summarizeHistory(history);
            history = summarizedHistory; // 用摘要替换原始历史
            // 重新构建 prompt
            sections.history = this._formatHistory(history);
            // ... 重新拼接 prompt ...
        } else {
            // 如果历史已经很短，可能需要截断 scratchpad 内容
            sections.scratchpad = this._truncate(sections.scratchpad);
            // ... 重新拼接 prompt ...
        }
    }

    return prompt;
  }

  // ... 其他私有方法 ...
}
```

## 2. 上下文的核心组成

每一次调用 LLM 时，`ContextManager` 都会组装以下几类信息：

1.  **系统提示 (System Prompt)**: (静态) 定义智能体的身份、目标和基本规则。这是每次对话的基石，始终位于上下文的最顶端。

2.  **用户画像 (User Profile)**: (静态) 包含用户的简历信息和求职偏好。这部分信息在整个任务期间保持不变，确保智能体的所有行动都围绕用户的核心需求展开。

3.  **世界知识 (World Knowledge)**: (静态) 一个包含主流招聘网站 URL 的列表。这为智能体提供了从哪里开始的初始方向。

4.  **行动历史 (Action History)**: (动态) 这是上下文中最核心、动态变化的部分。它是一个不断增长的列表，记录了智能体每一步的“思考-行动-观察”三元组。
    *   **思考 (Think)**: LLM 在上一步的内心独白（`<thinking>` 标签内的内容）。
    *   **行动 (Act)**: LLM 在上一步选择执行的工具代码（`<tool_code>` 标签内的内容）。
    *   **观察 (Observe)**: 上一步工具执行后返回的结果（成功信息、错误信息或抓取到的数据）。

5.  **短期记忆 (Short-term Memory / Scratchpad)**: (动态) 一块临时区域，用于存放当前正在处理的、从网页上抓取到的信息。例如，当智能体使用 `browser.scrape_job_list` 后，抓取到的职位列表会先存放在这里。LLM 会被告知：“这是你刚刚抓取到的职位列表，请根据用户偏好进行筛选。”

## 3. 上下文管理策略（详细）

由于 LLM 的上下文窗口大小有限，当任务步骤增多时，行动历史会变得非常长。`ContextManager` 必须采用智能策略来防止上下文溢出，同时保证信息的有效性。

#### 滚动摘要 (Rolling Summarization)

这不是每次都执行，而是在检测到上下文长度即将超限时触发的“维护”操作。

-   **触发时机**: `buildPrompt` 方法在构建完提示词后，发现其 token 总数超过阈值（如 `maxPromptTokens` 的 90%）。
-   **实现思路**:
    1.  取出历史记录中最早的 3-5 个步骤。
    2.  构建一个特殊的提示词，要求 LLM 对这些步骤进行摘要，例如：
        > “请将以下操作序列总结为一句话的摘要：[步骤1的文本] [步骤2的文本] ...”
    3.  用 LLM 返回的摘要替换掉原来的那几步历史记录，并在摘要前加上 `[Summarized]` 标签。
    4.  这样，历史记录的长度被有效缩短，为新的步骤腾出了空间。

#### 信息过滤与截断 (Filtering & Truncation)

-   **处理大文本**: 当 `browser.scrape_visible_text` 返回大量文本时，`ContextManager` 不会直接将其全部放入上下文。
    -   **预处理**: 它会先通过简单的规则（如移除多余的换行符、空格）和启发式方法（如移除长度小于 10 个单词的行）来清洗文本。
    -   **截断**: 清洗后，它会从文本的开头截取一部分（如前 4000 个 token），并在末尾附上 `[... content truncated ...]`，告知 LLM 这不是全部内容。
-   **处理结构化数据**: 当 `browser.scrape_job_list` 返回一个包含 20 个职位的 JSON 数组时，直接将整个 JSON 放入上下文是低效的。
    -   **存入临时区**: 这个 JSON 数组会被存放在 `scratchpad`（暂存器）中。
    -   **在提示词中引用**: `ContextManager` 会在提示词的 `<scratchpad>` 部分告诉 LLM：
        > “你刚刚通过 `scrape_job_list` 获取了 20 个职位，它们已存入暂存器。请根据用户画像，分析这些职位，并决定下一步是筛选它们，还是继续搜索。”
    -   只有当 LLM 明确要求分析某个具体职位时，才会将该职位的详细信息放入上下文。

## 4. 总结

求职经纪人的 `ContextManager` 就像一个高效的秘书。它不仅要忠实地记录经纪人的每一步行动，还要在“记忆”变得臃肿时，智能地进行清理、总结和归档。通过这种方式，它确保了 LLM 在任务的任何阶段都能获得最相关、最简洁的信息，从而做出正确、高效的决策。
