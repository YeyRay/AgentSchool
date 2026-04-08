# evaluation.py
# This file contains the refactored code for the classroom evaluation system.

from class_analyser import ClassroomAnalyzer
import os
from datetime import datetime
import re


class Evaluation:
    """
    负责进行课堂教学综合评估的类。
    封装了从数据加载到报告生成的所有工作流程。
    """

    def __init__(self):
        """
        通过创建一个 ClassroomAnalyzer 实例来初始化 Evaluation 类。
        """
        self.analyzer = ClassroomAnalyzer()

    def _auto_select_latest(self):
        """
        自动选择最新的日志目录（YYYYMMDD_HHMMSS），并返回 (datetime_str, event_id)。
        优先选择子目录中最大的数字作为 event_id；若不存在则默认为 1。
        """
        current_dir = os.path.dirname(__file__)
        project_root = os.path.dirname(current_dir)
        logs_root = os.path.join(project_root, "logs")

        if not os.path.isdir(logs_root):
            raise RuntimeError(f"日志根目录不存在: {logs_root}")

        # 过滤出符合 YYYYMMDD_HHMMSS 格式的目录并排序
        pattern = re.compile(r"^\d{8}_\d{6}$")
        candidates = [d for d in os.listdir(logs_root) if os.path.isdir(os.path.join(logs_root, d)) and pattern.match(d)]
        if not candidates:
            raise RuntimeError(f"未在 {logs_root} 下找到符合 YYYYMMDD_HHMMSS 的日志目录")

        candidates.sort()
        latest = candidates[-1]

        # 选择事件ID：取该日志目录下的最大数字子目录；若没有，默认 1
        latest_path = os.path.join(logs_root, latest)
        event_subdirs = []
        for name in os.listdir(latest_path):
            full = os.path.join(latest_path, name)
            if os.path.isdir(full) and name.isdigit():
                try:
                    event_subdirs.append(int(name))
                except Exception:
                    continue
        event_id = max(event_subdirs) if event_subdirs else 1

        print(f"🕒 未指定日志名，已自动选择最新日志: {latest}")
        print(f"🧭 事件ID: {event_id}")
        return latest, event_id

    def markdown_to_pdf(self, md_path: str, pdf_path: str = None) -> str:
        """
        使用 WeasyPrint 或其他备选方法将 Markdown 文件转换为 PDF。

        Args:
            md_path (str): Markdown 文件路径。
            pdf_path (str, optional): 期望的 PDF 输出路径。
                                       如果为 None，则自动生成。

        Returns:
            str: 生成的 PDF 或备选 HTML 文件的路径。
                 如果所有转换都失败，则返回 None。
        """
        # 如果未指定 PDF 路径，则自动生成
        if pdf_path is None:
            pdf_path = md_path.replace('.md', '.pdf')

        # --- 转换方法（按优先级排序） ---

        # 1. 优先：WeasyPrint
        result = self._convert_with_weasyprint(md_path, pdf_path)
        if result:
            return result

        # 2. 备选：pdfkit
        result = self._convert_with_pdfkit(md_path, pdf_path)
        if result:
            return result

        # 3. 最终备选：HTML
        html_path = self._generate_html_fallback(md_path)
        if html_path:
            print(f"📄 已生成 HTML 文件作为备选方案: {html_path}")
            print("💡 您可以在浏览器中打开此 HTML 文件，并将其保存为 PDF。")
            return html_path

        print("❌ 所有转换方法均失败。")
        return None

    def _convert_with_weasyprint(self, md_path: str, pdf_path: str) -> str:
        """用于使用 WeasyPrint 进行转换的辅助函数。"""
        try:
            import markdown2
            from weasyprint import HTML, CSS

            print("🔄 正在尝试使用 WeasyPrint 进行转换...")

            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()

            html_content = markdown2.markdown(md_content, extras=['tables', 'fenced-code-blocks', 'header-ids'])

            html_doc = f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>课堂教学评估报告</title>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """

            css_styles = """
            @page {
                size: A4;
                margin: 2cm;
            }

            body {
                font-family: "PingFang SC", "Microsoft YaHei", "SimHei", Arial, sans-serif;
                line-height: 1.8;
                color: #333;
                font-size: 14px;
            }

            h1 {
                color: #2c3e50;
                font-size: 24px;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
                margin-bottom: 30px;
                page-break-after: avoid;
            }

            h2 {
                color: #34495e;
                font-size: 20px;
                border-bottom: 2px solid #ecf0f1;
                padding-bottom: 8px;
                margin-top: 40px;
                margin-bottom: 20px;
                page-break-after: avoid;
            }

            h3 {
                color: #7f8c8d;
                font-size: 16px;
                margin-top: 30px;
                margin-bottom: 15px;
                page-break-after: avoid;
            }

            p {
                margin-bottom: 15px;
                text-align: justify;
                text-indent: 2em;
            }

            ul, ol {
                margin-left: 20px;
                margin-bottom: 15px;
            }

            li {
                margin-bottom: 8px;
                line-height: 1.6;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                page-break-inside: avoid;
            }

            th, td {
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }

            th {
                background-color: #f8f9fa;
                font-weight: bold;
            }

            code {
                background-color: #f8f8f8;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: "Courier New", monospace;
                font-size: 13px;
            }

            pre {
                background-color: #f8f8f8;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
                margin: 15px 0;
                page-break-inside: avoid;
            }

            blockquote {
                border-left: 4px solid #3498db;
                padding-left: 20px;
                margin: 20px 0;
                font-style: italic;
                color: #666;
            }
            """

            HTML(string=html_doc).write_pdf(
                pdf_path,
                stylesheets=[CSS(string=css_styles)]
            )

            print(f"✅ PDF 转换成功 (WeasyPrint): {pdf_path}")
            return pdf_path

        except ImportError:
            print("⚠️ WeasyPrint 未安装。")
            print("💡 安装命令: pip install weasyprint")
            return None
        except Exception as e:
            print(f"⚠️ WeasyPrint 转换失败: {e}")
            return None

    def _convert_with_pdfkit(self, md_path: str, pdf_path: str) -> str:
        """用于使用 pdfkit 进行转换的辅助函数。"""
        try:
            import markdown2
            import pdfkit

            print("🔄 正在尝试使用 pdfkit 进行转换...")

            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()

            html_content = markdown2.markdown(md_content, extras=['tables', 'fenced-code-blocks'])

            pdfkit.from_string(html_content, pdf_path)

            print(f"✅ PDF 转换成功 (pdfkit): {pdf_path}")
            return pdf_path

        except ImportError:
            print("⚠️ pdfkit 未安装。")
            return None
        except Exception as e:
            print(f"⚠️ pdfkit 转换失败: {e}")
            return None

    def _generate_html_fallback(self, md_path: str) -> str:
        """生成 HTML 文件作为最终备选方案。"""
        try:
            import markdown2

            print("🔄 正在生成 HTML 文件作为备选...")

            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()

            html_content = markdown2.markdown(md_content, extras=['tables', 'fenced-code-blocks'])

            html_doc = f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>课堂教学评估报告</title>
                <style>
                    body {{
                        font-family: "PingFang SC", "Microsoft YaHei", "SimHei", Arial, sans-serif;
                        line-height: 1.8;
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 40px;
                        color: #333;
                    }}
                    h1 {{
                        color: #2c3e50;
                        border-bottom: 3px solid #3498db;
                        padding-bottom: 10px;
                    }}
                    h2 {{
                        color: #34495e;
                        border-bottom: 2px solid #ecf0f1;
                        padding-bottom: 8px;
                        margin-top: 40px;
                    }}
                    h3 {{
                        color: #7f8c8d;
                        margin-top: 30px;
                    }}
                    p {{
                        margin-bottom: 15px;
                        text-align: justify;
                    }}
                    ul, ol {{
                        margin-left: 20px;
                    }}
                    li {{
                        margin-bottom: 8px;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin: 20px 0;
                    }}
                    th, td {{
                        border: 1px solid #ddd;
                        padding: 12px;
                        text-align: left;
                    }}
                    th {{
                        background-color: #f8f9fa;
                    }}
                    @media print {{
                        body {{
                            margin: 0;
                            padding: 20px;
                        }}
                    }}
                </style>
            </head>
            <body>
                {html_content}
                <div style="margin-top: 50px; padding: 20px; background-color: #f8f9fa; border-radius: 5px;">
                    <p><strong>💡 提示:</strong> 要将此页面保存为 PDF，请使用浏览器的打印功能：</p>
                    <ul>
                        <li>按 Cmd+P (Mac) 或 Ctrl+P (Windows)</li>
                        <li>选择 "保存为 PDF"</li>
                        <li>调整页面设置以获得最佳效果</li>
                    </ul>
                </div>
            </body>
            </html>
            """

            html_path = md_path.replace('.md', '.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_doc)

            return html_path

        except Exception as e:
            print(f"⚠️ HTML 生成失败: {e}")
            return None

    def run_evaluation(self, datetime_str: str = None, event_id: int = None):
        """
        根据特定的日期时间字符串和整数 ID 运行综合评估。

        Args:
            datetime_str (str): 日期时间字符串，例如 '20250804_164319'。
            event_id (int): 课程 ID。
        """
        print("课堂教学评估系统 (自动综合分析模式)")
        print("=" * 70)

        # 获取当前脚本所在目录（evaluation/）
        current_dir = os.path.dirname(__file__)
        # 获取项目根目录（即 evaluation 的父目录）
        project_root = os.path.dirname(current_dir)

        # 自动选择最新日志与事件ID
        if not datetime_str or event_id is None:
            datetime_str, event_id = self._auto_select_latest()

        # 根据输入参数动态构建文件路径
        logs_dir = os.path.join(project_root, "logs", datetime_str, str(event_id))
        classroom_file = os.path.join(logs_dir, "output.txt")
        objectives_file = os.path.join(logs_dir, "target.txt")
        student_folder = os.path.join(project_root, "stu_exercises")

        print(f"🔗 正在构建路径:")
        print(f"  - 课堂日志: {classroom_file}")
        print(f"  - 课程目标: {objectives_file}")
        print(f"  - 学生练习文件夹: {student_folder}")
        print(f"  - 学生文件模式: {{student.name}}_exercise_results_{datetime_str}_{event_id}.json")

        if not self.analyzer.load_data_from_folder(classroom_file, student_folder, objectives_file, datetime_str,
                                                   event_id):
            print("数据加载失败，程序退出。")
            return

        print(f"\n✅ 数据加载成功!")
        print(f"- 课堂日志: 已加载")
        print(f"- 学生数量: {len(self.analyzer.student_results)}")

        print("\n" + "=" * 70)
        print("开始综合分析...")
        print("=" * 70)

        try:
            # 首先，显示学生成绩
            print("\n📊 学生成绩统计")
            print("-" * 30)
            self.analyzer.print_student_accuracy()

            # 对课堂日志进行综合分析
            print("\n🔍 课堂日志综合分析")
            print("-" * 30)
            classroom_analysis = self.analyzer.analyze_classroom_record_comprehensive()

            if "error" in classroom_analysis:
                print(f"课堂分析失败: {classroom_analysis['error']}")
            else:
                print("\n" + "=" * 70)
                print("📋 课堂教学综合评估报告")
                print("=" * 70)
                print(classroom_analysis['comprehensive_analysis'])

                # 自动保存为 Markdown 文件
                output_dir = os.path.join(os.path.dirname(__file__), 'analysis_output')
                os.makedirs(output_dir, exist_ok=True)
                # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                # md_path = os.path.join(output_dir, f'analysis_report_{timestamp}.md')
                md_path = os.path.join(output_dir, f'analysis_report_{datetime_str}_{event_id}.md')

                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(f"# 课堂教学综合评估报告\n\n")
                    f.write(f"## 生成时间: {classroom_analysis.get('timestamp', '')}\n\n")
                    dims = classroom_analysis.get('dimensions', {})
                    for key, value in dims.items():
                        f.write(f"### {key}\n{value}\n\n")
                    f.write(f"## 综合分析报告\n{classroom_analysis['comprehensive_analysis']}\n")

                print(f"\n📄 已保存为 Markdown: {md_path}")

                # 转换为 PDF
                result_path = self.markdown_to_pdf(md_path)
                if result_path and result_path.endswith('.pdf'):
                    print(f"📑 已自动导出为 PDF: {result_path}")
                elif result_path and result_path.endswith('.html'):
                    print(f"📄 已生成 HTML 文件: {result_path}")

        except Exception as e:
            print(f"分析过程中发生错误: {e}")

        print("\n" + "=" * 70)
        print("✅ 分析完成。")
        print("=" * 70)


if __name__ == "__main__":
    evaluator = Evaluation()
    # 未提供参数时自动选择最新日志目录和事件ID
    evaluator.run_evaluation()
