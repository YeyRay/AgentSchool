# classroom_analyzer.py
from pathlib import Path
import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import pandas as pd
import os
import glob
from typing import Dict, List, Tuple
from datetime import datetime
import asyncio
from util.model import call_LLM


class ClassroomAnalyzer:
    """课堂记录和学生成绩分析器"""
    
    def __init__(self):
        self.classroom_data = None
        self.student_results = {}
        self.analysis_results = {}
        self.course_objectives = None  # 新增：存储课程目标
    
    def load_course_objectives(self, objectives_file: str):
        """加载课程目标文件"""
        try:
            with open(objectives_file, 'r', encoding='utf-8') as f:
                self.course_objectives = f.read()
            print(f"课程目标加载成功: {objectives_file}")
            return True
        except Exception as e:
            print(f"课程目标加载失败: {e}")
            return False

    def load_data_from_folder(self, classroom_file: str, student_folder: str, objectives_file: str = None,
                              datetime_str: str = None, integer_id: int = None):
        """
        从文件夹加载课堂记录、学生成绩数据和课程目标。
        根据 datetime_str 和 integer_id 动态构建学生成绩文件路径。
        """
        # 加载课堂记录
        try:
            with open(classroom_file, 'r', encoding='utf-8') as f:
                self.classroom_data = f.read()
            print(f"课堂记录加载成功: {classroom_file}")
        except Exception as e:
            print(f"课堂记录加载失败: {e}")
            return False

        # 加载课程目标（可选）
        if objectives_file:
            if not self.load_course_objectives(objectives_file):
                return False

        # 加载学生成绩文件
        if datetime_str and integer_id is not None:
            # student_folder = os.path.join(student_base_folder, datetime_str, str(integer_id))
            print(f"尝试从文件夹加载学生成绩: {student_folder}")

            # 调整文件查找模式以匹配新格式
            pattern = os.path.join(student_folder, f"*_exercise_results_{datetime_str}_{integer_id}.json")
            student_files = glob.glob(pattern)

            if not student_files:
                print(f"❌ 未找到匹配的学生成绩文件：{pattern}")
                return False

            # 假设你有一个方法来加载这些文件
            self._load_student_files(student_files)

        return True

    def load_student_data_from_folder(self, student_folder: str):
        """仅从文件夹加载学生成绩数据"""
        student_files = self._get_student_files(student_folder)
        
        if not student_files:
            print(f"在文件夹 {student_folder} 中未找到学生成绩文件")
            return False
        
        print(f"找到 {len(student_files)} 个学生成绩文件")
        for file in student_files:
            print(f"  - {os.path.basename(file)}")
        
        return self._load_student_files(student_files)

    def _get_student_files(self, folder_path):
        """从文件夹中获取所有学生成绩文件"""
        if not os.path.exists(folder_path):
            print(f"文件夹不存在: {folder_path}")
            return []

        # 查找所有 JSON 文件，并过滤出符合新命名模式的文件
        pattern = os.path.join(folder_path, "*_exercise_results_*.json")
        files = glob.glob(pattern)

        # 按文件名排序
        files.sort()
        return files

    def _load_student_files(self, student_files: List[str]):
        """加载学生成绩文件"""
        for file_path in student_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    student_data = json.load(f)

                # 从文件名提取学生名，这里假设学生名是第一个部分
                file_name = os.path.basename(file_path)
                student_name = file_name.split('_')[0]
                # 仅加载题目明细，令题号成为顶层键，符合统计逻辑
                self.student_results[student_name] = student_data.get("detailed_answers", {})
                print(f"学生成绩加载成功: {student_name}")

            except Exception as e:
                print(f"学生成绩加载失败 {file_path}: {e}")

        return len(self.student_results) > 0

    
    def _truncate_classroom_data(self, max_chars: int = 30000) -> str:
        """截断课堂记录以适应模型限制"""
        if not self.classroom_data:
            return ""
        
        if len(self.classroom_data) <= max_chars:
            return self.classroom_data
        
        # 截断并添加说明
        truncated = self.classroom_data[:max_chars]
        truncated += f"\n\n[注：原文档过长，已截断至{max_chars}字符进行分析]"
        return truncated
    
    def calculate_student_accuracy(self) -> Dict:
        """计算每个学生的正确率"""
        if not self.student_results:
            return {"error": "学生成绩数据未加载"}
        
        results = {
            "individual_accuracy": {},
            "overall_accuracy": 0.0,
            "total_students": len(self.student_results)
        }
        
        # 收集所有题目编号
        all_questions = set()
        for student_data in self.student_results.values():
            if isinstance(student_data, dict):
                all_questions.update(student_data.keys())
        
        # 过滤出数字题目编号
        numeric_questions = []
        for q in all_questions:
            try:
                numeric_questions.append(int(q))
            except (ValueError, TypeError):
                continue
        
        numeric_questions.sort()
        
        if not numeric_questions:
            return {"error": "未找到有效的题目数据"}
        
        total_correct = 0
        total_attempts = 0
        
        # 计算每个学生的正确率
        for student_name, student_data in self.student_results.items():
            if not isinstance(student_data, dict):
                continue
                
            correct = 0
            answered = 0
            
            for question_num in numeric_questions:
                question_str = str(question_num)
                if question_str in student_data:
                    answered += 1
                    question_data = student_data[question_str]
                    
                    if isinstance(question_data, dict):
                        is_correct = question_data.get("correct", False)
                    else:
                        is_correct = question_data
                    
                    if is_correct is True or is_correct == 1 or is_correct == "correct" or is_correct == "1":
                        correct += 1
            
            accuracy = round((correct / answered) * 100, 1) if answered > 0 else 0
            
            results["individual_accuracy"][student_name] = {
                "correct": correct,
                "total": answered,
                "accuracy": accuracy
            }
            
            total_correct += correct
            total_attempts += answered
        
        # 计算总体正确率
        results["overall_accuracy"] = round((total_correct / total_attempts) * 100, 1) if total_attempts > 0 else 0
        
        return results

    def print_student_accuracy(self):
        """打印学生正确率统计"""
        results = self.calculate_student_accuracy()
        if "error" in results:
            print(f"统计失败: {results['error']}")
            return results
        
        print(f"\n📊 学生成绩统计")
        print(f"- 参与学生数量: {results['total_students']} 人")
        print(f"- 班级平均正确率: {results['overall_accuracy']}%")
        
        print(f"\n👥 各学生正确率:")
        for student_name, data in results["individual_accuracy"].items():
            print(f"- {student_name}: {data['correct']}/{data['total']} ({data['accuracy']}%)")
        
        return results

    def analyze_teaching_content(self) -> Dict:
        """分析教学内容"""
        if not self.classroom_data:
            return {"error": "课堂记录未加载"}
        
        truncated_data = self._truncate_classroom_data()
        
        content_prompt = """
请对以下课堂记录进行教学内容分析，重点关注：

### 教学内容分析
- 主要教学主题和知识点
- 教学方法和策略  
- 课堂活动类型

请提供详细的分析结果。
        """
        
        try:
            # response = self.client.chat.completions.create(
            #     model="deepseek-chat",
            #     messages=[
            #         {"role": "system", "content": "你是一位资深的教育专家，擅长分析教学内容和教学方法。"},
            #         {"role": "user", "content": f"{content_prompt}\n\n课堂记录：\n{truncated_data}"}
            #     ],
            #     temperature=0.1,
            #     max_tokens=800
            # )
            #
            # return {
            #     "dimension": "teaching_content",
            #     "analysis": response.choices[0].message.content,
            #     "timestamp": datetime.now().isoformat()
            # }
            messages=[
                {"role": "system", "content": "你是一位资深的教育专家，擅长分析教学内容和教学方法。"},
                {"role": "user", "content": f"{content_prompt}\n\n课堂记录：\n{truncated_data}"}
            ]
            response = asyncio.run(call_LLM("evaluation", messages))
            return {
                "dimension": "teaching_content",
                "analysis": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"教学内容分析失败: {str(e)}"}

    def analyze_student_engagement(self) -> Dict:
        """分析学生参与度"""
        if not self.classroom_data:
            return {"error": "课堂记录未加载"}
        
        truncated_data = self._truncate_classroom_data()
        
        engagement_prompt = """
请对以下课堂记录进行学生参与度分析，重点关注：

### 学生参与度分析
- 学生互动频率和质量
- 学生提问和回答情况
- 学生注意力和专注度表现

请提供详细的分析结果。
        """
        
        try:
            # response = self.client.chat.completions.create(
            #     model="deepseek-chat",
            #     messages=[
            #         {"role": "system", "content": "你是一位资深的教育专家，擅长观察和分析学生课堂参与情况。"},
            #         {"role": "user", "content": f"{engagement_prompt}\n\n课堂记录：\n{truncated_data}"}
            #     ],
            #     temperature=0.1,
            #     max_tokens=800
            # )
            #
            # return {
            #     "dimension": "student_engagement",
            #     "analysis": response.choices[0].message.content,
            #     "timestamp": datetime.now().isoformat()
            # }
            messages=[
                {"role": "system", "content": "你是一位资深的教育专家，擅长观察和分析学生课堂参与情况。"},
                {"role": "user", "content": f"{engagement_prompt}\n\n课堂记录：\n{truncated_data}"}
            ]
            response = asyncio.run(call_LLM("evaluation", messages))

            return {
                "dimension": "student_engagement",
                "analysis": response,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {"error": f"学生参与度分析失败: {str(e)}"}

    def analyze_teaching_effectiveness(self) -> Dict:
        """分析教学效果"""
        if not self.classroom_data:
            return {"error": "课堂记录未加载"}
        
        truncated_data = self._truncate_classroom_data()
        
        effectiveness_prompt = """
请对以下课堂记录进行教学效果评估，重点关注：

### 教学效果评估
- 知识传递的清晰度
- 学生理解程度
- 教学目标达成情况

请提供详细的分析结果。
        """
        
        try:
            # response = self.client.chat.completions.create(
            #     model="deepseek-chat",
            #     messages=[
            #         {"role": "system", "content": "你是一位资深的教育评估专家，擅长评估教学效果和学习成果。"},
            #         {"role": "user", "content": f"{effectiveness_prompt}\n\n课堂记录：\n{truncated_data}"}
            #     ],
            #     temperature=0.1,
            #     max_tokens=800
            # )
            #
            # return {
            #     "dimension": "teaching_effectiveness",
            #     "analysis": response.choices[0].message.content,
            #     "timestamp": datetime.now().isoformat()
            # }
            messages=[
                {"role": "system", "content": "你是一位资深的教育评估专家，擅长评估教学效果和学习成果。"},
                {"role": "user", "content": f"{effectiveness_prompt}\n\n课堂记录：\n{truncated_data}"}
            ]
            response = asyncio.run(call_LLM("evaluation", messages))

            return {
                "dimension": "teaching_effectiveness",
                "analysis": response,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {"error": f"教学效果分析失败: {str(e)}"}

    def analyze_classroom_atmosphere(self) -> Dict:
        """分析课堂氛围"""
        if not self.classroom_data:
            return {"error": "课堂记录未加载"}
        
        truncated_data = self._truncate_classroom_data()
        
        atmosphere_prompt = """
请对以下课堂记录进行课堂氛围分析，重点关注：

### 课堂氛围分析
- 师生互动质量
- 课堂纪律情况
- 学习氛围营造

请提供详细的分析结果。
        """
        
        try:
            # response = self.client.chat.completions.create(
            #     model="deepseek-chat",
            #     messages=[
            #         {"role": "system", "content": "你是一位资深的课堂观察专家，擅长分析课堂氛围和师生互动。"},
            #         {"role": "user", "content": f"{atmosphere_prompt}\n\n课堂记录：\n{truncated_data}"}
            #     ],
            #     temperature=0.1,
            #     max_tokens=800
            # )
            #
            # return {
            #     "dimension": "classroom_atmosphere",
            #     "analysis": response.choices[0].message.content,
            #     "timestamp": datetime.now().isoformat()
            # }
            messages=[
                {"role": "system", "content": "你是一位资深的课堂观察专家，擅长分析课堂氛围和师生互动。"},
                {"role": "user", "content": f"{atmosphere_prompt}\n\n课堂记录：\n{truncated_data}"}
            ]
            response = asyncio.run(call_LLM("evaluation", messages))

            return {
                "dimension": "classroom_atmosphere",
                "analysis": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"课堂氛围分析失败: {str(e)}"}

    def generate_improvement_suggestions(self) -> Dict:
        """生成改进建议"""
        if not self.classroom_data:
            return {"error": "课堂记录未加载"}
        
        truncated_data = self._truncate_classroom_data()
        
        suggestions_prompt = """
请基于以下课堂记录提供改进建议，重点关注：

### 改进建议
- 教学方法优化建议
- 学生参与度提升策略
- 课堂管理改进方案

请提供具体可行的改进建议。
        """
        
        try:
            # response = self.client.chat.completions.create(
            #     model="deepseek-chat",
            #     messages=[
            #         {"role": "system", "content": "你是一位资深的教育顾问，擅长为教师提供实用的教学改进建议。"},
            #         {"role": "user", "content": f"{suggestions_prompt}\n\n课堂记录：\n{truncated_data}"}
            #     ],
            #     temperature=0.1,
            #     max_tokens=800
            # )
            #
            # return {
            #     "dimension": "improvement_suggestions",
            #     "analysis": response.choices[0].message.content,
            #     "timestamp": datetime.now().isoformat()
            # }
            messages=[
                {"role": "system", "content": "你是一位资深的教育顾问，擅长为教师提供实用的教学改进建议。"},
                {"role": "user", "content": f"{suggestions_prompt}\n\n课堂记录：\n{truncated_data}"}
            ]
            response = asyncio.run(call_LLM("evaluation", messages))

            return {
                "dimension": "improvement_suggestions",
                "analysis": response,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {"error": f"改进建议生成失败: {str(e)}"}

    def analyze_classroom_record_comprehensive(self) -> Dict:
        """综合分析课堂记录 - 调用所有维度并生成综合报告"""
        if not self.classroom_data:
            return {"error": "课堂记录未加载"}
        
        print("正在进行各维度分析...")
        
        # 调用各个维度的分析函数
        dimensions_results = {}
        
        # 1. 教学内容分析
        print("- 教学内容分析...")
        content_result = self.analyze_teaching_content()
        if "error" not in content_result:
            dimensions_results["teaching_content"] = content_result["analysis"]
        
        # 2. 学生参与度分析
        print("- 学生参与度分析...")
        engagement_result = self.analyze_student_engagement()
        if "error" not in engagement_result:
            dimensions_results["student_engagement"] = engagement_result["analysis"]
        
        # 3. 教学效果评估
        print("- 教学效果评估...")
        effectiveness_result = self.analyze_teaching_effectiveness()
        if "error" not in effectiveness_result:
            dimensions_results["teaching_effectiveness"] = effectiveness_result["analysis"]
        
        # 4. 课堂氛围分析
        print("- 课堂氛围分析...")
        atmosphere_result = self.analyze_classroom_atmosphere()
        if "error" not in atmosphere_result:
            dimensions_results["classroom_atmosphere"] = atmosphere_result["analysis"]
        
        # 5. 改进建议
        print("- 改进建议生成...")
        suggestions_result = self.generate_improvement_suggestions()
        if "error" not in suggestions_result:
            dimensions_results["improvement_suggestions"] = suggestions_result["analysis"]
        
        # 生成综合报告
        print("- 生成综合报告...")
        comprehensive_analysis = self._generate_comprehensive_report(dimensions_results)
        
        # 保存结果
        result = {
            "comprehensive_analysis": comprehensive_analysis,
            "dimensions": dimensions_results,
            "timestamp": datetime.now().isoformat()
        }
        
        self.analysis_results['classroom'] = result
        return result

    def _generate_comprehensive_report(self, dimensions_results: Dict) -> str:
        """基于各维度分析结果生成综合报告"""
        if not dimensions_results:
            return "无法生成综合报告：缺少维度分析结果"
        
        # 获取详细的学生成绩数据
        accuracy_results = self.calculate_student_accuracy()
        
        if 'error' in accuracy_results:
            # 如果获取成绩数据失败，仍然生成报告但不包含成绩信息
            overall_accuracy = "无法获取"
            total_students = "未知"
            student_performance_summary = "学生成绩数据获取失败"
        else:
            overall_accuracy = accuracy_results['overall_accuracy']
            total_students = accuracy_results['total_students']
            
            # 生成学生成绩摘要
            individual_scores = []
            for student_name, data in accuracy_results['individual_accuracy'].items():
                individual_scores.append(f"{student_name}: {data['accuracy']}%")
            
            student_performance_summary = f"""
班级整体表现：
- 平均正确率：{overall_accuracy}%
- 参与学生：{total_students}人
- 个人成绩：{', '.join(individual_scores)}
            """
        
        # 处理课程目标信息
        if self.course_objectives:
            course_objectives_section = f"""
## 课程目标：
{self.course_objectives}
            """
            objectives_analysis_instruction = f"请特别分析本节课对于既定课程目标的完成情况，结合{overall_accuracy}%的班级平均正确率来评估目标达成度。"
        else:
            course_objectives_section = "\n## 课程目标：\n未提供课程目标文件"
            objectives_analysis_instruction = "由于未提供具体课程目标，请根据课堂内容推测可能的教学目标并分析完成情况。"
        
        # 构建综合分析提示
        dimensions_summary = ""
        for dimension, analysis in dimensions_results.items():
            dimension_name = {
                "teaching_content": "教学内容分析",
                "student_engagement": "学生参与度分析", 
                "teaching_effectiveness": "教学效果评估",
                "classroom_atmosphere": "课堂氛围分析",
                "improvement_suggestions": "改进建议"
            }.get(dimension, dimension)
            
            dimensions_summary += f"\n### {dimension_name}\n{analysis}\n"
        
        comprehensive_prompt = f"""
请基于以下各维度的分析结果、学生成绩数据和课程目标，生成一份综合的课堂教学评估报告：

## 各维度分析结果：
{dimensions_summary}

## 学生成绩表现：
{student_performance_summary}

{course_objectives_section}

请综合以上信息提供：
1. 整体教学质量和学生成绩评估（重点结合{overall_accuracy}%的班级平均正确率）
2. 学生课堂参与度和师生互动情况分析
3. 课程目标完成度评估（{objectives_analysis_instruction}）
4. 主要优点和亮点
5. 需要改进的方面
6. 综合建议和总结

请以专业、客观的角度给出综合评价，确保将学生的学习成果与课堂教学过程以及预设的课程目标相结合进行深入分析。
        """
        
        try:
            # response = self.client.chat.completions.create(
            #     model="deepseek-chat",
            #     messages=[
            #         {"role": "system", "content": "你是一位资深的教育评估专家，擅长综合分析课堂教学质量、学生学习成果和课程目标达成情况，并提供专业评估报告。"},
            #         {"role": "user", "content": comprehensive_prompt}
            #     ],
            #     temperature=0.1,
            #     max_tokens=1500  # 增加token数量以容纳更详细的分析
            # )
            #
            # return response.choices[0].message.content
            messages=[
                {"role": "system",
                 "content": "你是一位资深的教育评估专家，擅长综合分析课堂教学质量、学生学习成果和课程目标达成情况，并提供专业评估报告。"},
                {"role": "user", "content": comprehensive_prompt}
            ]
            response = asyncio.run(call_LLM("evaluation", messages))

            return response

        except Exception as e:
            return f"综合报告生成失败: {str(e)}"
