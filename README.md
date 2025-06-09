# 南开大学网站搜索引擎项目

本项目为南开大学信息检索课程作业，旨在实现一个支持通配符查询的中文网页搜索引擎，涵盖网页爬取、索引构建、Web 查询与用户管理等功能。

---

## 一、项目结构说明

```
search_engine/
│
├── crawler/                # Scrapy 爬虫相关代码
│   ├── items.py            # 定义爬取数据结构
│   ├── pipelines.py        # 数据保存与处理管道
│   ├── settings.py         # Scrapy 配置
│   └── spiders/
│       └── nankai_spider.py# 主爬虫实现
│
├── analyzers.py            # 中文分词器（Whoosh自定义分析器）
├── personalization.py      # 搜索个性化推荐
├── index_builder.py        # 倒排索引构建与测试搜索
├── server.py               # Flask Web 服务端，支持注册、登录、查询、日志等
│
├── templates/              # 前端页面模板（React+Tailwind）
│   ├── index.html
│   ├── login.html
│   └── register.html
│
├── spider_data/            # 爬虫数据存储目录
│   ├── pages/              # HTML 页面文件
│   ├── files/              # 其他文件（PDF、DOCX等）
│   └── metadata.json       # 爬取文件元数据
│
├── indexdir/               # Whoosh 索引目录
│
├── users.json              # 用户信息（加密存储）
├── query_logs.json         # 用户查询日志
├── log_counter.json        # 日志自增ID计数
└── scrapy.cfg              # Scrapy 配置文件
```

---

## 二、使用方法

### 1. 安装依赖

- Python 3.8 及以上（推荐 3.10）
- 安装依赖库：
  ```
  pip install scrapy flask whoosh jieba tqdm beautifulsoup4 passlib
  ```

### 2. 运行爬虫采集数据

- 进入 `search_engine` 目录，运行爬虫（支持断点续爬）：
  ```
  scrapy crawl nankai_crawler -s JOBDIR=spider_data/state
  ```
- 爬取数据将自动保存到 `spider_data/pages/` 和 `spider_data/files/`，元数据保存在 `spider_data/metadata.json`。

### 3. 构建倒排索引

- 运行索引构建脚本（可调整 max_entries 处理条数）：
  ```
  python index_builder.py
  ```
- 索引文件将生成在 `indexdir/` 目录。

### 4. 启动 Web 服务

- 启动 Flask 服务（默认端口5000）：
  ```
  python server.py
  ```
- 浏览器访问 [http://localhost:5000](http://localhost:5000) 进行注册、登录、搜索。

---

## 三、主要文件与函数说明

### 1. `crawler/items.py`
- `PageItem`：定义爬取页面/文件的结构（url, content, file_type, original_filename）。

### 2. `crawler/pipelines.py`
- `SaveContentPipeline`：
  - `process_item`：保存页面/文件到本地，记录元数据，更新进度条。
  - `close_spider`：保存所有元数据到 metadata.json。

### 3. `crawler/spiders/nankai_spider.py`
- `NankaiSpider`：
  - `start_requests`：初始化爬虫、进度条、断点续爬。
  - `parse`：处理 HTML 页面，发现新链接和文件。
  - `parse_file`：处理文件型资源，提取原始文件名。
  - `handle_error`：错误处理。

### 4. `analyzers.py`
- `ChineseTokenizer`：基于 jieba 的中文分词器，适配 Whoosh。
- `ChineseAnalyzer`：返回自定义中文分析器。

### 5. `index_builder.py`
- `extract_html_content`：提取 HTML 文件标题与正文。
- `build_index`：构建 Whoosh 倒排索引，支持进度条。
- `search_index`：测试索引查询。

### 6. `server.py`
- Flask 路由：
  - `/register`、`/login`、`/logout`、`/get_session`：用户注册、登录、登出、会话管理。
  - `/search`：支持通配符的全文检索。
  - `/get_logs`、`/delete_log/<id>`、`/clear_logs`：用户查询日志管理。
- 用户密码加密存储，支持多用户并发。

### 7. `templates/*.html`
- 前端页面，基于 React + Tailwind，支持注册、登录、搜索、历史记录等交互。

---

## 四、注意事项

- 建议在校园网环境下运行爬虫，避免部分子域名无法访问。
- 数据量较大时，建议预留 20GB 以上磁盘空间。
- 若需重置用户或日志，直接删除 `users.json`、`query_logs.json`、`log_counter.json` 文件。

---

## 五、常见问题

- **爬虫断点续爬**：使用 `-s JOBDIR=spider_data/state` 参数。
- **索引构建慢**：可调整 `build_index` 的 `max_entries` 参数，分批构建。
- **Web 服务端口冲突**：可在 `server.py` 修改端口。
