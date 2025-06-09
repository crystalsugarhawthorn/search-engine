from whoosh.analysis import Tokenizer, Token, LowercaseFilter
import jieba

class ChineseTokenizer(Tokenizer):
    def __init__(self, stoplist=None):
        # 从cn_stopwords.txt加载停用词
        stopwords_file = 'cn_stopwords.txt'
        default_stoplist = set()
        try:
            with open(stopwords_file, 'r', encoding='utf-8') as f:
                default_stoplist = {line.strip() for line in f if line.strip()}
        except FileNotFoundError:
            print(f"警告: 停用词文件 {stopwords_file} 未找到，使用默认停用词")
            default_stoplist = {"的", "是", "和", "在", "了", "有", "我", "他", "她", "它"}
        
        # 合并传入的停用词和默认停用词
        self.stoplist = set(stoplist) if stoplist else default_stoplist

    def __call__(self, value, positions=False, chars=False, keeporiginal=False, 
                 removestops=True, start_pos=0, start_char=0, mode='', **kwargs):
        assert isinstance(value, str), f"{value!r} is not text"
        # 优化：使用 jieba.lcut 直接返回列表，减少迭代开销
        seglist = jieba.lcut(value, cut_all=(mode == 'index'))
        pos = start_pos
        char_pos = start_char
        for term in seglist:
            # 优化：在分词器中直接过滤停用词
            if removestops and term in self.stoplist:
                continue
            token = Token(positions=positions, chars=chars)
            token.text = term
            token.boost = 1.0
            if positions:
                token.pos = pos
                pos += 1
            if chars:
                token.startchar = char_pos
                token.endchar = char_pos + len(term)
                char_pos += len(term)
            yield token

def ChineseAnalyzer(stoplist=None):
    # 优化：仅使用 ChineseTokenizer 和 LowercaseFilter，减少过滤器开销
    return ChineseTokenizer(stoplist=stoplist) | LowercaseFilter()