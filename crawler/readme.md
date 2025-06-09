# 南开大学网站爬虫说明

本目录包含基于 Scrapy 的南开大学官网及子域名爬虫，支持断点续爬、文件与页面分类保存、进度条显示等功能。

---

## 一、用法

1. **安装依赖**
   ```
   pip install scrapy tqdm tldextract
   ```

2. **运行爬虫**
   ```
   scrapy crawl nankai_crawler -s JOBDIR=spider_data/state
   ```
   - 支持断点续爬，JOBDIR 路径可自定义。

3. **数据存储**
   - HTML 页面保存至 `spider_data/pages/`，文件保存至 `spider_data/files/`。
   - 元数据（包括 url、文件类型、原始文件名等）记录在 `spider_data/metadata.json`。

---

## 二、主要文件与功能

### 1. `items.py`
- 定义 `PageItem`，包含 url、content、file_type、original_filename 字段。

### 2. `pipelines.py`
- `SaveContentPipeline`：
  - 保存页面/文件到本地，避免重复下载。
  - 记录元数据，支持进度条与断点续爬。

### 3. `settings.py`
- Scrapy 配置，包括并发数、延迟、缓存、超时、断点续爬等参数。

### 4. `spiders/nankai_spider.py`
- `NankaiSpider`：
  - `start_requests`：初始化爬虫、断点续爬、进度条。
  - `parse`：处理 HTML 页面，发现并递归爬取新链接，识别文件型资源。
  - `parse_file`：处理文件下载，提取原始文件名。
  - `handle_error`：请求错误处理。

---

## 三、函数说明

- `start_requests`：初始化 tldextract 缓存、进度条，支持断点续爬。
- `parse`：解析页面，发现新链接和文件，递归爬取。
- `parse_file`：下载文件，提取文件名，保存内容。
- `process_item`（pipeline）：保存文件/页面，记录元数据，更新进度条。
- `close_spider`（pipeline）：保存所有元数据，关闭进度条。

---

## 四、注意事项

- 建议在校园网环境下运行，避免部分子域名无法访问。
- 数据量大时，建议定期备份 `spider_data/` 目录。
- 若需重置爬虫状态，可删除 `spider_data/state/` 目录。