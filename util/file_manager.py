"""
文件管理工具类
用于统一管理SchoolAgent项目的文件保存和组织
"""
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

class SchoolAgentFileManager:
    """
    SchoolAgent项目的文件管理器
    提供统一的文件保存、组织和索引功能
    """
    
    def __init__(self, base_dir: str = "results"):
        """
        初始化文件管理器
        
        Args:
            base_dir: 基础保存目录
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        
        # 定义文件夹结构
        self.folder_structure = {
            "exercises": "练习题结果",
            "memory_analysis": "记忆分析报告", 
            "evaluations": "评估结果",
            "progress": "进度记录",
            "logs": "运行日志",
            "backups": "备份文件",
            "visualizations": "可视化数据"
        }
    
    def get_student_dir(self, student_name: str, date: Optional[datetime] = None) -> Path:
        """
        获取学生的目录路径
        
        Args:
            student_name: 学生名称
            date: 日期，默认为今天
            
        Returns:
            学生目录路径
        """
        if date is None:
            date = datetime.now()
        
        date_str = date.strftime("%Y-%m-%d")
        student_dir = self.base_dir / student_name / date_str
        student_dir.mkdir(parents=True, exist_ok=True)
        
        return student_dir
    
    def get_category_dir(self, student_name: str, category: str, date: Optional[datetime] = None) -> Path:
        """
        获取特定类别的目录路径
        
        Args:
            student_name: 学生名称
            category: 文件类别
            date: 日期，默认为今天
            
        Returns:
            类别目录路径
        """
        student_dir = self.get_student_dir(student_name, date)
        category_dir = student_dir / category
        category_dir.mkdir(exist_ok=True)
        
        return category_dir
    
    def generate_unique_filename(self, student_name: str, file_type: str, 
                                postfix: str = "", extension: str = ".json") -> str:
        """
        生成唯一的文件名（避免覆盖）
        
        Args:
            student_name: 学生名称
            file_type: 文件类型
            postfix: 后缀标识
            extension: 文件扩展名
            
        Returns:
            唯一的文件名
        """
        timestamp = datetime.now().strftime("%H%M%S")
        
        # 构建文件名
        name_parts = [student_name, file_type]
        if postfix:
            name_parts.append(postfix)
        name_parts.append(timestamp)
        
        filename = "_".join(name_parts) + extension
        return filename
    
    def save_exercise_results(self, student_name: str, data: Dict[Any, Any], 
                            postfix: str = "") -> Path:
        """
        保存练习题结果
        
        Args:
            student_name: 学生名称
            data: 要保存的数据
            postfix: 文件后缀标识
            
        Returns:
            保存的文件路径
        """
        # 获取保存目录
        save_dir = self.get_category_dir(student_name, "exercises")
        
        # 生成文件名
        filename = self.generate_unique_filename(student_name, "exercise_results", postfix)
        filepath = save_dir / filename
        
        # 添加元数据
        enhanced_data = {
            "metadata": {
                "file_info": {
                    "creation_time": datetime.now().isoformat(),
                    "file_version": "2.0",
                    "file_type": "exercise_results",
                    "student_name": student_name,
                    "session_id": f"{student_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                },
                "file_structure": {
                    "relative_path": str(filepath.relative_to(self.base_dir)),
                    "category": "exercises",
                    "backup_available": False
                }
            },
            "data": data
        }
        
        # 保存文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(enhanced_data, f, ensure_ascii=False, indent=4)
        
        # 更新索引
        self._update_file_index(student_name, "exercises", filename, enhanced_data["metadata"])
        
        # 创建备份（如果需要）
        if self._should_create_backup(filepath):
            self._create_backup(filepath, student_name)
        
        return filepath
    
    def save_memory_analysis(self, student_name: str, data: Dict[Any, Any], 
                           postfix: str = "") -> Path:
        """
        保存记忆分析结果
        
        Args:
            student_name: 学生名称
            data: 要保存的数据
            postfix: 文件后缀标识
            
        Returns:
            保存的文件路径
        """
        save_dir = self.get_category_dir(student_name, "memory_analysis")
        filename = self.generate_unique_filename(student_name, "memory_analysis", postfix)
        filepath = save_dir / filename
        
        # 添加元数据
        enhanced_data = {
            "metadata": {
                "analysis_info": {
                    "creation_time": datetime.now().isoformat(),
                    "analysis_type": "memory_usage_comprehensive",
                    "student_name": student_name,
                    "version": "2.0"
                }
            },
            "analysis": data
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(enhanced_data, f, ensure_ascii=False, indent=4)
        
        self._update_file_index(student_name, "memory_analysis", filename, enhanced_data["metadata"])
        
        return filepath
    
    def save_progress_checkpoint(self, student_name: str, data: Dict[Any, Any], 
                               checkpoint_id: str) -> Path:
        """
        保存进度检查点
        
        Args:
            student_name: 学生名称
            data: 要保存的数据
            checkpoint_id: 检查点标识
            
        Returns:
            保存的文件路径
        """
        save_dir = self.get_category_dir(student_name, "progress")
        filename = self.generate_unique_filename(student_name, "progress", checkpoint_id)
        filepath = save_dir / filename
        
        checkpoint_data = {
            "checkpoint_info": {
                "timestamp": datetime.now().isoformat(),
                "checkpoint_id": checkpoint_id,
                "student_name": student_name,
                "auto_recovery": True
            },
            "progress_data": data
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=4)
        
        return filepath
    
    def get_latest_file(self, student_name: str, category: str, 
                       date: Optional[datetime] = None) -> Optional[Path]:
        """
        获取最新的文件
        
        Args:
            student_name: 学生名称
            category: 文件类别
            date: 日期，默认为今天
            
        Returns:
            最新文件的路径，如果没有文件则返回None
        """
        category_dir = self.get_category_dir(student_name, category, date)
        
        if not category_dir.exists():
            return None
        
        # 获取所有文件并按修改时间排序
        files = [f for f in category_dir.iterdir() if f.is_file() and f.suffix == '.json']
        if not files:
            return None
        
        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        return latest_file
    
    def list_student_sessions(self, student_name: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        列出学生最近的会话记录
        
        Args:
            student_name: 学生名称
            days: 查询最近几天的记录
            
        Returns:
            会话记录列表
        """
        sessions = []
        student_base_dir = self.base_dir / student_name
        
        if not student_base_dir.exists():
            return sessions
        
        # 遍历最近几天的目录
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            date_dir = student_base_dir / date_str
            
            if date_dir.exists():
                index_file = date_dir / "index.json"
                if index_file.exists():
                    with open(index_file, 'r', encoding='utf-8') as f:
                        index_data = json.load(f)
                        sessions.extend(index_data.get("sessions", []))
        
        return sorted(sessions, key=lambda x: x.get("timestamp", ""), reverse=True)
    
    def create_daily_summary(self, student_name: str, date: Optional[datetime] = None) -> Path:
        """
        创建日常总结报告
        
        Args:
            student_name: 学生名称
            date: 日期，默认为今天
            
        Returns:
            总结报告文件路径
        """
        if date is None:
            date = datetime.now()
        
        student_dir = self.get_student_dir(student_name, date)
        summary_file = student_dir / f"daily_summary_{date.strftime('%Y%m%d')}.json"
        
        # 收集当天的所有活动
        daily_activities = {
            "date": date.strftime("%Y-%m-%d"),
            "student_name": student_name,
            "summary": {
                "exercises_completed": 0,
                "analysis_reports": 0,
                "progress_checkpoints": 0,
                "total_files": 0
            },
            "file_list": [],
            "performance_highlights": []
        }
        
        # 统计各类文件
        for category in self.folder_structure.keys():
            category_dir = student_dir / category
            if category_dir.exists():
                files = list(category_dir.glob("*.json"))
                daily_activities["summary"][f"{category}_count"] = len(files)
                daily_activities["file_list"].extend([
                    {
                        "category": category,
                        "filename": f.name,
                        "size_kb": round(f.stat().st_size / 1024, 2),
                        "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                    }
                    for f in files
                ])
        
        daily_activities["summary"]["total_files"] = len(daily_activities["file_list"])
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(daily_activities, f, ensure_ascii=False, indent=4)
        
        return summary_file
    
    def _update_file_index(self, student_name: str, category: str, 
                          filename: str, metadata: Dict[str, Any]) -> None:
        """
        更新文件索引
        
        Args:
            student_name: 学生名称
            category: 文件类别
            filename: 文件名
            metadata: 元数据
        """
        student_dir = self.get_student_dir(student_name)
        index_file = student_dir / "index.json"
        
        # 读取或创建索引
        if index_file.exists():
            with open(index_file, 'r', encoding='utf-8') as f:
                index = json.load(f)
        else:
            index = {
                "student_name": student_name,
                "created": datetime.now().isoformat(),
                "sessions": []
            }
        
        # 添加新记录
        session_record = {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "filename": filename,
            "metadata": metadata
        }
        
        index["sessions"].append(session_record)
        
        # 保持最近50条记录
        if len(index["sessions"]) > 50:
            index["sessions"] = index["sessions"][-50:]
        
        # 保存索引
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    
    def _should_create_backup(self, filepath: Path) -> bool:
        """
        判断是否需要创建备份
        
        Args:
            filepath: 文件路径
            
        Returns:
            是否需要备份
        """
        # 大于1MB的文件创建备份
        file_size_mb = filepath.stat().st_size / (1024 * 1024)
        return file_size_mb > 1.0
    
    def _create_backup(self, filepath: Path, student_name: str) -> None:
        """
        创建文件备份
        
        Args:
            filepath: 源文件路径
            student_name: 学生名称
        """
        backup_dir = self.get_category_dir(student_name, "backups")
        backup_filename = f"backup_{filepath.stem}_{datetime.now().strftime('%H%M%S')}{filepath.suffix}"
        backup_path = backup_dir / backup_filename
        
        # 复制文件
        import shutil
        shutil.copy2(filepath, backup_path)
        
        print(f"📦 已创建备份: {backup_path}")
    
    def cleanup_old_files(self, student_name: str, days_to_keep: int = 30) -> None:
        """
        清理旧文件
        
        Args:
            student_name: 学生名称
            days_to_keep: 保留天数
        """
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        student_base_dir = self.base_dir / student_name
        
        if not student_base_dir.exists():
            return
        
        # 遍历日期目录
        for date_dir in student_base_dir.iterdir():
            if date_dir.is_dir() and date_dir.name != "backups":
                try:
                    dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
                    if dir_date < cutoff_date:
                        # 移动到备份目录而不是删除
                        backup_dir = self.get_category_dir(student_name, "backups")
                        archive_name = f"archived_{date_dir.name}_{datetime.now().strftime('%H%M%S')}"
                        import shutil
                        shutil.move(str(date_dir), str(backup_dir / archive_name))
                        print(f"🗄️ 已归档旧目录: {date_dir.name}")
                except ValueError:
                    # 不是日期格式的目录，跳过
                    continue


# 全局文件管理器实例
file_manager = SchoolAgentFileManager()


def get_file_manager() -> SchoolAgentFileManager:
    """获取全局文件管理器实例"""
    return file_manager
