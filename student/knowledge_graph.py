"""Knowledge Graph (轻量内存版)
=================================
用于管理学生-概念-题目-掌握度。后续可替换成 Neo4j / SQLite / 图数据库。

核心功能:
1. 概念/题目/学生注册
2. 题目与概念(多权重)关联
3. 记录作答 Attempt 并更新 mastery (掌握度 p∈(0,1))
4. 指数遗忘衰减 + Logistic 增量更新 + streak 调整稳定度
5. 简单推荐（找中等掌握度或低覆盖概念）
6. JSON 持久化（可选调用）

后续可扩展:
- 引入 BKT / Elo / Performance Factor 模型
- 针对 Exercise 设置动态难度
- 添加资源(Lesson)覆盖关系
- 多学生群体统计、概念合并/拆分版本控制

使用示例:
-----------
from student.knowledge_graph import kg
kg.add_student('S1')
kg.add_concept('fractions-basic', name='分数基础')
kg.add_concept('fraction-add', name='分数加法')
kg.link_prerequisite('fractions-basic', 'fraction-add', weight=0.8)
kg.add_exercise('ex1', concepts={'fractions-basic':1.0}, difficulty=0.4)
kg.record_attempt('S1', 'ex1', correct=True, time_spent=32)
print(kg.get_mastery('S1', 'fractions-basic'))
print(kg.recommend_concepts('S1'))

注意:
- 本文件为无依赖纯 Python 结构，适合快速集成与迭代。
- 多线程下请在外层加锁；当前未做线程安全。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import math
import time
import json
from pathlib import Path
from collections import defaultdict
from util.file_manager import get_file_manager
from student.global_methods import *
from student.cognitive_module.student import load_grade_knowledge_points
import re



# =============================
# 数据类定义
# =============================
@dataclass
class Concept:
    id: str
    name: Optional[str] = None
    parent_id: Optional[str] = None
    # tags: List[str] = field(default_factory=list)
    # metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Exercise:
    id: str
    difficulty: float = 0.5  # 0~1 中心 0.5
    concepts: Dict[str, float] = field(default_factory=dict)  # concept_id -> weight
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Student:
    id: str
    profile: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Attempt:
    id: str
    student_id: str
    exercise_id: str
    correct: bool
    time_spent: float
    timestamp: float
    raw: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MasteryRecord:
    student_id: str
    concept_id: str
    concept_name: str
    misconceptions: List[str] = field(default_factory=list) # 迷思
    p: float = 0.3                 # 初始掌握度 (可配置)
    last_update: float = field(default_factory=lambda: time.time())
    stability: float = 0.0         # 反映长期巩固程度
    streak: int = 0                # 连续正确计数
    decay_lambda: float = 0.04     # 遗忘率(天)

    def decay(self, now: Optional[float] = None) -> None:
        """指数衰减: p <- p * exp(-λ * Δt)"""
        now = now or time.time()
        dt_days = (now - self.last_update) / 86400.0
        if dt_days <= 0:
            return
        self.p *= math.exp(-self.decay_lambda * dt_days / (1 + self.stability))
        self.p = max(0.01, min(0.99, self.p))
        self.last_update = now  # 衰减后立即更新时间，避免重复多次衰减

# =============================
# 知识图谱主类
# =============================
class KnowledgeGraph:
    def __init__(self):
        # 核心容器
        self.students: Dict[str, Student] = {}
        self.concepts: Dict[str, Concept] = {}
        self.exercises: Dict[str, Exercise] = {}
        self.prerequisites: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.attempts: List[Attempt] = []
        self.mastery: Dict[Tuple[str, str], MasteryRecord] = {}
        # 资源
        self._file_mgr = None  # 延迟获取，避免循环导入
        # 配置
        self.auto_save_enabled = True  # 每次更新后自动保存（覆盖式）
        

    # ---------- 基础注册 ----------
    def add_student(self, student_id: str, **profile):
        if student_id not in self.students:
            self.students[student_id] = Student(student_id, profile)
        else:
            self.students[student_id].profile.update(profile)

    def add_concept(self, concept_id: str, name: str, parent_id: str):
        if concept_id not in self.concepts:
            self.concepts[concept_id] = Concept(concept_id, name, parent_id)
        else:
            c = self.concepts[concept_id]
            c.name = name
            c.parent_id = parent_id
            # c.tags = list(set(c.tags).union(tags))
            # c.metadata.update(metadata)

    def link_prerequisite(self, pre_id: str, post_id: str, weight: float = 1.0):
        if pre_id not in self.concepts or post_id not in self.concepts:
            raise ValueError("概念未注册: {}/{}".format(pre_id, post_id))
        self.prerequisites[pre_id][post_id] = max(0.0, min(1.0, weight))

    def add_exercise(self, exercise_id: str, *, concepts: Dict[str, float], difficulty: float = 0.5, **metadata):
        # 归一化权重
        if not concepts:
            raise ValueError("题目必须关联至少一个概念")
        total = sum(concepts.values())
        norm = {cid: w / total for cid, w in concepts.items()}
        # 校验概念存在
        for cid in norm.keys():
            if cid not in self.concepts:
                raise ValueError(f"概念未注册: {cid}")
        self.exercises[exercise_id] = Exercise(exercise_id, difficulty, norm, metadata)

    # ---------- Mastery 访问 ----------
    # 添加迷思，名字
    def _get_or_create_mastery(self, student_id: str, concept_id: str,config_kg: dict, misconceptions: Optional[str] = None) -> MasteryRecord:
        key = (student_id, concept_id)
        rec = self.mastery.get(key)
        if rec is None:
            # 从 config_kg 获取概念名称: config_kg[concept_id] = (name, parent_id)
            concept_name = config_kg.get(concept_id, (concept_id, None))[0]
            rec = MasteryRecord(
                student_id=student_id, 
                concept_id=concept_id, 
                concept_name=concept_name, 
                misconceptions=[misconceptions] if misconceptions else []
            )
            self.mastery[key] = rec
        return rec

    def get_mastery(self, student_id: str, concept_id: str) -> Optional[float]:
        rec = self.mastery.get((student_id, concept_id))
        return rec.p if rec else None

    def get_student_profile_mastery(self, student_id: str) -> Dict[str, float]:
        return {rec.concept_name: rec.p for (sid, cid), rec in self.mastery.items() if sid == student_id}
    
    def get_student_profile_misconceptions(self, student_id: str) -> Dict[str, List[str]]:
        return {rec.concept_name: rec.misconceptions for (sid, cid), rec in self.mastery.items() if sid == student_id}

    # ---------- Attempt & 更新 ----------
    # TODO：如果后续要实现这部分，则再来实现。
    def record_attempt(
        self,
        student_id: str,
        exercise_id: str,
        *,
        correct: bool,
        time_spent: float,
        timestamp: Optional[float] = None,
        raw: Optional[Dict[str, Any]] = None,
        update: bool = True,
    persist_stream: bool = False,
    ) -> Attempt:
        if student_id not in self.students:
            raise ValueError(f"学生未注册: {student_id}")
        if exercise_id not in self.exercises:
            raise ValueError(f"题目未注册: {exercise_id}")
        timestamp = timestamp or time.time()
        attempt_id = f"{student_id}-{exercise_id}-{int(timestamp*1000)}"
        attempt = Attempt(
            id=attempt_id,
            student_id=student_id,
            exercise_id=exercise_id,
            correct=bool(correct),
            time_spent=float(time_spent),
            timestamp=timestamp,
            raw=raw or {},
        )
        self.attempts.append(attempt)
        if update:
            self._update_mastery_for_attempt(attempt)
        if persist_stream:
            # 直接写 JSONL 流 (只写精简字段 + mastery snapshot for involved concepts)
            if self._file_mgr is None:
                self._file_mgr = get_file_manager()
            mastery_snapshot = {
                cid: self.mastery[(student_id, cid)].p
                for cid in self.exercises[exercise_id].concepts.keys()
                if (student_id, cid) in self.mastery
            }
            self._file_mgr.append_knowledge_graph_attempt({
                "attempt_id": attempt.id,
                "student_id": student_id,
                "exercise_id": exercise_id,
                "correct": attempt.correct,
                "time_spent": attempt.time_spent,
                "timestamp": attempt.timestamp,
                "concepts": list(self.exercises[exercise_id].concepts.keys()),
                "mastery_after": mastery_snapshot,
            })
        # 自动保存（避免生成海量快照：覆盖固定文件）
        if self.auto_save_enabled:
            self._auto_save_compact()
        return attempt

    # 核心更新逻辑
    def _update_mastery_for_attempt(self, attempt: Attempt):
        ex = self.exercises[attempt.exercise_id]
        for cid, weight in ex.concepts.items():
            rec = self._get_or_create_mastery(attempt.student_id, cid)
            # 1. 衰减
            rec.decay(now=attempt.timestamp)
            # 2. Logistic 增量
            #   z = logit(p) + α*(outcome-0.5) + β*(0.5-difficulty) * weight 调整
            outcome = 1.0 if attempt.correct else 0.0
            z = math.log(rec.p / (1 - rec.p))
            alpha = 1.0 * weight          # 概念权重放大作用
            beta = 0.6 * weight
            z_new = z + alpha * (outcome - 0.5) + beta * (0.5 - ex.difficulty)
            p_new = 1 / (1 + math.exp(-z_new))
            # 3. 连续正确 streak & 稳定度
            if attempt.correct:
                rec.streak += 1
                if rec.streak >= 3:  # 达到阈值 -> 提升稳定度并降低遗忘率
                    rec.streak = 0
                    rec.stability += 1
                    rec.decay_lambda *= 0.9  # 忘记更慢
            else:
                rec.streak = 0
                # 失败惩罚: 轻微下调稳定 & 提高遗忘率(上限)
                rec.stability = max(0.0, rec.stability - 0.2)
                rec.decay_lambda = min(0.08, rec.decay_lambda * 1.05)
            # 4. 边界
            rec.p = max(0.01, min(0.99, p_new))
            rec.last_update = attempt.timestamp

    # ---------- 推荐 ----------
    def recommend_concepts(self, student_id: str, top_k: int = 5, mode: str = "weak") -> List[Tuple[str, float]]:
        """根据模式推荐概念
        mode:
          weak: 最低掌握度 (p 升序)
          reinforce: 中等区间(0.4~0.7) 优先 (最接近 0.55)
          review: 较高但久未更新
        """
        now = time.time()
        recs = []
        for cid in self.concepts:
            rec = self.mastery.get((student_id, cid))
            if not rec:
                # 未练过 -> 高优先
                recs.append((cid, 0.0, 0.0, 999999))  # (cid, p, score, age)
                continue
            age_days = (now - rec.last_update) / 86400.0
            p = rec.p
            if mode == "weak":
                score = p  # 直接按 p 升序
            elif mode == "reinforce":
                if 0.35 <= p <= 0.75:
                    score = abs(p - 0.55)  # 越接近0.55越好 -> 后面再反排序
                else:
                    score = 999
            elif mode == "review":
                score = -age_days + (1 - p) * 0.2  # 时间主导 + 少量p调节
            else:
                score = p
            recs.append((cid, p, score, age_days))
        if mode == "weak":
            recs.sort(key=lambda x: x[1])  # p 升序
        elif mode == "reinforce":
            recs = [r for r in recs if r[2] != 999]
            recs.sort(key=lambda x: x[2])
        elif mode == "review":
            recs.sort(key=lambda x: x[2], reverse=True)
        # 返回 (concept_id, p)
        return [(cid, round(p, 4)) for cid, p, _, _ in recs[:top_k]]

    # ---------- 分析 / 统计 ----------
    def student_summary(self, student_id: str) -> Dict[str, Any]:
        ms = {cid: rec for (sid, cid), rec in self.mastery.items() if sid == student_id}
        if not ms:
            return {"student": student_id, "concepts_tracked": 0, "avg_mastery": None}
        avg_p = sum(r.p for r in ms.values()) / len(ms)
        return {
            "student": student_id,
            "concepts_tracked": len(ms),
            "avg_mastery": round(avg_p, 4),
            "low_concepts": [cid for cid, r in ms.items() if r.p < 0.4],
            "high_concepts": [cid for cid, r in ms.items() if r.p > 0.8],
        }

    # ---------- 被动学习（感知阶段非答题强化） ----------
    # 添加迷思
    def passive_learn(self, student_id: str, concept_id: str, *, strength: float = 0.05, config_kg: dict, misconceptions: Optional[str] = None, timestamp: Optional[float] = None):
        """学生被动接触某概念(听课/讨论)，给予小幅掌握度提升。

        规则:
        - 自动创建学生 & 概念 mastery 记录
        - 先执行衰减，再执行提升: p <- p + (1-p)*strength
        - stability 微增: +strength*0.5
        - strength 建议 0.01~0.15 之间
        - config_kg 格式为字典，{id: (name, parent_id)}
        """
        if student_id not in self.students:
            self.add_student(student_id)
        if concept_id not in self.concepts:
            self.add_concept(concept_id, name=config_kg.get(concept_id, (concept_id, None))[0], parent_id=config_kg.get(concept_id, (None, None))[1])
        # 如果祖先概念存在，则进行关联
        if self.concepts[concept_id].parent_id in self.concepts:
            parent_id = self.concepts[concept_id].parent_id
            # 建立前置关系，默认权重 0.3
            if concept_id not in self.prerequisites[parent_id]:
                self.link_prerequisite(parent_id, concept_id, weight=0.3)
        rec = self._get_or_create_mastery(student_id, concept_id, config_kg, misconceptions=misconceptions)
        ts = timestamp or time.time()
        # 添加迷思
        if misconceptions and misconceptions not in rec.misconceptions:
            rec.misconceptions.append(misconceptions)
        # 衰减到当前时间点
        rec.decay(now=ts)
        strength = max(0.005, min(0.2, strength))
         # 提升（向1靠近）
        rec.p = rec.p + (1 - rec.p) * strength
        rec.p = max(0.01, min(0.99, rec.p))
        rec.stability += strength * 0.5
        rec.last_update = ts
        if self.auto_save_enabled:
            self._auto_save_compact()

    # 添加迷思
    def batch_passive_learn(self, student_id: str, concept_ids: List[str], *, base_strength: float = 0.04, config_kg: dict, misconceptions: Optional[str] = None,importance: Optional[int] = None):
        """批量被动学习，importance 可放大总体强度。"""
        if not concept_ids:
            return
        factor = 1.0
        if importance is not None:
            # importance 期望 1~10 之间，映射到 0.5~1.5 倍
            factor = 0.5 + min(max(importance, 1), 10) / 10.0
        for cid in concept_ids:
            s = base_strength * factor
            self.passive_learn(student_id, cid, strength=s, config_kg=config_kg, misconceptions=misconceptions)
        # batch 内 passive_learn 已各自触发 autosave；如需合并写入可改为禁用内部再统一写一次

    # ---------- 自动保存实现 ----------
    def _auto_save_compact(self):
        """覆盖写单一 autosave 文件，避免快照爆炸。"""
        if self._file_mgr is None:
            self._file_mgr = get_file_manager()
        # 使用 __global__ & knowledge_graph 目录
        target_dir = self._file_mgr.get_category_dir('__global__', 'knowledge_graph')
        path = target_dir / 'kg_autosave.json'
        data = self.to_dict()
        data['metadata'] = {
            'type': 'autosave',
            'updated': time.time(),
            'students': len(self.students),
            'concepts': len(self.concepts),
            'exercises': len(self.exercises),
            'mastery_edges': len(self.mastery),
            'attempts': len(self.attempts)
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------- 持久化 ----------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "students": {sid: s.profile for sid, s in self.students.items()},
            "concepts": {cid: {"name": c.name, "parent_id": c.parent_id} for cid, c in self.concepts.items()},
            "exercises": {
                eid: {"difficulty": e.difficulty, "concepts": e.concepts, "metadata": e.metadata}
                for eid, e in self.exercises.items()
            },
            "prerequisites": self.prerequisites,
            "mastery": {
                f"{sid}::{rec.concept_name}": {
                    "id": cid,
                    "misconceptions": rec.misconceptions,
                    "p": rec.p,
                    "last_update": rec.last_update,
                    "stability": rec.stability,
                    "streak": rec.streak,
                    "decay_lambda": rec.decay_lambda,
                }
                for (sid, cid), rec in self.mastery.items()
            },
            "attempts": [
                {
                    "id": a.id,
                    "student_id": a.student_id,
                    "exercise_id": a.exercise_id,
                    "correct": a.correct,
                    "time_spent": a.time_spent,
                    "timestamp": a.timestamp,
                }
                for a in self.attempts
            ],
        }

    def save_json(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    # ---- 集成统一文件管理器存储 ----
    def snapshot(self, postfix: str = "") -> Path:
        """通过项目 file_manager 保存快照"""
        if self._file_mgr is None:
            self._file_mgr = get_file_manager()
        return self._file_mgr.save_knowledge_graph_snapshot(self, postfix=postfix)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeGraph':
        """从字典数据反序列化知识图谱
        
        支持两种数据格式:
        
        1. 标准格式 (to_dict() 输出):
           - students: {sid: profile_dict}
           - concepts: {cid: {"name": str, "parent_id": str}}
           - exercises: {eid: {"difficulty": float, "concepts": dict, "metadata": dict}}
           - prerequisites: {pre_id: {post_id: weight}}
           - mastery: {"sid::cid": {"p": float, "last_update": float, ...}}
           - attempts: [{"id": str, "student_id": str, ...}] (可选)
        
        2. nodes.json 格式 (记忆系统):
           - node_1: {"type": "knowledge", "knowledge_tag": [...], "content": "...", ...}
           - node_2: {"type": "chat", ...}
           ...
           当检测到此格式时,会从 type="knowledge" 的节点中提取概念
        """
        kg = cls()
        
        # 检测数据格式: 如果所有键都是 "node_X" 格式,则是 nodes.json
        is_nodes_format = False
        if data:
            sample_keys = list(data.keys())[:5]  # 检查前5个键
            is_nodes_format = all(key.startswith("node_") for key in sample_keys)
        
        if is_nodes_format:
            # 从 nodes.json 格式恢复 - 提取所有 type="knowledge" 的节点并把 knowledge_tag 列表中的每一项作为概念
            for node_id, node_data in data.items():
                if not isinstance(node_data, dict):
                    continue

                node_type = node_data.get("type")
                if node_type != "knowledge":
                    continue

                knowledge_tags = node_data.get("knowledge_tag")
                if not knowledge_tags:
                    # 有些知识节点可能把标签放在 keywords 或者 content 中，暂不处理
                    continue

                # knowledge_tag 可能是列表或单个字符串
                tags = []
                if isinstance(knowledge_tags, list):
                    tags = knowledge_tags
                elif isinstance(knowledge_tags, str):
                    tags = [knowledge_tags]

                for concept_name in tags:
                    if not isinstance(concept_name, str):
                        continue
                    concept_name = concept_name.strip()
                    if not concept_name:
                        continue

                    # 生成概念ID: 将空白替换为下划线, 其它非字母数字下划线连字符的字符替换为下划线
                    candidate = re.sub(r"\s+", "_", concept_name)
                    candidate = re.sub(r"[^0-9A-Za-z_\-]", "_", candidate)
                    concept_id = candidate

                    # 避免重复添加相同概念
                    if concept_id not in kg.concepts:
                        kg.concepts[concept_id] = Concept(
                            id=concept_id,
                            name=concept_name,
                            parent_id=None  # nodes.json 中通常没有层级信息
                        )
        
        else:
            # 从标准格式恢复
            # 1. 恢复学生
            for sid, profile in data.get('students', {}).items():
                kg.add_student(sid, **profile)
            
            # 2. 恢复概念（必须先恢复所有概念，再建立前置关系）
            for cid, cdata in data.get('concepts', {}).items():
                kg.add_concept(
                    concept_id=cid,
                    name=cdata.get('name', cid),  # 如果没有name，使用id作为name
                    parent_id=cdata.get('parent_id')  # parent_id可以为None
                )
            
            # 3. 恢复题目
            for eid, edata in data.get('exercises', {}).items():
                kg.add_exercise(
                    exercise_id=eid,
                    concepts=edata.get('concepts', {}),
                    difficulty=edata.get('difficulty', 0.5),
                    **edata.get('metadata', {})
                )
            
            # 4. 恢复前置关系
            # prerequisites 格式: {pre_id: {post_id: weight, ...}, ...}
            prereqs = data.get('prerequisites', {})
            if isinstance(prereqs, dict):
                kg.prerequisites = defaultdict(dict)
                for pre_id, posts in prereqs.items():
                    if isinstance(posts, dict):
                        for post_id, weight in posts.items():
                            kg.prerequisites[pre_id][post_id] = weight
            
            # 5. 恢复掌握度记录
            for key, m in data.get('mastery', {}).items():
                # 解析复合键 "sid::concept_name"
                if '::' not in key:
                    continue  # 跳过格式不正确的键
                
                parts = key.split('::', 1)
                if len(parts) != 2:
                    continue
                    
                sid, concept_name = parts  # 注意: 键中存的是 concept_name, 不是 concept_id
                
                # 从数据中获取真正的 concept_id
                concept_id = m.get('id')
                if not concept_id:
                    continue  # 如果没有 id 字段,跳过
                
                # 创建掌握度记录 (注意参数顺序: student_id, concept_id, concept_name)
                rec = MasteryRecord(sid, concept_id, concept_name)
                rec.misconceptions = m.get('misconceptions', [])
                rec.p = m.get('p', 0.3)
                rec.last_update = m.get('last_update', time.time())
                rec.stability = m.get('stability', 0.0)
                rec.streak = m.get('streak', 0)
                rec.decay_lambda = m.get('decay_lambda', 0.04)
                
                # 注意: mastery 的键是 (student_id, concept_id), 不是 concept_name
                kg.mastery[(sid, concept_id)] = rec
            
            # 6. 恢复 attempts（可选，通常历史记录量大，可按需恢复）
            for a_data in data.get('attempts', []):
                attempt = Attempt(
                    id=a_data.get('id', ''),
                    student_id=a_data.get('student_id', ''),
                    exercise_id=a_data.get('exercise_id', ''),
                    correct=a_data.get('correct', False),
                    time_spent=a_data.get('time_spent', 0.0),
                    timestamp=a_data.get('timestamp', time.time()),
                    raw=a_data.get('raw', {})
                )
                kg.attempts.append(attempt)
        
        return kg

    @classmethod
    def load_json(cls, path: str | Path) -> 'KnowledgeGraph':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    # ---- 知识图谱的查找 ----
    def get_id_by_name(self, target_name: str, config_kg: dict) -> Optional[str]:
        """即根据config_kp, 通过名称得到概念 ID（返回第一个匹配）"""
        for cid, (name, parent_id) in config_kg.items():
            if name == target_name:
                return cid
        return None
    
    def get_batch_id_by_names(self, target_names: List[str], config_kg: dict) -> List[str]:
        """批量根据知识点名称得到概念 ID 列表"""
        ids = []
        name_to_id = {name: cid for cid, (name, _) in config_kg.items()}
        for name in target_names:
            if name in name_to_id:
                ids.append(name_to_id[name])
        return ids

# 单例实例 (方便直接导入使用)
kg = KnowledgeGraph()

# 如果你需要在现有答题流程里接入：
# 1. 在处理每题后调用 kg.record_attempt(student_id, exercise_id, correct=..., time_spent=..., raw=answer_dict)
# 2. 题目需提前通过 kg.add_exercise 注册（可在加载题库时一次性注册）
# 3. 在保存统计时输出 kg.student_summary(student.name)

if __name__ == '__main__':  # 简单自测
    kg.add_student('S1')
    kg.add_concept('c1', name='分数基础')
    kg.add_concept('c2', name='分数加法')
    kg.link_prerequisite('c1', 'c2', 0.8)
    kg.add_exercise('e1', concepts={'c1': 1.0}, difficulty=0.5)
    kg.add_exercise('e2', concepts={'c1': 0.4, 'c2': 0.6}, difficulty=0.6)
    for i in range(5):
        kg.record_attempt('S1', 'e1', correct=(i % 2 == 0), time_spent=30)
    kg.record_attempt('S1', 'e2', correct=True, time_spent=45)
    print('Summary:', kg.student_summary('S1'))
    print('Recommend (weak):', kg.recommend_concepts('S1', mode='weak'))
    p = kg.get_mastery('S1', 'c1')
    print('Mastery c1:', p)
