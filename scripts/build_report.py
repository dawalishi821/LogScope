"""Build the editable project report and its Markdown source from shared content."""
from __future__ import annotations

import os
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "report"
TITLE = "网站访问日志可视化分析工具开发报告"
FONT_PATHS = [
    os.environ.get("LOGSCOPE_CJK_FONT", ""),
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

SECTIONS = [
    ("项目背景与需求", [
        ("p", "Web 访问日志把客户端地址、请求时间、HTTP 方法、路径和服务器响应记录在同一条记录中。将这些字段与访问频率、状态码和客户端标识结合，可以帮助值班人员从普通访问中找出扫描、注入尝试和登录爆破线索。"),
        ("p", "项目按课程任务书实现：导入 Nginx / Apache 访问日志，完成字段提取、统计、基础异常检测、ECharts 展示和 CSV 导出。核心分析对象是 combined 格式；当 Referer 或 User-Agent 缺失时，也接受常见格式记录。"),
        ("table", (["任务要求", "实现内容", "对应位置"], [
            ["日志导入与解析", "上传 .log / .txt，识别 combined 与 common 格式，记录无效行数量。", "app.py / log_analyzer.py"],
            ["统计分析", "按小时趋势、Top 10 IP / URL、状态码和方法分布、错误率。", "log_analyzer.py"],
            ["异常检测", "7 条请求特征规则、11 个 User-Agent 特征，以及频率、错误率和登录爆破聚合判断。", "config/detection_rules.json"],
            ["可视化和导出", "6 个 ECharts 图表、筛选分页明细、UTF-8 BOM CSV。", "templates / static / app.py"],
            ["演示和版本管理", "10,301 行可重复生成的演示日志；仓库已有至少 10 次有意义的 Git 提交。", "data / scripts / Git 历史"],
        ])),
    ]),
    ("总体架构设计", [
        ("p", "项目使用单体 Flask 应用，分析逻辑和界面通过 JSON API 解耦。上传日志被解析为统一记录结构，后端同时生成图表聚合和异常事件；浏览器用 ECharts 绘制图表，并通过分页 API 查询异常明细。"),
        ("diagram", "从日志输入到可视化与导出的处理流程"),
        ("table", (["模块", "职责", "设计说明"], [
            ["Flask 应用 app.py", "提供页面、摘要、异常查询、文件上传、样例恢复与 CSV 下载。", "限制上传为 16 MB；不持久保存上传文件，分析结果保留在当前进程。"],
            ["分析模块 log_analyzer.py", "解析字段、汇总统计、运行特征与聚合检测规则。", "纯 Python 逻辑，可脱离页面单独测试。"],
            ["规则配置 JSON", "保存正则特征、风险级别与聚合阈值。", "增加常见签名时可只改配置文件。"],
            ["浏览器页面", "展示指标卡、趋势折线图、分布图、排行图和异常明细。", "ECharts 5.5.1 随项目本地提供，页面不依赖外网 CDN。"],
        ])),
        ("p", "关键数据路径为：日志文件 → Flask 接收 → combined 字段解析 → JSON 规则检测与聚合统计 → /api/summary、/api/anomalies → ECharts 与异常表；CSV 导出复用同一组异常筛选条件。"),
    ]),
    ("数据解析与统计实现", [
        ("p", "解析器以一行一条访问记录为单位，使用正则捕获远程地址、时间、引号内请求行、状态码、字节数，以及可选的 Referer 和 User-Agent。请求行再拆分为方法、路径和协议；时间保留日志中的时区，统计时按小时聚合。"),
        ("p", "解析失败的行会被计数并跳过，不会中止整份文件。样例中专门放入一条格式错误记录，用来验证容错。字段标准化后的记录供 Top IP、Top URL、状态码、方法、字节量和趋势统计复用，减少各图表重复解析。"),
        ("table", (["展示项", "计算方式", "页面呈现"], [
            ["访问趋势", "按日志本地时区聚合到小时；缺失小时补零。", "平滑折线图，可拖动缩放。"],
            ["来源与路径排行", "按 IP 和请求路径分别计数，按次数取前 10 名。", "横向柱状图，长路径截断显示并保留悬停详情。"],
            ["状态码与方法", "分别对状态码和 HTTP 方法计数。", "环形饼图，悬停查看数量及比例。"],
            ["错误比例", "将 4xx 和 5xx 记录数相加后除以有效记录数。", "指标卡显示百分比。"],
        ])),
    ]),
    ("异常检测规则", [
        ("p", "规则分为单条请求特征和整份日志聚合判断。每条异常记录保留命中规则、风险、类别、来源 IP、时间、请求路径、状态码和说明。一个请求可以命中多个规则，所以事件总数不等同于唯一可疑请求数。"),
        ("table", (["规则组", "命中条件", "默认风险与解读"], [
            ["SQL 注入特征", "UNION SELECT、恒真条件、SLEEP / BENCHMARK、information_schema。先对路径进行 URL 解码。", "高或中；说明 URL 中出现常见注入模式，不表示数据库已执行。"],
            ["路径遍历与敏感路径", "../、编码或双重编码穿越；.env、.git、phpMyAdmin、备份文件等路径。", "高或中；可作为扫描或文件读取尝试线索。"],
            ["工具 User-Agent", "匹配 sqlmap、Hydra、dirsearch、Nikto、Masscan 等 11 个关键字；空 UA 单独提示。", "工具标识通常为高风险；curl、wget 等常见客户端按低风险提示。"],
            ["非常用方法", "TRACE 或 CONNECT。", "中；需要结合服务器配置与来源行为复核。"],
            ["单 IP 高频", "同一 IP 在整份日志中的请求数达到 120。", "高；当前阈值按导入文件总量计算，不是时间窗口。"],
            ["4xx / 5xx 比例", "至少 10 次请求且 4xx 占比达到 72%；或至少 10 次请求且 5xx 占比达到 25%。", "高或中；可能是扫描、错误客户端，也可能反映服务异常。"],
            ["登录爆破", "同一 IP 对 login / signin / auth 路径发起至少 8 次 POST 401 / 403；失败后出现 200 时升为高。", "中或高；日志未包含账号或会话字段，时序关联只是启发式判断。"],
        ])),
        ("h2", "误报与漏报边界"),
        ("p", "User-Agent 可以伪造；搜索引擎、监控程序和合法运维脚本也可能触发工具特征。频率规则按整份文件统计，会把长时间的合法高流量来源标成高频；路径签名只能检查 URL 和日志中的请求行，无法看到 POST 请求体。代理场景下首字段可能是反向代理地址，必须由服务端配置可信的真实 IP 日志字段。规则用于定位复核对象，不应直接当作封禁或入侵成功结论。"),
    ]),
    ("演示数据与运行方式", [
        ("p", "演示文件由 scripts/generate_sample_logs.py 使用固定随机种子构造，包含 10,007 条普通访问、220 条目录探测、36 条 SQL 注入尝试、22 条路径遍历请求、15 条登录爆破记录，以及 1 条格式错误行。IP 使用文档示例网段，不代表真实用户或攻击源。"),
        ("table", (["样例指标", "本次生成结果"], [
            ["日志行数", "10,301 行；10,300 行解析成功，1 行被容错跳过。"],
            ["来源地址", "204 个唯一 IP；扫描源 198.51.100.23 在短时段产生 220 次请求。"],
            ["异常事件", "342 条：高风险 325 条，中风险 17 条；同一请求可能对应多条规则事件。"],
            ["错误比例", "4xx / 5xx 合计占有效请求的 8.28%。"],
            ["主要命中", "可疑 User-Agent 271、SQL 注入 36、路径遍历 22、目录扫描 8、状态码异常 3、高频访问 1、暴力破解 1。"],
        ])),
        ("p", "演示顺序建议：打开默认样例 → 解释访问趋势与状态码 → 按高风险筛选并查看扫描 / 注入线索 → 搜索 203.0.113.77 并解释登录失败后出现 200 → 导出 CSV → 上传自己的日志并恢复样例。"),
    ]),
    ("测试与结果", [
        ("p", "项目使用 Python unittest 与 Flask test client 验证解析、检测和 API 流程。对 10,301 行样例执行单次解析与分析，perf_counter 计时约 0.101 秒；12 项自动化测试全部通过，整套测试约 0.60 秒。该性能数据是本地开发环境的一次测量，不等同于生产环境吞吐承诺。"),
        ("table", (["测试范围", "验证内容", "结果"], [
            ["格式解析", "combined 字段、common 格式缺失尾字段、错误行跳过。", "通过"],
            ["特征与聚合检测", "URL 编码 SQL 注入、路径遍历、登录失败后成功、JSON 规则数量。", "通过"],
            ["样例规模", "10,301 行日志、10,300 条有效记录、异常事件与小时趋势。", "通过"],
            ["Web 页面与 API", "首页渲染、摘要数据、风险筛选、异常分页。", "通过"],
            ["上传和导出", "单行日志上传、完整 10,301 行文件上传、非法扩展名拒绝、CSV BOM 与字段。", "通过"],
            ["静态检查", "Python py_compile 与前端 JavaScript 语法检查。", "通过"],
        ])),
        ("p", "测试命令为 python -m unittest discover -s tests -v。浏览器检查确认默认页面加载了 6 个图表、关键指标和异常明细，移动窄屏下图表按单列布局显示。"),
    ]),
    ("个人总结", [
        ("p", "这次开发让我把 HTTP 字段、日志解析、检测规则和图表展示串成了一条可运行的数据路径。调试样例时，我发现单看某个状态码很难判断行为；把来源 IP、请求频率、路径和 User-Agent 放在一起，才能更有把握地解释为什么一条记录值得复核。"),
        ("p", "我也认识到规则写得越宽并不代表检测越好。阈值会影响误报，规则命中也不等于攻击成功。因此我把规则和阈值放进 JSON，并在界面和报告中说明判断边界。当前实现适合课程演示，后续可以增加按分钟的滑动窗口、真实代理 IP 配置、日志格式模板、用户隔离和基线对比，使结论更贴近真实运维场景。"),
    ]),
    ("参考资料", [
        ("bullets", [
            "《网站访问日志可视化分析工具开发》课程项目任务书，教师提供材料。",
            "《HTTP 协议基础：方法与状态码》课程资料。",
            "《Nginx 与 Apache 日志格式详解》课程资料。",
            "《Python 速成：文件处理、正则与 Flask》课程资料。",
            "《ECharts 进阶：折线图、饼图、柱状图》课程资料。",
            "《攻击日志特征库：SQL 注入、扫描与爆破》课程资料。",
            "Flask 官方文档，https://flask.palletsprojects.com/ 。",
            "Apache ECharts 官方文档，https://echarts.apache.org/zh/index.html 。项目随附 ECharts 5.5.1，遵循 Apache License 2.0。",
        ]),
    ]),
]


def make_architecture_image(path: Path) -> None:
    width, height = 1360, 260
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = next((Path(p) for p in FONT_PATHS if p and Path(p).is_file()), None)
    if font_path:
        title_font = ImageFont.truetype(str(font_path), 20)
        text_font = ImageFont.truetype(str(font_path), 15)
        small_font = ImageFont.truetype(str(font_path), 13)
    else:
        title_font = text_font = small_font = ImageFont.load_default()
    labels = [
        ("输入日志", "Nginx / Apache", "combined 文件"),
        ("Flask 接收", "上传 / 恢复样例", "16 MB 上限"),
        ("字段解析", "时间 · IP · 请求", "无效行容错"),
        ("规则引擎", "JSON 正则与阈值", "请求 + 聚合"),
        ("统计聚合", "趋势 · Top 10", "状态码 · 方法"),
        ("API 输出", "JSON 查询", "CSV 下载"),
        ("ECharts 页面", "图表 · 筛选", "异常明细"),
    ]
    node_w, node_h, gap = 166, 112, 27
    total = len(labels) * node_w + (len(labels) - 1) * gap
    x0, y0 = (width - total) // 2, 63
    fills = ["#eef4ff", "#f0f5ff", "#edf8f6", "#fff5e7", "#eff6ff", "#f2f1fb", "#eaf5f4"]
    borders = ["#8eabed", "#8eabed", "#76c2b1", "#e6b875", "#8eabed", "#a99add", "#76c2b1"]
    for i, (head, line1, line2) in enumerate(labels):
        x = x0 + i * (node_w + gap)
        draw.rounded_rectangle((x, y0, x + node_w, y0 + node_h), radius=17, fill=fills[i], outline=borders[i], width=2)
        draw.text((x + node_w / 2, y0 + 27), head, fill="#20314c", font=title_font, anchor="mm")
        draw.text((x + node_w / 2, y0 + 62), line1, fill="#596a83", font=text_font, anchor="mm")
        draw.text((x + node_w / 2, y0 + 88), line2, fill="#8290a4", font=small_font, anchor="mm")
        if i < len(labels) - 1:
            sx, ex, cy = x + node_w + 4, x + node_w + gap - 5, y0 + node_h / 2
            draw.line((sx, cy, ex, cy), fill="#8da0ba", width=3)
            draw.polygon([(ex, cy), (ex - 9, cy - 6), (ex - 9, cy + 6)], fill="#8da0ba")
    image.save(path, format="PNG", optimize=True)


def set_run_font(run, *, size: float | None = None, bold: bool | None = None, color: str | None = None):
    run.font.name = "Arial"
    r_fonts = run._element.get_or_add_rPr().rFonts
    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        r_fonts.attrib.pop(qn(f"w:{attr}"), None)
    r_fonts.set(qn("w:ascii"), "Arial")
    r_fonts.set(qn("w:hAnsi"), "Arial")
    r_fonts.set(qn("w:eastAsia"), "Heiti SC")
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_borders(cell, color="D9D9D9", size="5") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_cell_margins(cell, top=100, start=115, bottom=100, end=115) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for m, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def keep_row_together(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement("w:cantSplit"))


def add_field(paragraph, instruction: str):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, separate, text, end])
    set_run_font(run, size=9, color="7A8799")


def table_to_markdown(headers, rows):
    def fmt(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(fmt(x) for x in headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(fmt(x) for x in row) + " |" for row in rows)
    return "\n".join(lines)


def write_markdown(path: Path) -> None:
    parts = [f"# {TITLE}", "", "课程项目报告  ·  2026 年 11 月", "", "## 摘要", "",
             "本报告记录 LogScope 网站访问日志可视化分析工具的设计、实现与验证。项目使用 Flask 接收 Nginx / Apache 日志，由 Python 解析和统计，通过 JSON 配置的启发式规则标记异常，并在本地 ECharts 页面展示结果。使用 10,301 行构造样例与 12 项自动化测试完成验证；本机一次样例分析约 0.101 秒。工具可以指出值得复核的线索，但不判断攻击是否成功。", ""]
    for heading, blocks in SECTIONS:
        parts.extend([f"## {heading}", ""])
        for kind, value in blocks:
            if kind == "p":
                parts.extend([value, ""])
            elif kind == "h2":
                parts.extend([f"### {value}", ""])
            elif kind == "bullets":
                parts.extend([f"- {item}" for item in value])
                parts.append("")
            elif kind == "table":
                headers, rows = value
                parts.extend([table_to_markdown(headers, rows), ""])
            elif kind == "diagram":
                parts.extend(["输入日志 → Flask 接收 → 字段解析 → JSON 规则引擎 → 统计聚合 → JSON / CSV API → ECharts 页面", ""])
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def add_table(doc: Document, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    table.style = "Table Grid"
    widths = {
        2: [1.35, 3.5],
        3: [1.35, 3.25, 1.45],
    }.get(len(headers))
    if widths is None:
        widths = [6.05 / len(headers)] * len(headers)
    for idx, label in enumerate(headers):
        cell = table.rows[0].cells[idx]
        cell.width = Inches(widths[idx])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_shading(cell, "274C77")
        set_cell_borders(cell)
        set_cell_margins(cell)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.12
        run = p.add_run(str(label))
        set_run_font(run, size=8.7, bold=True, color="FFFFFF")
    repeat_header(table.rows[0])
    keep_row_together(table.rows[0])
    for row_index, values in enumerate(rows):
        row = table.add_row()
        keep_row_together(row)
        for idx, value in enumerate(values):
            cell = row.cells[idx]
            cell.width = Inches(widths[idx])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_shading(cell, "F4F7FB" if row_index % 2 == 0 else "FFFFFF")
            set_cell_borders(cell)
            set_cell_margins(cell)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.12
            run = p.add_run(str(value))
            set_run_font(run, size=8.2, color="26364E")
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return table


def build_docx(path: Path, diagram_path: Path):
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(.68)
    section.bottom_margin = Inches(.68)
    section.left_margin = Inches(.78)
    section.right_margin = Inches(.78)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "STHeiti")
    normal.font.size = Pt(10.2)
    normal.font.color.rgb = RGBColor(37, 51, 71)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.18

    for name, size in (("Title", 24), ("Subtitle", 13), ("Heading 1", 15), ("Heading 2", 11.5)):
        style = doc.styles[name]
        style.font.name = "Arial"
        r_fonts = style._element.rPr.rFonts
        for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
            r_fonts.attrib.pop(qn(f"w:{attr}"), None)
        r_fonts.set(qn("w:ascii"), "Arial")
        r_fonts.set(qn("w:hAnsi"), "Arial")
        r_fonts.set(qn("w:eastAsia"), "Heiti SC")
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.bold = name != "Subtitle"
        style.paragraph_format.keep_with_next = True
        if name == "Heading 1":
            style.paragraph_format.space_before = Pt(16)
            style.paragraph_format.space_after = Pt(7)
        elif name == "Heading 2":
            style.paragraph_format.space_before = Pt(9)
            style.paragraph_format.space_after = Pt(4)

    # Cover page: title and metadata without extra decorative rules.
    cover_space = doc.add_paragraph()
    cover_space.paragraph_format.space_after = Pt(82)
    title = doc.add_paragraph(style="Title")
    title_ppr = title._p.get_or_add_pPr()
    title_borders = title_ppr.find(qn("w:pBdr"))
    if title_borders is not None:
        title_ppr.remove(title_borders)
    title_style_ppr = doc.styles["Title"]._element.get_or_add_pPr()
    style_borders = title_style_ppr.find(qn("w:pBdr"))
    if style_borders is not None:
        title_style_ppr.remove(style_borders)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(16)
    run = title.add_run(TITLE)
    set_run_font(run, size=24, bold=True, color="000000")
    subtitle = doc.add_paragraph(style="Subtitle")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(24)
    run = subtitle.add_run("课程项目报告")
    set_run_font(run, size=14, color="000000")
    for line in ("Python · Flask · ECharts", "2026 年 11 月"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(7)
        run = p.add_run(line)
        set_run_font(run, size=11, color="66758B")
    doc.add_page_break()

    doc.add_heading("摘要", level=1)
    summary = ("本报告记录 LogScope 网站访问日志可视化分析工具的设计、实现与验证。项目使用 Flask 接收 Nginx / Apache 日志，由 Python 解析和统计，通过 JSON 配置的启发式规则标记异常，并在本地 ECharts 页面展示结果。使用 10,301 行构造样例与 12 项自动化测试完成验证；本机一次样例分析约 0.101 秒。工具可以指出值得复核的线索，但不判断攻击是否成功。")
    p = doc.add_paragraph(summary)
    p.paragraph_format.space_after = Pt(8)

    for heading, blocks in SECTIONS:
        doc.add_heading(heading, level=1)
        for kind, value in blocks:
            if kind == "p":
                p = doc.add_paragraph(value)
                p.paragraph_format.widow_control = True
            elif kind == "h2":
                doc.add_heading(value, level=2)
            elif kind == "bullets":
                for item in value:
                    p = doc.add_paragraph(style="List Bullet")
                    p.paragraph_format.left_indent = Inches(.25)
                    p.paragraph_format.first_line_indent = Inches(-.16)
                    p.paragraph_format.space_after = Pt(4)
                    run = p.add_run(item)
                    set_run_font(run, size=9.8, color="26364E")
            elif kind == "table":
                headers, rows = value
                add_table(doc, headers, rows)
            elif kind == "diagram":
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_before = Pt(4)
                p.paragraph_format.space_after = Pt(1)
                p.add_run().add_picture(str(diagram_path), width=Inches(6.88))
                caption = doc.add_paragraph(value)
                caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
                caption.paragraph_format.space_after = Pt(8)
                for run in caption.runs:
                    set_run_font(run, size=8.5, color="6D7B90")

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.space_before = Pt(0)
    run = footer.add_run("LogScope  ·  网站访问日志可视化分析工具  ·  ")
    set_run_font(run, size=8.5, color="7A8799")
    add_field(footer, "PAGE")
    doc.core_properties.title = TITLE
    doc.core_properties.subject = "Flask 与 ECharts 日志分析课程项目报告"
    doc.core_properties.author = "LogScope 项目"
    doc.save(path)


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    diagram_path = REPORT_DIR / "architecture.png"
    docx_path = REPORT_DIR / "project_report.docx"
    markdown_path = REPORT_DIR / "project_report.md"
    make_architecture_image(diagram_path)
    write_markdown(markdown_path)
    build_docx(docx_path, diagram_path)
    print(f"Created {docx_path.relative_to(ROOT)}")
    print(f"Created {markdown_path.relative_to(ROOT)}")
    print(f"Created {diagram_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
