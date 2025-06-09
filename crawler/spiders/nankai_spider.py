import scrapy
import os
from crawler.items import PageItem
from urllib.parse import urlparse, urljoin, unquote
import re
from tqdm import tqdm
import tldextract
import pickle

class NankaiSpider(scrapy.Spider):
    name = 'nankai_crawler'
    allowed_domains = ['nankai.edu.cn']
    start_urls = [
        'https://www.nankai.edu.cn/',
        'https://wxy.nankai.edu.cn/',
        'https://history.nankai.edu.cn/',
        'https://phil.nankai.edu.cn/',
        'https://sfs.nankai.edu.cn/',
        'https://law.nankai.edu.cn/',
        'https://zfxy.nankai.edu.cn/',
        'https://cz.nankai.edu.cn/',
        'https://hyxy.nankai.edu.cn/',
        'https://economics.nankai.edu.cn/',
        'https://bs.nankai.edu.cn/',
        'https://tas.nankai.edu.cn/,'
        'https://finance.nankai.edu.cn/',
        'https://math.nankai.edu.cn/',
        'https://physics.nankai.edu.cn/',
        'https://chem.nankai.edu.cn/',
        'https://sky.nankai.edu.cn/',
        'https://env.nankai.edu.cn/',
        'https://medical.nankai.edu.cn/',
        'https://pharmacy.nankai.edu.cn/',
        'https://ceo.nankai.edu.cn/',
        'https://mse.nankai.edu.cn/',
        'https://cc.nankai.edu.cn/',
        'https://cyber.nankai.edu.cn/',
        'https://ai.nankai.edu.cn/',
        'https://cs.nankai.edu.cn/',
        'https://stat.nankai.edu.cn/',
        'https://jc.nankai.edu.cn/',
        'https://shxy.nankai.edu.cn/'
    ]
    file_extensions = {'.pdf', '.doc', '.docx', '.jpg', '.png', '.xls', '.xlsx'}
    handle_httpstatus_list = [403, 404, 429]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_urls = set()  # 使用集合快速去重

    def start_requests(self):
        # Initialize tldextract with custom cache
        cache_dir = os.path.join('spider_data', 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        self.tld_extract = tldextract.TLDExtract(
            cache_dir=cache_dir,
            suffix_list_urls=None,
            fallback_to_snapshot=True
        )
        
        # Initialize progress bar
        try:
            self.progress_bar = tqdm(total=100000, desc="Crawling", unit="items")
            stats = self.crawler.stats.get_stats()
            initial_count = stats.get('item_scraped_count', 0)
            self.progress_bar.n = initial_count
            self.progress_bar.refresh()
        except Exception as e:
            self.logger.warning(f"Failed to initialize progress bar: {e}")
            self.progress_bar = None

        # Yield start URLs
        for url in self.start_urls:
            if url not in self.seen_urls:
                self.seen_urls.add(url)
                yield scrapy.Request(url, callback=self.parse, errback=self.handle_error)

    def parse(self, response):
        if response.status in (403, 404, 429):
            return

        try:
            # Save HTML page
            if not any(response.url.lower().endswith(ext) for ext in self.file_extensions):
                item = PageItem()
                item['url'] = response.url
                item['content'] = response.body
                item['file_type'] = 'html'
                item['original_filename'] = None
                yield item

            # Extract and follow links
            for href in response.css('a::attr(href)').getall():
                absolute_url = urljoin(response.url, href.strip())
                if absolute_url in self.seen_urls:
                    continue  # 跳过已处理的 URL
                self.seen_urls.add(absolute_url)

                parsed = urlparse(absolute_url)
                if not parsed.scheme in ('http', 'https') or not parsed.netloc:
                    continue

                path = parsed.path.lower()
                file_ext = next((ext for ext in self.file_extensions if path.endswith(ext)), None)
                
                if file_ext:
                    yield scrapy.Request(
                        absolute_url,
                        callback=self.parse_file,
                        meta={'file_type': file_ext[1:]},
                        errback=self.handle_error
                    )
                else:
                    yield response.follow(
                        absolute_url,
                        self.parse,
                        errback=self.handle_error
                    )
        except Exception as e:
            self.logger.warning(f"Error in parse: {e}")

    def parse_file(self, response):
        if response.status in (403, 404, 429):
            return
        try:
            item = PageItem()
            item['url'] = response.url
            item['content'] = response.body
            item['file_type'] = response.meta['file_type']
            
            content_disposition = response.headers.get('Content-Disposition', b'').decode('utf-8', errors='ignore')
            if content_disposition:
                filename_match = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disposition)
                item['original_filename'] = filename_match.group(1) if filename_match else None
            else:
                parsed = urlparse(response.url)
                path = parsed.path
                filename = path.split('/')[-1] if '/' in path else path
                item['original_filename'] = unquote(filename, encoding='utf-8', errors='replace') if filename else None
            
            yield item
        except Exception as e:
            self.logger.warning(f"Error in parse_file: {e}")

    def handle_error(self, failure):
        self.logger.warning(f"Request failed: {failure}")