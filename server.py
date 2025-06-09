import os
import json
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory
from personalization import analyze_user_interests, adjust_search_results, get_collaborative_recommendations
from whoosh.index import open_dir
from whoosh.qparser import MultifieldParser
from whoosh.highlight import UppercaseFormatter
from whoosh.scoring import BM25F
from whoosh.query import Phrase, Wildcard
import logging
from passlib.hash import sha256_crypt
import datetime
import time
import re
from cachetools import LRUCache

app = Flask(__name__)
app.secret_key = 'nankai_search_2025'
app.config['SESSION_COOKIE_DOMAIN'] = 'localhost'

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化查询缓存，最大100条记录
query_cache = LRUCache(maxsize=100)

def load_users():
    try:
        users_file = 'users.json'
        if not os.path.exists(users_file):
            logger.error(f"users.json 文件不存在: {users_file}")
            raise FileNotFoundError("users.json 文件不存在")
        with open(users_file, 'r', encoding='utf-8') as f:
            return json.load(f).get('users', [])
    except Exception as e:
        logger.error(f"加载 users.json 失败: {e}", exc_info=True)
        raise

def save_users(users):
    try:
        with open('users.json', 'w', encoding='utf-8') as f:
            json.dump({'users': users}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存 users.json 失败: {e}", exc_info=True)
        raise

def get_next_log_id():
    try:
        counter_file = 'log_counter.json'
        if not os.path.exists(counter_file):
            counter = {'next_id': 1}
            with open(counter_file, 'w', encoding='utf-8') as cf:
                json.dump(counter, cf, ensure_ascii=False, indent=2)
            return 1
        with open(counter_file, 'r', encoding='utf-8') as f:
            counter = json.load(f)
            next_id = counter['next_id']
            counter['next_id'] += 1
            with open(counter_file, 'w', encoding='utf-8') as cf:
                json.dump(counter, cf, ensure_ascii=False, indent=2)
            return next_id
    except Exception as e:
        logger.error(f"获取日志 ID 失败: {e}", exc_info=True)
        raise

def log_query(username, query):
    log_entry = {
        'id': get_next_log_id(),
        'username': username,
        'query': query,
        'timestamp': datetime.datetime.now().isoformat()
    }
    try:
        log_file = 'query_logs.json'
        logs = []
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        logs.append(log_entry)
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to log query: {e}", exc_info=True)

def get_user_personalization(username):
    try:
        log_file = 'query_logs.json'
        if not os.path.exists(log_file):
            return {}
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        user_logs = [log['query'] for log in logs if log['username'] == username]
        keyword_weights = {}
        for query in user_logs:
            for word in query.split():
                keyword_weights[word] = keyword_weights.get(word, 0) + 1
        return keyword_weights
    except Exception as e:
        logger.error(f"Failed to generate personalization for user {username}: {e}", exc_info=True)
        return {}

def apply_personalization(results, keyword_weights):
    for result in results:
        score_boost = 0
        for keyword, weight in keyword_weights.items():
            if keyword in result['title'] or keyword in result['content_highlight']:
                score_boost += weight
        result['score'] += score_boost
    return sorted(results, key=lambda x: x['score'], reverse=True)

def search_index(index_dir, query_str, page=1, files_only=False, ranking_params=None, is_phrase=False, username=None):
    """优化后的搜索倒排索引函数，支持分页、短语查询、通配查询、精确匹配优先和个性化排序"""
    try:
        if not os.path.exists(index_dir):
            logger.error(f"索引目录不存在: {index_dir}")
            return [], 0, 0, 0
        ix = open_dir(index_dir)
        start_time = time.time()
        ranking_params = ranking_params or {"B": 0.75, "K1": 1.5}
        results = []
        seen_urls = set()

        # 检查缓存
        cache_key = f"{query_str}_{page}_{files_only}_{is_phrase}_{username}"
        if cache_key in query_cache:
            cached_result = query_cache[cache_key]
            return cached_result['results'], cached_result['elapsed_time'], cached_result['total_pages'], cached_result['total_results']

        with ix.searcher(weighting=BM25F(**ranking_params)) as searcher:
            # 1. 精确短语查询
            phrase_results = []
            if is_phrase:
                terms = query_str.split()
                query = Phrase("content", terms)
                phrase_hits = searcher.search(query, limit=100)
                phrase_hits.formatter = UppercaseFormatter()
                for hit in phrase_hits:
                    if hit['url'] not in seen_urls:
                        title_highlight = hit.highlights("title") or hit['title'] or "无标题匹配"
                        content_highlight = hit.highlights("content") or "无内容匹配"
                        # 高亮完整查询词组及单字符
                        query_chars = query_str
                        pattern = re.compile(f"({re.escape(query_chars)})", re.IGNORECASE)
                        title_highlight = pattern.sub(r"<strong>\1</strong>", title_highlight)
                        content_highlight = pattern.sub(r"<strong>\1</strong>", content_highlight)
                        for char in query_chars:
                            char_pattern = re.compile(f"(?<!<strong>)({re.escape(char)})(?!</strong>)", re.IGNORECASE)
                            title_highlight = char_pattern.sub(r"<strong>\1</strong>", title_highlight)
                            content_highlight = char_pattern.sub(r"<strong>\1</strong>", content_highlight)
                        phrase_results.append({
                            "url": hit['url'],
                            "title": hit['title'],
                            "title_highlight": title_highlight,
                            "content_highlight": content_highlight,
                            "score": hit.score * 5.0 + 200.0,
                            "file_type": hit['file_type'],
                            "snapshot_path": hit.get('snapshot_path', ''),
                            "is_exact": True
                        })
                        seen_urls.add(hit['url'])
            else:
                # 2. 通配查询或模糊查询
                # 检测通配符
                is_wildcard = '*' in query_str or '?' in query_str
                fieldboosts = {"title": 2.0, "content": 1.0}
                # 动态调整字段权重
                if is_wildcard:
                    if query_str.startswith('*'):
                        fieldboosts = {"title": 1.0, "content": 2.0}  # 优先内容
                    elif query_str.endswith('*'):
                        fieldboosts = {"title": 3.0, "content": 1.0}  # 优先标题

                if is_wildcard:
                    # 使用 Wildcard 查询处理通配符
                    query = MultifieldParser(["title", "content"], ix.schema, fieldboosts=fieldboosts).parse(query_str)
                    fuzzy_hits = searcher.search(query, limit=100, terms=True, scored=True)
                    fuzzy_hits.formatter = UppercaseFormatter()
                    for hit in fuzzy_hits:
                        if hit['url'] not in seen_urls and (not files_only or hit['file_type'] != 'html'):
                            title_highlight = hit.highlights("title") or hit['title'] or "无标题匹配"
                            content_highlight = hit.highlights("content") or "无内容匹配"
                            # 高亮匹配的扩展词及单字符
                            matched_terms = [term[1].decode('utf-8') for term in hit.matched_terms() if term[0] in [b'title', b'content']]
                            for term in matched_terms + list(query_str.replace('*', '').replace('?', '')):
                                pattern = re.compile(f"(?<!<strong>)({re.escape(term)})(?!</strong>)", re.IGNORECASE)
                                title_highlight = pattern.sub(r"<strong>\1</strong>", title_highlight)
                                content_highlight = pattern.sub(r"<strong>\1</strong>", content_highlight)
                            # 过滤低分结果
                            if hit.score > 0.5:  # 设置分数阈值
                                results.append({
                                    "url": hit['url'],
                                    "title": hit['title'],
                                    "title_highlight": title_highlight,
                                    "content_highlight": content_highlight,
                                    "score": hit.score,
                                    "file_type": hit['file_type'],
                                    "snapshot_path": hit.get('snapshot_path', ''),
                                    "is_exact": False
                                })
                                seen_urls.add(hit['url'])
                else:
                    # 普通模糊查询
                    query = MultifieldParser(["title", "content"], ix.schema, fieldboosts=fieldboosts).parse(query_str)
                    fuzzy_hits = searcher.search(query, limit=100)
                    fuzzy_hits.formatter = UppercaseFormatter()
                    for hit in fuzzy_hits:
                        if hit['url'] not in seen_urls and (not files_only or hit['file_type'] != 'html'):
                            title_highlight = hit.highlights("title") or hit['title'] or "无标题匹配"
                            content_highlight = hit.highlights("content") or "无内容匹配"
                            query_chars = query_str
                            pattern = re.compile(f"({re.escape(query_chars)})", re.IGNORECASE)
                            title_highlight = pattern.sub(r"<strong>\1</strong>", title_highlight)
                            content_highlight = pattern.sub(r"<strong>\1</strong>", content_highlight)
                            for char in query_chars:
                                char_pattern = re.compile(f"(?<!<strong>)({re.escape(char)})(?!</strong>)", re.IGNORECASE)
                                title_highlight = char_pattern.sub(r"<strong>\1</strong>", title_highlight)
                                content_highlight = char_pattern.sub(r"<strong>\1</strong>", content_highlight)
                            if hit.score > 0.5:  # 设置分数阈值
                                results.append({
                                    "url": hit['url'],
                                    "title": hit['title'],
                                    "title_highlight": title_highlight,
                                    "content_highlight": content_highlight,
                                    "score": hit.score,
                                    "file_type": hit['file_type'],
                                    "snapshot_path": hit.get('snapshot_path', ''),
                                    "is_exact": False
                                })
                                seen_urls.add(hit['url'])

            # 3. 合并结果，精确匹配优先
            results = phrase_results + results
            if username:
                results = adjust_search_results(results, username, query_str)

            total_results = len(results)
            results_per_page = 10
            start_index = (page - 1) * results_per_page
            paginated_results = results[start_index:start_index + results_per_page]
        
        elapsed_time = time.time() - start_time
        total_pages = (total_results + results_per_page - 1) // results_per_page

        # 缓存结果
        query_cache[cache_key] = {
            'results': paginated_results,
            'elapsed_time': elapsed_time,
            'total_pages': total_pages,
            'total_results': total_results
        }

        return paginated_results, elapsed_time, total_pages, total_results
    except Exception as e:
        logger.error(f"搜索失败: {e}", exc_info=True)
        return [], 0, 0, 0

@app.route('/')
def index():
    try:
        template_path = os.path.join(app.template_folder, 'index.html')
        if not os.path.exists(template_path):
            logger.error(f"模板文件不存在: {template_path}")
            return jsonify({"error": "模板文件不存在"}), 500
        if 'username' not in session:
            logger.debug("无用户名会话，重定向到登录")
            return redirect(url_for('login_page'))
        logger.debug(f"渲染 index.html，用户: {session['username']}")
        return render_template('index.html')
    except Exception as e:
        logger.error(f"index 路由错误: {e}", exc_info=True)
        return jsonify({"error": f"内部服务器错误: {str(e)}"}), 500

@app.route('/login')
def login_page():
    try:
        if 'username' in session:
            logger.debug("已有会话，重定向到首页")
            return redirect(url_for('index'))
        return render_template('login.html')
    except Exception as e:
        logger.error(f"login_page 路由错误: {e}", exc_info=True)
        return jsonify({"error": "内部服务器错误"}), 500

@app.route('/register')
def register_page():
    try:
        if 'username' in session:
            logger.debug("已有会话，重定向到首页")
            return redirect(url_for('index'))
        return render_template('register.html')
    except Exception as e:
        logger.error(f"register_page 路由错误: {e}", exc_info=True)
        return jsonify({"error": "内部服务器错误"}), 500

@app.route('/search', methods=['POST'])
def search():
    try:
        if 'username' not in session:
            logger.warning("未登录用户尝试搜索")
            return jsonify({"error": "您必须登录才能搜索"}), 401
        data = request.get_json()
        if not data:
            return jsonify({"error": "无效的请求数据"}), 400
        query_str = data.get('query', '').strip()
        if not query_str:
            logger.warning("收到空查询")
            return jsonify({"error": "查询字符串不能为空"}), 400
        page = int(data.get('page', 1))
        files_only = data.get('files_only', False)
        is_phrase = data.get('is_phrase', False)
        ranking_params = get_user_ranking_params(session['username'])
        index_dir = "indexdir"
        results, elapsed_time, total_pages, total_results = search_index(
            index_dir, 
            query_str, 
            page=page, 
            files_only=files_only, 
            ranking_params=ranking_params, 
            is_phrase=is_phrase, 
            username=session['username']
        )
        log_query(session['username'], query_str)
        logger.debug(f"搜索结果: {len(results)} 条，耗时: {elapsed_time:.2f} 秒")
        return jsonify({
            "results": results,
            "elapsed_time": elapsed_time,
            "total_pages": total_pages,
            "total": total_results,
            "page": page,
            "query": query_str
        })
    except Exception as e:
        logger.error(f"search 路由错误: {e}", exc_info=True)
        return jsonify({"error": "搜索失败"}), 500

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        users = load_users()
        if any(user['username'] == username for user in users):
            logger.warning(f"用户名已存在: {username}")
            return jsonify({"error": "用户名已存在"}), 400
        hashed_password = sha256_crypt.hash(password)
        users.append({'username': username, 'password': hashed_password})
        save_users(users)
        logger.info(f"用户注册成功: {username}")
        return jsonify({"message": "注册成功"}), 201
    except Exception as e:
        logger.error(f"register 路由错误: {e}", exc_info=True)
        return jsonify({"error": "注册失败"}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        users = load_users()
        user = next((u for u in users if u['username'] == username), None)
        if user and sha256_crypt.verify(password, user['password']):
            session['username'] = username
            logger.info(f"用户登录成功: {username}")
            return jsonify({"message": "登录成功"}), 200
        else:
            logger.warning(f"无效的用户名或密码: {username}")
            return jsonify({"error": "无效的用户名或密码"}), 401
    except Exception as e:
        logger.error(f"login 路由错误: {e}", exc_info=True)
        return jsonify({"error": "登录失败"}), 500

@app.route('/logout')
def logout():
    try:
        session.pop('username', None)
        logger.info("用户登出")
        return jsonify({"message": "登出成功"})
    except Exception as e:
        logger.error(f"logout 路由错误: {e}", exc_info=True)
        return jsonify({"error": "登出失败"}), 500

@app.route('/get_session')
def get_session():
    try:
        return jsonify({"logged_in": 'username' in session, "username": session.get('username', '')})
    except Exception as e:
        logger.error(f"Failed to get session: {e}", exc_info=True)
        return jsonify({"error": "获取会话失败"}), 500

@app.route('/get_logs')
def get_logs():
    try:
        if 'username' not in session:
            return jsonify({"error": "未登录"}), 401
        if os.path.exists('query_logs.json'):
            with open('query_logs.json', 'r', encoding='utf-8') as f:
                all_logs = json.load(f)
            user_logs = [
                {
                    'query': log['query'],
                    'timestamp': log.get('timestamp', ''),
                    'results_count': log.get('results_count', 0)
                }
                for log in all_logs
                if log.get('username') == session['username']
            ]
            return jsonify(user_logs)
        else:
            return jsonify([])
    except Exception as e:
        logger.error(f"获取日志失败: {e}", exc_info=True)
        return jsonify({"error": "获取日志失败"}), 500

@app.route('/delete_log', methods=['POST'])
def delete_log():
    try:
        if 'username' not in session:
            return jsonify({"error": "未登录"}), 401
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({"error": "缺少查询参数"}), 400
        query = data['query']
        if os.path.exists('query_logs.json'):
            with open('query_logs.json', 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []
        logs = [log for log in logs if log.get('query') != query or log.get('username') != session['username']]
        with open('query_logs.json', 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        return jsonify({"message": "删除成功"})
    except Exception as e:
        logger.error(f"删除日志失败: {e}", exc_info=True)
        return jsonify({"error": "删除失败"}), 500

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    try:
        if 'username' not in session:
            return jsonify({"error": "未登录"}), 401
        if os.path.exists('query_logs.json'):
            with open('query_logs.json', 'r', encoding='utf-8') as f:
                logs = json.load(f)
            logs = [log for log in logs if log.get('username') != session['username']]
            with open('query_logs.json', 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        return jsonify({"message": "清空成功"})
    except Exception as e:
        logger.error(f"清空日志失败: {e}", exc_info=True)
        return jsonify({"error": "清空失败"}), 500

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

@app.route('/spider_data/<path:filename>')
def serve_spider_data(filename):
    return send_from_directory('spider_data', filename)

@app.route('/_redirect')
def redirect_proxy():
    siteId = request.args.get('siteId', '')
    columnId = request.args.get('columnId', '')
    articleId = request.args.get('articleId', '')
    if siteId and columnId and articleId:
        target_url = f"https://www.nankai.edu.cn/_redirect?siteId={siteId}&columnId={columnId}&articleId={articleId}"
        return redirect(target_url)
    return "无法找到目标页面", 404

def get_user_ranking_params(username):
    users = load_users()
    for user in users:
        if user.get('username') == username:
            return user.get('ranking_params', {"B": 0.75, "K1": 1.5})
    return {"B": 0.75, "K1": 1.5}

@app.route('/suggest')
def suggest():
    try:
        if 'username' not in session:
            return jsonify({"error": "您必须登录才能获取建议"}), 401
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify([])
        username = session['username']
        user_interests = analyze_user_interests(username)
        log_file = 'query_logs.json'
        if not os.path.exists(log_file):
            return jsonify([])
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        suggestions_set = set()
        suggestions = []
        user_logs = [log for log in logs if log['username'] == username]
        for log in user_logs:
            log_q = log.get('query', '')
            if log_q.lower().startswith(q.lower()) and log_q not in suggestions_set:
                suggestions_set.add(log_q)
                suggestions.append({
                    'query': log_q,
                    'type': 'history',
                    'weight': user_interests.get(log_q, 0)
                })
        other_logs = [log for log in logs if log['username'] != username]
        for log in other_logs:
            log_q = log.get('query', '')
            if log_q.lower().startswith(q.lower()) and log_q not in suggestions_set:
                suggestions_set.add(log_q)
                suggestions.append({
                    'query': log_q,
                    'type': 'popular',
                    'weight': 1
                })
        suggestions.sort(key=lambda x: x['weight'], reverse=True)
        return jsonify(suggestions[:5])
    except Exception as e:
        logger.error(f"搜索建议功能错误: {e}", exc_info=True)
        return jsonify({"error": "获取搜索建议失败"}), 500

@app.route('/recommend')
def recommend():
    try:
        if 'username' not in session:
            return jsonify({"error": "您必须登录才能获取推荐"}), 401
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify([])
        username = session['username']
        collaborative_recommendations = get_collaborative_recommendations(username, q)
        index_dir = "indexdir"
        content_results, _, _, _ = search_index(index_dir, q, page=1, files_only=False, username=username)
        content_recommendations = [result['title'] for result in content_results[:3]]
        recommendations = []
        seen = set()
        for i in range(max(len(collaborative_recommendations), len(content_recommendations))):
            if i < len(collaborative_recommendations) and collaborative_recommendations[i] not in seen:
                recommendations.append({
                    'query': collaborative_recommendations[i],
                    'type': 'collaborative'
                })
                seen.add(collaborative_recommendations[i])
            if i < len(content_recommendations) and content_recommendations[i] not in seen:
                recommendations.append({
                    'query': content_recommendations[i],
                    'type': 'content'
                })
                seen.add(content_recommendations[i])
            if len(recommendations) >= 5:
                break
        return jsonify(recommendations)
    except Exception as e:
        logger.error(f"推荐功能错误: {e}", exc_info=True)
        return jsonify({"error": "获取推荐失败"}), 500

if __name__ == "__main__":
    try:
        logger.info("启动 Flask 服务器...")
        app.run(debug=True, host='localhost', port=5000)
    except Exception as e:
        logger.error(f"启动服务器失败: {e}", exc_info=True)