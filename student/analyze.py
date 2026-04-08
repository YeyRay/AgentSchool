import json
import matplotlib.pyplot as plt
import os
import numpy as np
import glob
from pathlib import Path

def find_latest_exercise_files():
    """查找最新的练习结果文件"""
    base_path = Path(__file__).parent.parent / "results"
    student_files = {}
    
    # 查找每个学生最新的结果文件
    for student_dir in base_path.glob("Student*"):
        if student_dir.is_dir():
            student_name = student_dir.name
            # 查找最新日期的文件夹
            date_dirs = sorted([d for d in student_dir.iterdir() if d.is_dir()], reverse=True)
            if date_dirs:
                latest_date = date_dirs[0]
                exercise_dir = latest_date / "exercises"
                if exercise_dir.exists():
                    # 查找最新的final结果文件
                    final_files = list(exercise_dir.glob(f"{student_name}_exercise_results_final*.json"))
                    if final_files:
                        # 按修改时间排序，取最新的
                        latest_file = max(final_files, key=lambda f: f.stat().st_mtime)
                        student_files[student_name] = latest_file
    
    return student_files

def load_exercise_results(file_path):
    """加载新格式的练习结果文件并重新计算统计信息"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 从详细答案中重新计算正确的统计信息
    detailed_answers = data["data"]["detailed_answers"]
    
    # 重新统计
    total_questions = len(detailed_answers)
    correct_count = 0
    incorrect_count = 0
    modified_count = 0
    
    for question_id, answer_data in detailed_answers.items():
        # 统计正确/错误
        if answer_data.get("correct", False):
            correct_count += 1
        else:
            incorrect_count += 1
        
        # 统计个性化修改
        if "question_modification" in answer_data or "personalization_log" in answer_data:
            modified_count += 1
    
    # 计算正确率
    accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
    modification_rate = (modified_count / total_questions * 100) if total_questions > 0 else 0
    
    # 重新构建准确的统计信息
    corrected_stats = {
        "total_questions": total_questions,
        "correct_answers": correct_count,
        "incorrect_answers": incorrect_count,
        "accuracy_percentage": round(accuracy, 2)
    }
    
    # 个性化修改信息
    personalization_stats = {
        "total_questions": total_questions,
        "modified_questions": modified_count,
        "modification_rate": round(modification_rate, 2),
        "unmodified_questions": total_questions - modified_count
    }
    
    # 提取原始数据用于比较
    original_stats = data["data"]["statistics"]["performance"]
    original_personalization = data["data"]["statistics"].get("personalization", {})
    
    return {
        "stats": corrected_stats,
        "original_stats": original_stats,
        "answers": detailed_answers,
        "personalization": personalization_stats,
        "original_personalization": original_personalization,
        "test_info": data["data"]["test_info"]
    }

# 查找并加载最新的学生文件
student_files = find_latest_exercise_files()
print(f"找到 {len(student_files)} 个学生的结果文件:")
for student, file_path in student_files.items():
    print(f"  {student}: {file_path}")

# 存储统计信息
stats = {}
all_student_data = {}

for student_name, file_path in student_files.items():
    try:
        data = load_exercise_results(file_path)
        all_student_data[student_name] = data
        
        # 从重新计算的统计信息中提取数据
        performance = data["stats"]
        original_performance = data["original_stats"]
        
        stats[student_name] = {
            'correct': performance["correct_answers"],
            'wrong': performance["incorrect_answers"],
            'total': performance["total_questions"],
            'accuracy': performance["accuracy_percentage"]
        }
        
        print(f"\n{student_name} 统计对比:")
        print(f"  📊 重新计算的正确统计:")
        print(f"     总题数: {performance['total_questions']}")
        print(f"     正确: {performance['correct_answers']}")
        print(f"     错误: {performance['incorrect_answers']}")
        print(f"     正确率: {performance['accuracy_percentage']:.2f}%")
        
        print(f"  📋 文件中原始统计:")
        print(f"     总题数: {original_performance['total_questions']}")
        print(f"     正确: {original_performance['correct_answers']}")
        print(f"     错误: {original_performance['incorrect_answers']}")
        print(f"     正确率: {original_performance['accuracy_percentage']:.2f}%")
        
        # 检查统计是否一致
        if (performance["correct_answers"] != original_performance["correct_answers"] or
            performance["incorrect_answers"] != original_performance["incorrect_answers"]):
            print(f"  ⚠️  警告: 统计数据不一致!")
            print(f"     正确答案差异: {performance['correct_answers'] - original_performance['correct_answers']}")
            print(f"     错误答案差异: {performance['incorrect_answers'] - original_performance['incorrect_answers']}")
        else:
            print(f"  ✅ 统计数据一致")
        
        # 个性化修改统计
        if data["personalization"]:
            print(f"  题目修改: {data['personalization'].get('modified_questions', 0)}/{data['personalization'].get('total_questions', 0)}")
            print(f"  修改率: {data['personalization'].get('modification_rate', 0):.2f}%")
            
    except Exception as e:
        print(f"处理 {student_name} 的文件时出错: {e}")
        continue

# 可视化1：正确/错误答案分布
if stats:
    labels = list(stats.keys())
    correct_counts = [stats[name]['correct'] for name in labels]
    wrong_counts = [stats[name]['wrong'] for name in labels]
    accuracies = [stats[name]['accuracy'] for name in labels]

    # 基本统计图
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # 左图：正确/错误数量堆叠柱状图
    x = range(len(labels))
    ax1.bar(x, correct_counts, width=0.6, label='Correct', color='green', alpha=0.7)
    ax1.bar(x, wrong_counts, width=0.6, bottom=correct_counts, label='Wrong', color='red', alpha=0.7)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=45)
    ax1.set_ylabel('Number of Questions')
    ax1.set_title('Distribution of Correct/Wrong Answers for Each Student')
    ax1.legend()
    
    # 添加总数标签
    for i, (correct, wrong) in enumerate(zip(correct_counts, wrong_counts)):
        total = correct + wrong
        ax1.text(i, total + 1, str(total), ha='center', va='bottom', fontweight='bold')
    
    # 右图：正确率柱状图
    bars = ax2.bar(x, accuracies, width=0.6, color=['green' if acc >= 60 else 'orange' if acc >= 40 else 'red' for acc in accuracies], alpha=0.7)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=45)
    ax2.set_ylabel('Accuracy (%)')
    ax2.set_title('Accuracy Rate for Each Student')
    ax2.set_ylim(0, 100)
    
    # 添加百分比标签
    for i, (bar, acc) in enumerate(zip(bars, accuracies)):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                f'{acc:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    plt.show()
else:
    print("没有找到有效的学生数据文件")

# 可视化2：详细的每题分析（如果有详细数据）
if all_student_data:
    # 收集所有学生的逐题答案
    all_results = []
    student_names = list(all_student_data.keys())
    max_questions = 0
    
    for student_name in student_names:
        answers = all_student_data[student_name]["answers"]
        # 将answers字典转换为按题目序号排序的列表
        student_answers = []
        # 安全地解析question_id，处理各种格式包括科学计数法
        valid_question_ids = []
        for k in answers.keys():
            try:
                # 先尝试直接转换为整数
                if k.isdigit():
                    valid_question_ids.append(int(k))
                else:
                    # 尝试转换科学计数法或浮点数
                    float_val = float(k)
                    if float_val.is_integer() and 0 <= float_val < 10000:  # 合理的题目ID范围
                        valid_question_ids.append(int(float_val))
                    else:
                        print(f"⚠️  跳过无效的题目ID: {k} (值: {float_val})")
            except (ValueError, OverflowError):
                print(f"⚠️  跳过无法解析的题目ID: {k}")
                continue
        
        question_ids = sorted(valid_question_ids)
        max_questions = max(max_questions, max(question_ids) + 1 if question_ids else 0)
        
        for i in range(max_questions):
            if str(i) in answers:
                student_answers.append(1 if answers[str(i)].get('correct', False) else 0)
            else:
                student_answers.append(np.nan)  # 缺失数据
        all_results.append(student_answers)
    
    if max_questions > 0:
        # 转置：行=题目，列=学生
        all_results = np.array(all_results).T
        
        # 每题正确人数统计
        correct_counts_per_question = np.nansum(all_results, axis=1)
        
        # 可视化3：每题正确人数柱状图
        plt.figure(figsize=(15, 6))
        bars = plt.bar(np.arange(len(correct_counts_per_question)), 
                       correct_counts_per_question, 
                       color=plt.cm.RdYlGn(correct_counts_per_question/len(student_names)))
        plt.xlabel('Question Number')
        plt.ylabel('Number of Students Correct')
        plt.title(f'Number of Students Correct per Question (Total Students: {len(student_names)})')
        plt.yticks(range(len(student_names) + 1))
        
        # 添加平均线
        avg_correct = np.nanmean(correct_counts_per_question)
        plt.axhline(y=avg_correct, color='blue', linestyle='--', alpha=0.7, 
                   label=f'Average: {avg_correct:.1f}')
        plt.legend()
        
        # 标记困难题目（正确人数少于平均值的一半）
        difficult_threshold = avg_correct / 2
        difficult_questions = np.where(correct_counts_per_question <= difficult_threshold)[0]
        if len(difficult_questions) > 0:
            plt.scatter(difficult_questions, correct_counts_per_question[difficult_questions], 
                       color='red', s=50, marker='x', label=f'Difficult Questions (≤{difficult_threshold:.1f})')
            plt.legend()
        
        plt.tight_layout()
        plt.show()
        
        # 可视化4：热力图 - 学生 vs 题目
        if len(student_names) <= 10 and max_questions <= 200:  # 避免图太大
            plt.figure(figsize=(max(12, max_questions//10), max(8, len(student_names))))
            plt.imshow(all_results.T, cmap='RdYlGn', aspect='auto', interpolation='nearest', vmin=0, vmax=1)
            plt.colorbar(label='Correct (1) / Wrong (0)', shrink=0.6)
            plt.xlabel('Question Number')
            plt.ylabel('Student')
            plt.title('Heatmap: Per-Question, Per-Student Correctness')
            plt.yticks(range(len(student_names)), student_names)
            plt.tight_layout()
            plt.show()

# 可视化5：个性化修改统计（如果有的话）
personalization_data = {}
for student_name, data in all_student_data.items():
    # 更严格的数据检查
    if (data.get("personalization") and 
        isinstance(data["personalization"], dict) and 
        data["personalization"].get('total_questions', 0) > 0):
        personalization_data[student_name] = data["personalization"]

if personalization_data:
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        students = list(personalization_data.keys())
        modification_rates = []
        modified_counts = []
        total_counts = []
        
        # 安全地提取数据，确保数值类型正确
        for s in students:
            pers_data = personalization_data[s]
            try:
                mod_rate = float(pers_data.get('modification_rate', 0))
                mod_count = int(pers_data.get('modified_questions', 0))
                total_count = int(pers_data.get('total_questions', 0))
                
                modification_rates.append(mod_rate)
                modified_counts.append(mod_count)
                total_counts.append(total_count)
            except (ValueError, TypeError) as e:
                print(f"⚠️  数据转换错误 {s}: {e}")
                modification_rates.append(0)
                modified_counts.append(0)
                total_counts.append(0)
        
        # 左图：修改率
        bars1 = ax1.bar(range(len(students)), modification_rates, color='skyblue', alpha=0.7)
        ax1.set_xticks(range(len(students)))
        ax1.set_xticklabels(students, rotation=45, ha='right')
        ax1.set_ylabel('Modification Rate (%)')
        ax1.set_title('Question Modification Rate by Student')
        ax1.set_ylim(0, 100)
        
        # 为左图添加数值标签
        for i, (bar, rate) in enumerate(zip(bars1, modification_rates)):
            if rate > 0:  # 只在有数据时显示标签
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                        f'{rate:.1f}%', ha='center', va='bottom', fontsize=9)
        
        # 右图：修改数量 vs 总数量 (正确的堆叠图)
        x_pos = np.arange(len(students))
        unmodified_counts = [total - modified for total, modified in zip(total_counts, modified_counts)]
        
        bars2 = ax2.bar(x_pos, unmodified_counts, width=0.6, label='Unmodified Questions', 
                       color='lightgray', alpha=0.7)
        bars3 = ax2.bar(x_pos, modified_counts, width=0.6, bottom=unmodified_counts, 
                       label='Modified Questions', color='orange', alpha=0.7)
        
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(students, rotation=45, ha='right')
        ax2.set_ylabel('Number of Questions')
        ax2.set_title('Question Modification Count by Student')
        ax2.legend()
        
        # 添加数量标签
        for i, (total, modified, unmodified) in enumerate(zip(total_counts, modified_counts, unmodified_counts)):
            # 总数标签
            if total > 0:
                ax2.text(i, total + max(total_counts) * 0.02, str(total), 
                        ha='center', va='bottom', fontweight='bold', fontsize=9)
            # 修改数量标签（如果有修改的题目）
            if modified > 0:
                label_y = unmodified + modified/2
                ax2.text(i, label_y, str(modified), 
                        ha='center', va='center', color='white', fontweight='bold', fontsize=8)
        
        plt.tight_layout()
        plt.show()
        
    except Exception as e:
        print(f"⚠️  可视化个性化修改统计时出错: {e}")
        print(f"    personalization_data: {personalization_data}")
else:
    print("📝 没有找到有效的个性化修改数据")

# 打印总结报告
print("\n" + "="*50)
print("分析总结报告")
print("="*50)
for student_name, data in all_student_data.items():
    print(f"\n{student_name}:")
    performance = data["stats"]
    print(f"  📊 总体表现: {performance['correct_answers']}/{performance['total_questions']} = {performance['accuracy_percentage']:.1f}%")
    
    if data["personalization"]:
        pers = data["personalization"]
        print(f"  🔧 题目个性化: {pers.get('modified_questions', 0)}/{pers.get('total_questions', 0)} = {pers.get('modification_rate', 0):.1f}%")
        
        # 分析修改效果
        if 'modification_effectiveness' in pers:
            eff = pers['modification_effectiveness']
            print(f"  ✨ 修改效果: {eff.get('improved_performance', 'N/A')}")
    
    print(f"  ⏱️  测试时间: {data['test_info']['test_date']}")
    print(f"  🏷️  测试类型: {data['test_info']['postfix']}")

print("\n整体统计:")
if stats:
    avg_accuracy = np.mean([stats[name]['accuracy'] for name in stats])
    total_questions = sum([stats[name]['total'] for name in stats])
    total_correct = sum([stats[name]['correct'] for name in stats])
    print(f"  🎯 平均正确率: {avg_accuracy:.1f}%")
    print(f"  📝 总题目数: {total_questions}")
    print(f"  ✅ 总正确数: {total_correct}")
    
    if personalization_data:
        avg_mod_rate = np.mean([personalization_data[s].get('modification_rate', 0) for s in personalization_data])
        print(f"  🔧 平均修改率: {avg_mod_rate:.1f}%")
