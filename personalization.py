import json
import math
from collections import Counter
from datetime import datetime, timedelta

def analyze_user_interests(username):
    """分析用户兴趣特征"""
    try:
        with open('query_logs.json', 'r', encoding='utf-8') as f:
            logs = json.load(f)
        
        # 获取用户最近30天的搜索记录
        recent_date = datetime.now() - timedelta(days=30)
        user_logs = [
            log for log in logs 
            if log['username'] == username and 
            datetime.fromisoformat(log['timestamp']) > recent_date
        ]
        
        # 提取关键词并计算权重
        keywords = Counter()
        for log in user_logs:
            query_terms = log['query'].split()
            # 为最近的查询赋予更高权重
            time_weight = 1 + (datetime.fromisoformat(log['timestamp']) - recent_date).days / 30.0
            for term in query_terms:
                keywords[term] += time_weight
        
        return dict(keywords)
    except Exception as e:
        print(f"分析用户兴趣时出错: {e}")
        return {}

def calculate_content_similarity(query_terms, doc_terms):
    """计算查询词与文档内容的相似度"""
    query_vector = Counter(query_terms)
    doc_vector = Counter(doc_terms)
    
    # 计算余弦相似度
    intersection = set(query_vector.keys()) & set(doc_vector.keys())
    numerator = sum(query_vector[x] * doc_vector[x] for x in intersection)
    
    sum1 = sum(query_vector[x]**2 for x in query_vector.keys())
    sum2 = sum(doc_vector[x]**2 for x in doc_vector.keys())
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    
    if not denominator:
        return 0.0
    return float(numerator) / denominator

def get_collaborative_recommendations(username, query):
    """基于协同过滤的推荐"""
    try:
        with open('query_logs.json', 'r', encoding='utf-8') as f:
            logs = json.load(f)
        
        # 找到相似用户
        user_queries = set(log['query'] for log in logs if log['username'] == username)
        user_similarities = {}
        
        for log in logs:
            other_user = log['username']
            if other_user != username:
                other_queries = set(l['query'] for l in logs if l['username'] == other_user)
                # 计算用户相似度
                similarity = len(user_queries & other_queries) / len(user_queries | other_queries) if user_queries or other_queries else 0
                user_similarities[other_user] = similarity
        
        # 获取相似用户的相关查询
        similar_queries = []
        for other_user, similarity in sorted(user_similarities.items(), key=lambda x: x[1], reverse=True)[:5]:
            other_user_logs = [log['query'] for log in logs if log['username'] == other_user]
            similar_queries.extend(other_user_logs)
        
        # 根据与当前查询的相关性排序
        query_terms = set(query.lower().split())
        recommendations = []
        for similar_query in set(similar_queries):
            similar_terms = set(similar_query.lower().split())
            similarity = len(query_terms & similar_terms) / len(query_terms | similar_terms) if query_terms or similar_terms else 0
            if similarity > 0:
                recommendations.append((similar_query, similarity))
        
        return [r[0] for r in sorted(recommendations, key=lambda x: x[1], reverse=True)[:5]]
    except Exception as e:
        print(f"获取协同推荐时出错: {e}")
        return []

def adjust_search_results(results, username, query):
    """优化后的搜索结果排序调整"""
    try:
        # 获取用户兴趣权重(带时间衰减)
        user_interests = analyze_user_interests(username)
        query_terms = query.lower().split()
        
        # 获取协同过滤推荐(去重)
        collaborative_recs = set(get_collaborative_recommendations(username, query))
        
        for result in results:
            # 基础分数
            base_score = result['score']
            
            # 提取内容关键词
            content_terms = (result['title'] + ' ' + result['content_highlight']).lower().split()
            
            # 1. 计算个性化兴趣匹配度(带时间衰减)
            interest_score = sum(
                user_interests.get(term, 0) 
                for term in content_terms
                if term in user_interests
            )
            
            # 2. 计算查询与内容的语义相似度
            similarity_score = calculate_content_similarity(query_terms, content_terms)
            
            # 3. 协同过滤推荐加成(如果在推荐列表中)
            collaborative_boost = 1.5 if any(
                rec_query.lower() in result['title'].lower() 
                for rec_query in collaborative_recs
            ) else 1.0
            
            # 4. 多样性控制(避免同一来源内容过于集中)
            source_penalty = 1.0 - (0.1 * min(
                sum(1 for r in results if r['url'].startswith(result['url'].split('/')[2])),
                3
            ))
            
            # 综合评分公式
            result['score'] = base_score * (
                1 
                + 0.25 * interest_score  # 个性化权重降低
                + 0.3 * similarity_score  # 语义相似度权重提高
            ) * collaborative_boost * source_penalty
        
        # 重新排序并限制结果数量
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:100]  # 限制返回结果数量
    except Exception as e:
        print(f"调整搜索结果时出错: {e}")
        return results