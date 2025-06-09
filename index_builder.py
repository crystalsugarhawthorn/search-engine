import os
import json
import time
from functools import lru_cache, partial
from multiprocessing import Pool, cpu_count
from whoosh.index import create_in
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import MultifieldParser, FuzzyTermPlugin, WildcardPlugin
from whoosh.highlight import UppercaseFormatter
from bs4 import BeautifulSoup, SoupStrainer
import logging
from tqdm import tqdm
from analyzers import ChineseAnalyzer
from whoosh.scoring import BM25F
import psutil

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 支持的文件类型
SUPPORTED_FILE_TYPES = {'.html', '.pdf', '.doc', '.docx', '.jpg', '.png', '.xls', '.xlsx'}

@lru_cache(maxsize=1000)
def extract_html_content(file_path):
    """提取 HTML 或 XML 文件的标题和正文"""
    try:
        with open(file_path, 'rb') as f:
            content = f.read().decode('utf-8', errors='ignore')
        strainer = SoupStrainer(['title', 'p', 'div', 'article'])
        soup = BeautifulSoup(content, 'lxml' if "<html" in content.lower() else "xml", parse_only=strainer)
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        main_content = soup.find('article') or soup.find('div', {'class': 'content'}) or soup
        paragraphs = main_content.find_all('p')
        text = ' '.join(p.get_text() for p in paragraphs).strip() if paragraphs else ""
        return title, text
    except Exception as e:
        logger.error(f"Failed to parse HTML content from {file_path}: {e}")
        return "", ""

@lru_cache(maxsize=100)
def get_file_type(url):
    """从 URL 提取文件类型"""
    return url.split('.')[-1].lower() if '.' in url.split('/')[-1] else 'html'

def process_entry(entry, data_dir):
    """解析单个条目并返回索引文档"""
    try:
        # 获取 file_type，优先使用 metadata.json 中的值
        file_type = entry.get('file_type', get_file_type(entry['url'])).lower()
        if file_type.startswith('.'):
            file_type = file_type[1:]  # 规范化，去掉前缀点
        filename = entry.get('filename')
        
        # 检查 filename 是否存在
        if not filename:
            logger.warning(f"No filename provided for URL {entry['url']}, file_type: {file_type}")
            original_filename = entry.get('original_filename', entry['url'].split('/')[-1] or '未知文件名')
            return {
                "url": entry['url'],
                "title": original_filename,
                "content": "",
                "file_type": file_type,
                "snapshot_path": None
            }
        
        # 修复：根据 file_type 选择文件夹
        base_dir = os.path.dirname(os.path.abspath(__file__))  # 获取 index_builder.py 所在目录
        folder = 'pages' if file_type == 'html' else 'files'
        file_path = os.path.join(base_dir, data_dir, folder, filename)
        
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path} for URL {entry['url']}, file_type: {file_type}")
            original_filename = entry.get('original_filename', entry['url'].split('/')[-1] or '未知文件名')
            return {
                "url": entry['url'],
                "title": original_filename,
                "content": "",
                "file_type": file_type,
                "snapshot_path": None
            }
        
        # 仅为 HTML 文件提取内容
        if file_type == 'html':
            title, content = extract_html_content(file_path)
            logger.info(f"Extracted HTML content for {file_path}")
        else:
            # 非 HTML 文件仅设置标题
            title = entry.get('original_filename', entry['url'].split('/')[-1] or '无标题')
            content = "无内容"
            logger.info(f"Skipping content extraction for {file_type} file: {file_path}")
        
        return {
            "url": entry['url'],
            "title": title,
            "content": content,
            "file_type": file_type,
            "snapshot_path": entry.get('snapshot_path', file_path)
        }
    except Exception as e:
        logger.error(f"Failed to process entry {entry.get('url', 'unknown')}: {e}")
        return None

def build_index(data_dir, index_dir, max_entries=None, batch_size=None):
    """构建倒排索引，支持批量提交和多进程解析"""
    start_time = time.time()
    
    # 加载元数据
    load_start = time.time()
    metadata_file = os.path.join(data_dir, 'metadata.json')
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load metadata: {e}")
        return
    load_time = time.time() - load_start

    # 动态计算 batch_size
    mem = psutil.virtual_memory()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    total_size = 0
    for entry in metadata:
        if entry.get('filename'):
            folder = 'pages' if entry.get('file_type', get_file_type(entry['url'])).lower().lstrip('.') == 'html' else 'files'
            file_path = os.path.join(base_dir, data_dir, folder, entry['filename'])
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
    avg_size = total_size / len(metadata) if metadata else 1
    batch_size = min(10000, max(100, int(mem.available / avg_size))) if batch_size is None else batch_size
    
    # 优化后的schema，使用cn_stopwords.txt中的停用词
    schema = Schema(
        url=ID(stored=True, unique=True),
        title=TEXT(analyzer=ChineseAnalyzer(),  # 使用默认停用词配置
                 stored=True, field_boost=2.0),  # 标题权重加倍
        content=TEXT(analyzer=ChineseAnalyzer(),  # 使用默认停用词配置
                   stored=True, field_boost=1.0),
        file_type=TEXT(stored=True),
        snapshot_path=ID(stored=True)
    )
    os.makedirs(index_dir, exist_ok=True)
    ix = create_in(index_dir, schema)

    metadata = metadata[:max_entries] if max_entries else metadata
    total_entries = len(metadata)
    # 检查缺失文件
    missing_files = []
    for entry in metadata:
        if entry.get('filename'):
            folder = 'pages' if entry.get('file_type', get_file_type(entry['url'])).lower().lstrip('.') == 'html' else 'files'
            file_path = os.path.join(base_dir, data_dir, folder, entry['filename'])
            if not os.path.exists(file_path):
                missing_files.append(entry['filename'])
    if missing_files:
        logger.warning(f"Missing files: {missing_files[:10]}{'...' if len(missing_files) > 10 else ''}")

    process_start = time.time()
    documents = []
    process_entry_with_dir = partial(process_entry, data_dir=data_dir)
    with Pool(processes=max(1, cpu_count() - 1)) as pool, tqdm(total=total_entries, desc="Indexing", unit="doc") as pbar:
        for i, doc in enumerate(pool.imap_unordered(process_entry_with_dir, metadata)):
            if doc:
                documents.append(doc)
            pbar.update(1)
            if (i + 1) % 1000 == 0:
                logger.info(f"Processed {i + 1} documents, memory usage: {psutil.virtual_memory().used / (1024 * 1024):.2f} MB")
    process_time = time.time() - process_start

    index_start = time.time()
    writer = ix.writer()
    for i, doc in enumerate(documents):
        writer.add_document(**doc)
        if (i + 1) % batch_size == 0:
            writer.commit(optimize=False)
            logger.info(f"Committed batch {i + 1} / {len(documents)}")
            writer = ix.writer()
    writer.commit(optimize=True)
    index_time = time.time() - index_start

    total_time = time.time() - start_time
    print(f"\nIndex building completed ({len(documents)} documents indexed)")
    print(f"Time statistics:")
    print(f"- Metadata loading: {load_time:.2f}s")
    print(f"- Document processing: {process_time:.2f}s")
    print(f"- Index building: {index_time:.2f}s")
    print(f"- Total time: {total_time:.2f}s")
    print(f"- Batch size used: {batch_size}")

if __name__ == "__main__":
    data_dir = "spider_data"
    index_dir = "indexdir"
    build_index(data_dir, index_dir, max_entries=None)