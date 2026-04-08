import os
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import hnswlib
import torch
from sklearn.metrics.pairwise import cosine_similarity

class VectorDB:
    _model_cache = {}  # 类变量，用于缓存模型
    
    def __init__(self, model_name='BAAI/bge-large-zh', model_cache_dir=None, similarity_threshold=0.85):
        """初始化向量数据库工具类"""
        self.model_name = model_name
        self.model_cache_dir = model_cache_dir or os.path.join(os.path.dirname(__file__), "model_cache")
        os.makedirs(self.model_cache_dir, exist_ok=True)
        
        # 从缓存加载模型
        self.model = self._load_or_create_model()
        self.index = None
        self.documents = []
        self.embeddings_cache = []  # 缓存已有文档的向量
        self.similarity_threshold = similarity_threshold  # 相似度阈值，超过此值认为是重复
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200, 
            separators=["\n\n", "\n", "。", "，", " ", ""]
        )
        self.init_idex = []
    
    def _load_or_create_model(self):
        """从缓存加载模型，如果缓存不存在则创建并缓存"""
        # 优先使用环境变量 BGE_MODEL_L，如果没有则使用 self.model_name
        model_name_to_use = os.getenv("BGE_MODEL_L") or self.model_name
        
        # 如果使用了环境变量，打印提示
        if os.getenv("BGE_MODEL_L"):
            print(f"Using model from environment variable BGE_MODEL_L: {model_name_to_use}")
        
        # 检查类缓存中是否有模型
        if model_name_to_use in VectorDB._model_cache:
            print(f"从内存缓存加载模型: {model_name_to_use}")
            return VectorDB._model_cache[model_name_to_use]
        
        # 检查磁盘缓存
        cache_path = os.path.join(self.model_cache_dir, model_name_to_use.replace('/', '_'))
        if os.path.exists(cache_path):
            print(f"从磁盘缓存加载模型: {cache_path}")
            model = SentenceTransformer(cache_path)
        else:
            print(f"首次加载模型: {model_name_to_use}")
            model = SentenceTransformer(model_name_to_use)
            # 保存到磁盘缓存
            model.save(cache_path)
            print(f"已将模型保存至: {cache_path}")
        
        # 添加到内存缓存
        VectorDB._model_cache[model_name_to_use] = model
        return model
    
    def encode(self, texts):
        """使用本地模型进行编码"""
        if not texts:
            return np.array([])
        return self.model.encode(texts, normalize_embeddings=True)
    
    def _is_duplicate(self, new_embedding, existing_embeddings, threshold=None):
        """检查新的向量是否与现有向量重复"""
        if threshold is None:
            threshold = self.similarity_threshold
            
        # 保险处理输入类型
        if existing_embeddings is None or len(existing_embeddings) == 0:
            return False, -1
        
        # 确保 numpy 数组
        existing_embs = np.array(existing_embeddings)
        # 如果已有索引且数据量较大，使用索引查询最近邻
        try:
            if self.index is not None:
                ids, distances = self.index.knn_query(new_embedding.reshape(1, -1), k=1)
                idx = int(ids[0][0])
                sim = 1.0 - float(distances[0][0])  # hnswlib cosine distance -> similarity
                return (sim > threshold), idx
        except Exception:
            # 如果索引查询出错，回退到精确计算
            pass

        # 精确计算（适用于小规模或索引不可用时）
        similarities = cosine_similarity([new_embedding], existing_embs)[0]
        max_similarity = float(np.max(similarities))
        max_index = int(np.argmax(similarities))
        
        return max_similarity > threshold, max_index

    def _remove_duplicates_from_embeddings(self, embeddings, documents, threshold=None):
        """从嵌入向量列表中移除重复项"""
        if threshold is None:
            threshold = self.similarity_threshold
            
        if len(embeddings) <= 1:
            return embeddings, documents
            
        unique_embeddings = []
        unique_documents = []
        duplicate_count = 0
        
        for i, (embedding, doc) in enumerate(zip(embeddings, documents)):
            is_dup, _ = self._is_duplicate(embedding, unique_embeddings, threshold)
            
            if not is_dup:
                unique_embeddings.append(embedding)
                unique_documents.append(doc)
            else:
                duplicate_count += 1
                
        if duplicate_count > 0:
            print(f"已去除 {duplicate_count} 个重复的文本块")
            
        return np.array(unique_embeddings), unique_documents

    def create_from_text(self, text: str, metadata: dict = None, init: bool = False, enable_dedup: bool = True, allow_split: bool = True):  # fix: 增加 allow_split 参数
        """
        从文本创建向量数据库，或者添加文本到现有的向量数据库
        
        Args:
            text: 输入文本
            metadata: 元数据
            init: 是否存储初始索引用于后续删除操作
            enable_dedup: 是否启用智能去重
            allow_split: 是否对长文本进行分块（默认 True）
        
        Returns:
            int: 实际添加的文档数量
        """
        if not text or text.strip() == "":
            print("警告: 向量数据库输入文本为空")
            return 0
            
        # 文本分块（可选）
        if allow_split:
            texts = self.text_splitter.split_text(text)
        else:
            texts = [text]
        if not texts:
            print("警告: 分块后文本为空")
            return 0
            
        # 为每个文本块创建Documents对象
        docs = []
        for i, text_chunk in enumerate(texts):
            chunk_metadata = {"chunk_id": len(self.documents) + i}
            if metadata:
                chunk_metadata.update(metadata)
            doc = Document(page_content=text_chunk, metadata=chunk_metadata)
            docs.append(doc)
        
        # 使用本地模型编码
        embeddings = self.encode([doc.page_content for doc in docs])
        
        if enable_dedup:
            # 去除与现有文档的重复
            if len(self.embeddings_cache) > 0:
                final_embeddings = []
                final_docs = []
                duplicate_count = 0
                
                for embedding, doc in zip(embeddings, docs):
                    is_dup, dup_index = self._is_duplicate(embedding, self.embeddings_cache)
                    
                    if not is_dup:
                        final_embeddings.append(embedding)
                        final_docs.append(doc)
                    else:
                        duplicate_count += 1
                        print(f"发现重复文档，与已有文档 {dup_index} 相似度过高")
                
                if duplicate_count > 0:
                    print(f"与现有文档去重，移除了 {duplicate_count} 个重复文本块")
                    
                embeddings = np.array(final_embeddings)
                docs = final_docs
        
        if len(embeddings) == 0:
            print("所有文本块都被识别为重复，未添加任何内容")
            return 0
        
        # 创建HNSW索引
        dimension = embeddings.shape[1]
        if self.index is None:
            self.index = hnswlib.Index(space='cosine', dim=dimension)
            self.index.init_index(max_elements=10000, ef_construction=200, M=16)
        
        # 添加向量到索引
        start_idx = len(self.documents)
        ids = np.arange(start_idx, start_idx + len(embeddings))
        self.index.add_items(embeddings, ids)
        
        # 保存文档和向量缓存
        self.documents.extend(docs)
        self.embeddings_cache.extend(embeddings.tolist())
        
        # 记录初始索引
        if init:
            for i in range(start_idx, start_idx + len(embeddings)):
                self.init_idex.append(i)
        
        print(f"已添加 {len(docs)} 个文本块到向量数据库")
        return len(docs)

    def search(self, query, k=3):
        """
        input: str
        output: list of Document
        在向量数据库中搜索与查询最相似的文档
        """
        if self.index is None or not self.documents:
            print("警告: 向量数据库为空")
            return []
        
        if query == "":
            print("警告: 查询字符串为空")
            return []
        
        # 编码查询
        query_vector = self.encode([query])
        
        # 搜索
        ids, distances = self.index.knn_query(query_vector, k=min(k, len(self.documents)))
        
        # 返回结果
        results = []
        for idx in ids[0]:
            if 0 <= idx < len(self.documents):
                results.append(self.documents[idx])
        
        return results
    
    
    def save(self, path):
        """保存向量数据库"""
        # 创建目录(如果不存在)
        os.makedirs(path, exist_ok=True)
        
        # 保存文档
        docs_path = os.path.join(path, "documents.pkl")
        with open(docs_path, "wb") as f:
            pickle.dump(self.documents, f)
        
        # 保存嵌入向量缓存
        embeddings_path = os.path.join(path, "embeddings_cache.pkl")
        with open(embeddings_path, "wb") as f:
            pickle.dump(self.embeddings_cache, f)
        
        # 保存初始索引
        init_index_path = os.path.join(path, "init_index.pkl")
        with open(init_index_path, "wb") as f:
            pickle.dump(self.init_idex, f)
        
        # 保存配置信息
        config_path = os.path.join(path, "config.pkl")
        config = {
            "model_name": self.model_name,
            "similarity_threshold": self.similarity_threshold,
            "has_index": self.index is not None
        }
        
        if self.index is not None:
            # 保存索引
            index_path = os.path.join(path, "index.bin")
            self.index.save_index(index_path)
            
            # 添加索引相关配置
            config.update({
                "dim": self.index.dim,
                "space": "cosine",
                "max_elements": self.index.get_max_elements()
            })
        
        with open(config_path, "wb") as f:
            pickle.dump(config, f)
            
        if self.index is None:
            print(f"空向量数据库已保存到: {path}")
        else:
            print(f"向量数据库已保存到: {path}")
        return True
    
    def load(self, path):
        """加载向量数据库"""
        if not os.path.exists(path):
            raise ValueError(f"路径不存在: {path}")
            
        docs_path = os.path.join(path, "documents.pkl")
        config_path = os.path.join(path, "config.pkl")
        embeddings_path = os.path.join(path, "embeddings_cache.pkl")
        init_index_path = os.path.join(path, "init_index.pkl")
        
        # 检查必要的文件
        required_files = [docs_path, config_path]
        if not all(os.path.exists(p) for p in required_files):
            raise ValueError(f"路径 {path} 中缺少必要的文件")
            
        # 加载配置
        with open(config_path, "rb") as f:
            config = pickle.load(f)
        
        # 加载文档
        with open(docs_path, "rb") as f:
            self.documents = pickle.load(f)
        
        # 加载嵌入向量缓存（如果存在）
        if os.path.exists(embeddings_path):
            with open(embeddings_path, "rb") as f:
                self.embeddings_cache = pickle.load(f)
        else:
            self.embeddings_cache = []
        
        # 加载初始索引（如果存在）
        if os.path.exists(init_index_path):
            with open(init_index_path, "rb") as f:
                self.init_idex = pickle.load(f)
        else:
            self.init_idex = []
        
        # 更新模型配置
        if "model_name" in config:
            self.model_name = config["model_name"]
        if "similarity_threshold" in config:
            self.similarity_threshold = config["similarity_threshold"]
        
        # 加载索引（如果存在）
        if config.get("has_index", False):
            index_path = os.path.join(path, "index.bin")
            if os.path.exists(index_path):
                # 初始化索引
                self.index = hnswlib.Index(space=config["space"], dim=config["dim"])
                self.index.load_index(index_path, max_elements=config["max_elements"])
            else:
                print("警告: 配置显示有索引但索引文件不存在，将重建索引")
                self.index = None
        else:
            self.index = None
        
        # 如果有文档但没有索引，重建索引
        if self.documents and self.index is None:
            print("检测到有文档但无索引，正在重建索引...")
            if not self.embeddings_cache:
                # 重新计算嵌入向量
                all_texts = [doc.page_content for doc in self.documents]
                self.embeddings_cache = self.encode(all_texts).tolist()
            
            # 重建索引
            if self.embeddings_cache:
                embeddings = np.array(self.embeddings_cache)
                dimension = embeddings.shape[1]
                self.index = hnswlib.Index(space='cosine', dim=dimension)
                self.index.init_index(max_elements=max(10000, len(embeddings)), 
                                    ef_construction=200, M=16)
                self.index.add_items(embeddings, np.arange(len(embeddings)))
        
        # 如果没有嵌入向量缓存但有文档，重新计算
        if self.documents and not self.embeddings_cache:
            all_texts = [doc.page_content for doc in self.documents]
            self.embeddings_cache = self.encode(all_texts).tolist()
            
        if self.documents:
            print(f"向量数据库已从 {path} 加载，包含 {len(self.documents)} 个文档")
        else:
            print(f"空向量数据库已从 {path} 加载")
        return True
    
    def delete_documents(self):
        """删除指定的文档"""
        if not self.init_idex or not self.documents:
            return False
        
        # 过滤要保留的文档和相应的ID
        new_documents = []
        for i, doc in enumerate(self.documents):
            if i not in self.init_idex:
                new_documents.append(doc)
            
        # 重建索引
        if new_documents:
            all_embeddings = self.encode([doc.page_content for doc in new_documents])
            dimension = all_embeddings.shape[1]
        
            # 创建新索引
            self.index = hnswlib.Index(space='cosine', dim=dimension)
            self.index.init_index(max_elements=max(10000, len(all_embeddings)), 
                             ef_construction=200, M=16)
            self.index.add_items(all_embeddings, np.arange(len(all_embeddings)))
        
        # 更新文档列表
        self.documents = new_documents
        self.init_idex = []
        return True
    
    def deduplicate_database(self, threshold=None):
        """对整个数据库进行去重操作"""
        if threshold is None:
            threshold = self.similarity_threshold
            
        if len(self.documents) <= 1:
            print("数据库中文档数量不足，无需去重")
            return 0
            
        print(f"开始对数据库进行去重，当前文档数量: {len(self.documents)}")
        
        # 重新计算所有文档的嵌入向量
        all_texts = [doc.page_content for doc in self.documents]
        all_embeddings = self.encode(all_texts)
        
        # 执行去重
        unique_embeddings, unique_documents = self._remove_duplicates_from_embeddings(
            all_embeddings, self.documents, threshold
        )
        
        removed_count = len(self.documents) - len(unique_documents)
        
        if removed_count > 0:
            # 重建索引
            dimension = unique_embeddings.shape[1]
            self.index = hnswlib.Index(space='cosine', dim=dimension)
            self.index.init_index(max_elements=max(10000, len(unique_embeddings)), 
                                ef_construction=200, M=16)
            self.index.add_items(unique_embeddings, np.arange(len(unique_embeddings)))
            
            # 更新文档列表和缓存
            self.documents = unique_documents
            self.embeddings_cache = unique_embeddings.tolist()
            
            # 更新初始索引
            if self.init_idex:
                # 简单处理：清空初始索引，因为索引已经改变
                print("警告: 去重操作后初始索引已重置")
                self.init_idex = []
            
            print(f"去重完成，移除了 {removed_count} 个重复文档，当前文档数量: {len(self.documents)}")
        else:
            print("未发现重复文档")
            
        return removed_count

    def set_similarity_threshold(self, threshold):
        """设置相似度阈值"""
        if 0.0 <= threshold <= 1.0:
            self.similarity_threshold = threshold
            print(f"相似度阈值已设置为: {threshold}")
        else:
            print("相似度阈值必须在 0.0 到 1.0 之间")

    def get_similarity_matrix(self, top_k=10):
        """获取最相似的文档对，用于调试和分析"""
        if len(self.embeddings_cache) < 2:
            return []
            
        embeddings = np.array(self.embeddings_cache)
        similarity_matrix = cosine_similarity(embeddings)
        
        # 获取最相似的文档对
        similar_pairs = []
        for i in range(len(similarity_matrix)):
            for j in range(i + 1, len(similarity_matrix)):
                similarity = similarity_matrix[i][j]
                similar_pairs.append({
                    'doc1_index': i,
                    'doc2_index': j,
                    'similarity': similarity,
                    'doc1_content': self.documents[i].page_content[:100] + "...",
                    'doc2_content': self.documents[j].page_content[:100] + "..."
                })
        
        # 按相似度排序并返回前k个
        similar_pairs.sort(key=lambda x: x['similarity'], reverse=True)
        return similar_pairs[:top_k]