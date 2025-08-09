# 智能求职经纪人：工具使用与执行（详细设计）

智能求职经纪人的所有实际操作都通过一个名为 `JobToolExecutor` 的工具执行器来完成。这个执行器将 LLM 的指令转化为具体的浏览器行为。由于任务的高度聚焦，其工具集也应该非常专业和高效。

## 核心工具集 (Core Toolset)

以下是为求职任务设计的核心浏览器工具集：

### 1. `browser.navigate(url: string)`
*   **功能**: 指示浏览器跳转到指定的 URL。
*   **用途**: 打开招聘网站首页，或直接进入特定的招聘板块。
*   **示例**: `browser.navigate('https://www.linkedin.com/jobs')`
*   **参数**: `url` - 必须是包含协议的完整 URL (e.g., `https://...`)。
*   **底层实现**: `await this.page.goto(url, { waitUntil: 'domcontentloaded' });`
*   **成功返回**: `{ isTermination: false, hasError: false, content: '成功导航到 ' + url }`
*   **失败返回**: `{ ..., hasError: true, error: '导航失败，URL可能无效或页面加载超时' }`

### 2. `browser.type(selector: string, text: string)`
*   **功能**: 在指定的页面元素（通过 CSS 选择器定位）中输入文本。
*   **用途**: 填写搜索框（职位、地点）、登录表单等。
*   **示例**: `browser.type('input.jobs-search-box__text-input', 'Senior Product Manager')`
*   **参数**: `selector` - 用于定位元素的 CSS 选择器; `text` - 要输入的文本。
*   **底层实现**: `await this.page.type(selector, text, { delay: 100 });` (增加延迟模拟真实用户)
*   **成功返回**: `{ ..., hasError: false, content: '成功在元素 ' + selector + ' 中输入文本' }`
*   **失败返回**: `{ ..., hasError: true, error: '找不到选择器 ' + selector + ' 对应的元素' }`

### 3. `browser.click(selector: string)`
*   **功能**: 模拟用户点击一个页面元素。
*   **用途**: 点击搜索按钮、“下一页”按钮、筛选条件、查看职位详情链接等。
*   **示例**: `browser.click('button[type=submit]')`
*   **参数**: `selector` - 要点击的元素的 CSS 选择器。
*   **底层实现**: `await this.page.click(selector);`
*   **成功返回**: `{ ..., hasError: false, content: '成功点击元素 ' + selector }`
*   **失败返回**: `{ ..., hasError: true, error: '找不到或无法点击选择器 ' + selector + ' 对应的元素' }`

### 4. `browser.scrape_visible_text()`
*   **功能**: 提取当前浏览器视口内所有可见的文本内容。
*   **用途**: 一个通用的“阅读”工具，让 LLM 可以理解当前页面的内容，判断页面状态（如是否需要登录、是否有验证码、搜索结果是否为空等）。
*   **返回**: 包含页面所有文本内容的一个长字符串。
*   **底层实现**: `const text = await this.page.evaluate(() => document.body.innerText);`
*   **成功返回**: `{ ..., hasError: false, content: '页面可见文本内容: [截断后的文本...]' }` (返回内容需要截断以防超出上下文)

### 5. `browser.scrape_job_list(item_selector: string, title_selector: string, company_selector: string, link_selector: string, location_selector: string)`
*   **功能**: 这是一个为求职场景特化的高级工具。它能从一个职位列表页面中，根据指定的选择器，结构化地提取出多个职位的信息。
*   **用途**: 高效地从搜索结果页中批量抓取职位列表，而不是逐个处理。
*   **返回**: 一个 JSON 数组，每个对象包含 `title`, `company`, `link`, `location` 等字段。
*   **示例**: `browser.scrape_job_list('.job-card', '.job-title', '.company-name', 'a.job-link', '.job-location')`
*   **参数**: 一个包含多个选择器的对象，如 `{ item: '.job-card', title: '.title', ... }`。
*   **底层实现**: 
    ```typescript
    const jobs = await this.page.evaluate((selectors) => {
        const results = [];
        document.querySelectorAll(selectors.item).forEach(item => {
            results.push({
                title: item.querySelector(selectors.title)?.innerText,
                // ... etc
            });
        });
        return results;
    }, selectors);
    ```
*   **成功返回**: `{ ..., hasError: false, content: jobs }` (返回结构化的 JSON 数据)

### 6. `system.finish(reason: string, found_jobs: object[])`
*   **功能**: 这是一个特殊的**同步**工具，它不与浏览器交互，而是用于终止任务循环。
*   **用途**: 当 LLM 判断任务已经完成时（例如，已搜索完所有预定网站，或找到了足够多的匹配职位），它会调用此工具来终止自己的运行。
*   **实现**: 
    ```typescript
    this.foundJobs = found_jobs;
    return { isTermination: true, hasError: false, content: '任务完成: ' + reason };
    ```
*   **返回**: `isTermination` 标志被设为 `true`，主循环会捕获这个信号并退出。

## 工具执行流程

1.  **接收指令**: `JobToolExecutor` 从 `JobSearchTask` 接收到 LLM 生成的工具代码字符串。
2.  **解析与验证**: 解析字符串，提取工具名称和参数。验证工具是否存在以及参数是否合法。
3.  **调用浏览器库**: `JobToolExecutor` 的底层会调用一个真正的浏览器自动化库，如 **Playwright** 或 **Puppeteer**。例如，`browser.click(selector)` 的实现就是调用 `page.click(selector)`。
4.  **捕获结果**: 执行浏览器操作，并捕获结果。如果成功，返回成功信息或抓取到的数据。如果失败（如选择器未找到、页面加载超时），则捕获异常信息。
5.  **返回给核心循环**: 将执行结果（成功或失败）返回给 `JobSearchTask`，以便作为“观察结果”反馈给 LLM。

## 工具执行器 (`JobToolExecutor`) 伪代码

`JobToolExecutor` 是所有工具的入口点。它负责解析工具调用、分发到具体实现并统一返回格式。

```typescript
import { Page } from 'playwright';

// 定义统一的工具返回格式
interface ToolResult {
  isTermination: boolean; // 是否是终止任务的工具
  hasError: boolean;
  content: any; // 工具执行的返回内容
  error?: string; // 错误信息
}

class JobToolExecutor {
  private page: Page; // Playwright 的页面实例
  private foundJobs: object[] = [];

  constructor(page: Page) {
    this.page = page;
  }

  async execute(toolCode: string): Promise<ToolResult> {
    // 简单的解析逻辑，实际应使用更健壮的解析器
    const match = toolCode.match(/(\w+\.\w+)\((.*)\)/);
    if (!match) {
      return { isTermination: false, hasError: true, content: null, error: '无效的工具代码格式' };
    }

    const [_, toolName, argsString] = match;
    const args = this._parseArgs(argsString);

    try {
      switch (toolName) {
        case 'browser.navigate':
          return await this._navigate(args[0]);
        case 'browser.type':
          return await this._type(args[0], args[1]);
        case 'browser.click':
          return await this._click(args[0]);
        case 'browser.scrape_visible_text':
          return await this._scrapeVisibleText();
        case 'browser.scrape_job_list':
          return await this._scrapeJobList(args);
        case 'system.finish':
          return this._finish(args[0], args[1]);
        default:
          return { isTermination: false, hasError: true, content: null, error: `未知的工具: ${toolName}` };
      }
    } catch (e) {
      return { isTermination: false, hasError: true, content: null, error: `工具执行失败: ${e.message}` };
    }
  }
  
  // ... 具体工具的私有实现 ...

  getFinalResult() {
      return this.foundJobs;
  }
}
