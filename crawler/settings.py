BOT_NAME = 'nankai_crawler'
SPIDER_MODULES = ['crawler.spiders']
NEWSPIDER_MODULE = 'crawler.spiders'
DOWNLOAD_DELAY = 0.1
USER_AGENT = 'NankaiCrawler (2310648@mail.nankai.edu.cn)'
CONCURRENT_REQUESTS = 32
CONCURRENT_REQUESTS_PER_DOMAIN = 16  # 增加每个域名的并发请求
CLOSESPIDER_ITEMCOUNT = 100000
ITEM_PIPELINES = {
    'crawler.pipelines.SaveContentPipeline': 300,
}
ROBOTSTXT_OBEY = True
LOG_LEVEL = 'INFO'
DOWNLOAD_TIMEOUT = 60
TLDEXTRACT_CACHE = 'spider_data/cache/tldextract.cache'  # 自定义缓存路径
HTTPERROR_ALLOWED_CODES = [403, 404, 429]
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]
JOBDIR = 'spider_data/state'
STATS_DUMP = True
