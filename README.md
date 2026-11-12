# Dongyuan’s Notes

Hugo + PaperMod 研究博客，Notion 为内容源，GitHub Actions 构建并部署到 GitHub Pages。

网站：https://coffee3699.github.io/

## 发布文章

1. 直接在 Notion Blog Posts 中编辑原始文章。数据库条目就是原始页面，仅维护这一份正文。
2. 填写 Name、Summary、Slug（小写英文与连字符）、Published Date、Category、Series。
3. 设置 Status = Published，勾选 Public Approved。
4. GitHub Actions → Publish research blog → Run workflow；或等待每小时第 23 分钟的定时任务（GitHub 可能延迟执行）。
5. 只有部署任务成功才代表网站已更新。首次部署没有合格文章时显示博客首页与导航，这是正常状态。

撤回：取消 Public Approved 或改为 Draft，然后重新运行工作流。下一次成功部署会移除该文章，已被第三方缓存的内容不受控制。

## GitHub 设置

- Settings → Pages → Source 选择 GitHub Actions。
- Actions secret: NOTION_TOKEN。
- Actions variable: NOTION_DATA_SOURCE_ID。
- Notion 连接应具有 Blog Posts 的读取权限。
- 仓库 coffee3699.github.io 为个人主页，baseURL 为 https://coffee3699.github.io/；以后绑定自定义域名时需同步更新此配置。

## 内容格式

支持段落、标题、富文本、列表、任务列表、引用、callout、代码、公式、普通表格、图片、列布局与折叠内容（展开呈现）、外部书签。Notion 目录由 Hugo 目录替代。公式使用 Notion equation 块或行内 equation。

不支持的块会中止部署，避免静默丢失正文。文件附件、同步块、子页面、数据库、视频等请先改写成受支持的形式。图片会下载到文章资源目录，支持 PNG/JPEG/GIF/WebP/AVIF，单张不超过 20 MB。公式渲染使用 MathJax CDN。

正文直接从原始页面读取，不复制到另一份发布稿。原始 Notion 页面链接在移动后保持有效。Source Notes 不导出。私人页面、数据库和用户 mention 及 Notion 链接会阻止发布。此检查不能代替人工审稿。同步不递归读取 Source Notes；不要直接复制内部报告作为公开正文。

## 本地开发

安装 Hugo 0.145.0 和 uv 后：

```sh
git submodule update --init --recursive
uv sync --frozen
uv run python -m unittest discover -s tests -v
# 设置 NOTION_TOKEN、NOTION_DATA_SOURCE_ID 环境变量后：
uv run python scripts/notion_sync.py
hugo server
```

生成的 Markdown 与图片仅用于构建，不提交回仓库；原稿保存在 Notion。同步失败不会发布部分内容，网站保留上次成功部署。

## 维护

主题固定到 Git 子模块提交，Hugo 和 uv 固定版本。更新后先跑测试与 Hugo 构建。GitHub 可能在长期无活动后停用公共仓库的计划任务，可在 Actions 页面重新启用。查看失败任务日志时不要粘贴 token 或私有正文。

## 系列分区

Notion 中只维护 Series（多选），首页按 Series 分区展示。同一文章可属于多个系列，会在对应分区分别出现；未设置系列的文章归入“未分类”。原 Tags 已合并至 Series。
