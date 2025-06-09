import os
import json
import hashlib
import pickle

class SaveContentPipeline:
    def __init__(self, crawler):
        self.crawler = crawler
        os.makedirs('spider_data/pages', exist_ok=True)
        os.makedirs('spider_data/files', exist_ok=True)
        self.metadata_file = 'spider_data/metadata.json'
        self.metadata = []
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
        # Load custom stats backup
        self.stats_file = 'spider_data/state/custom_stats.pickle'
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'rb') as f:
                    self.crawler.stats.set_value('item_scraped_count', pickle.load(f).get('item_scraped_count', 0))
            except Exception as e:
                crawler.spider.logger.warning(f"Failed to load custom stats: {e}")

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_item(self, item, spider):
        url_hash = hashlib.md5(item['url'].encode()).hexdigest()
        if item['file_type'] == 'html':
            filename = f'{url_hash}.html'
            folder = 'spider_data/pages'
            snapshot_path = os.path.join(folder, filename)  # 新增快照路径
        else:
            filename = f'{url_hash}.{item["file_type"]}'
            folder = 'spider_data/files'
            snapshot_path = None  # 非 HTML 文件无快照

        file_path = os.path.join(folder, filename)
        if os.path.exists(file_path):
            return item

        try:
            with open(file_path, 'wb') as f:
                f.write(item['content'])
        except Exception as e:
            spider.logger.warning(f"Failed to save file {file_path}: {e}")
            return item

        metadata_entry = {
            'url': item['url'],
            'filename': filename,
            'file_type': item['file_type'],
            'original_filename': item.get('original_filename'),
            'snapshot_path': snapshot_path  # 新增字段
        }
        self.metadata.append(metadata_entry)
        
        # Update progress bar and backup stats
        if hasattr(spider, 'progress_bar') and spider.progress_bar:
            try:
                stats = self.crawler.stats.get_stats()
                item_count = stats.get('item_scraped_count', 0)
                spider.progress_bar.n = item_count
                spider.progress_bar.refresh()
                # Backup stats
                with open(self.stats_file, 'wb') as f:
                    pickle.dump(stats, f)
            except Exception as e:
                spider.logger.warning(f"Failed to update progress bar or backup stats: {e}")
        
        return item
    
    def close_spider(self, spider):
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            spider.logger.warning(f"Failed to save metadata: {e}")
        if hasattr(spider, 'progress_bar') and spider.progress_bar:
            spider.progress_bar.close()
