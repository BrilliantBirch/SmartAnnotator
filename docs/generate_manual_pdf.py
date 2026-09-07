# -*- coding: utf-8 -*-
"""
用户说明书 PDF 生成脚本

将 docs/manual.md 转换为 PDF：
    markdown(MD→HTML) → QTextDocument(HTML 富文本) → QPrinter(输出 PDF)

使用 PySide6 原生渲染，无需 TeX 环境，中文以 Microsoft YaHei 字体输出。

注意：必须使用默认 windows 平台插件（非 offscreen），
offscreen 平台无系统字体数据库，中文会渲染为方块。

使用方式（在项目根目录执行）:
    python docs/generate_manual_pdf.py

作者: BaiBinnan
创建日期: 2026-08-26
"""

import sys
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtPrintSupport import QPrinter

DOCS_DIR = Path(__file__).parent
MANUAL_MD = DOCS_DIR / "manual.md"
OUTPUT_PDF = DOCS_DIR / "BrilliantAnnotator_用户说明书.pdf"

# 中文字体（Windows 系统自带）
FONT_FAMILY = "Microsoft YaHei"
MONO_FAMILY = "Consolas"

# 页面内嵌 CSS（QTextDocument 支持的 CSS 子集）
HTML_STYLE = """
<style>
body { font-family: "%s"; font-size: 11pt; color: #18181b; line-height: 1.5; }
h1 { font-size: 20pt; color: #18181b; border-bottom: 2px solid #d4d4d8; padding-bottom: 6px; }
h2 { font-size: 15pt; color: #18181b; margin-top: 20px; }
h3 { font-size: 12.5pt; color: #3f3f46; margin-top: 14px; }
table { border-collapse: collapse; width: 100%%; margin: 8px 0; }
th { background-color: #f4f4f5; border: 1px solid #d4d4d8; padding: 5px 8px; text-align: left; }
td { border: 1px solid #d4d4d8; padding: 5px 8px; }
code { font-family: "%s"; background-color: #f4f4f5; }
pre { font-family: "%s"; background-color: #f4f4f5; border: 1px solid #e4e4e7;
      padding: 8px; white-space: pre-wrap; }
hr { border: none; border-top: 1px solid #d4d4d8; }
blockquote { color: #52525b; border-left: 3px solid #a1a1aa; margin-left: 0;
             padding-left: 10px; }
</style>
""" % (FONT_FAMILY, MONO_FAMILY, MONO_FAMILY)


def markdown_to_html(md_path: Path) -> str:
    """将 Markdown 文件转换为带内嵌样式的完整 HTML 文档。

    Args:
        md_path: Markdown 源文件路径。

    Returns:
        完整 HTML 文档字符串。

    Raises:
        FileNotFoundError: 源文件不存在。
        ImportError: markdown 包未安装。
    """
    import markdown

    if not md_path.exists():
        raise FileNotFoundError(f"说明书源文件不存在: {md_path}")

    md_text = md_path.read_text(encoding="utf-8")
    # extensions: tables(表格) / fenced_code(代码块) / sane_lists(列表)
    body = markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "sane_lists"]
    )
    return (
        "<html><head><meta charset='utf-8'/>"
        + HTML_STYLE
        + "</head><body>"
        + body
        + "</body></html>"
    )


def html_to_pdf(html: str, pdf_path: Path) -> None:
    """将 HTML 渲染输出为 PDF 文件。

    Args:
        html: 完整 HTML 文档字符串。
        pdf_path: 输出 PDF 文件路径。
    """
    # QTextDocument/QPrinter 需要 QApplication 实例（windows 平台，
    # 提供系统字体数据库以正确渲染中文）
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    doc = QTextDocument()
    doc.setDefaultFont(QFont(FONT_FAMILY, 11))
    doc.setHtml(html)
    # 适应 A4 页宽，与 QPrinter 分辨率一致
    doc.setPageSize(QSizeF(794, 1123))

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(pdf_path))
    # 页边距 15mm（QPageLayout.Unit 默认 Millimeter）
    printer.setPageMargins(QMarginsF(15, 15, 15, 15))
    doc.print_(printer)
    app.processEvents()


def main() -> int:
    """生成说明书 PDF，返回进程退出码。"""
    try:
        html = markdown_to_html(MANUAL_MD)
    except FileNotFoundError as e:
        print(f"[错误] {e}")
        return 1
    except ImportError:
        print("[错误] 缺少 markdown 包，请执行: pip install markdown")
        return 1

    html_to_pdf(html, OUTPUT_PDF)
    size_kb = OUTPUT_PDF.stat().st_size / 1024
    print(f"已生成: {OUTPUT_PDF} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
