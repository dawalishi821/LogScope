# LogScope 网站访问日志可视化分析工具

LogScope 使用 Flask、Python 和本地 ECharts 页面分析 Nginx / Apache 访问日志。启动后默认加载仓库中的演示日志，可查看每小时访问趋势、状态码和请求方法分布、Top IP / URL、异常类别，以及可筛选和导出的异常明细。

## 运行环境

- Python 3.10 或更新版本
- macOS、Linux 或 Windows
- 不需要数据库；ECharts 已随项目提供，打开页面和图表不依赖外网 CDN

## 安装与启动

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Windows PowerShell：

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

打开 <http://127.0.0.1:5000/>。默认页面会自动加载 `data/sample_access.log`。点击“恢复样例”可以重新载入演示数据；点击“导入日志”可选择 `.log` 或 `.txt` 文件。上传上限为 16 MB。

## 10 分钟演示流程

1. 打开首页，先说明 10,301 行样例中有 10,300 行有效日志，另有 1 行格式错误记录，用来展示容错。
2. 看访问趋势、状态码分布和高频来源 IP；指出凌晨时段的扫描请求峰值。
3. 在异常明细按“高风险”筛选，查看 SQL 注入、目录扫描、路径遍历和登录失败后成功响应的线索。
4. 搜索 `203.0.113.77` 或筛选“暴力破解”，说明 401 失败与随后 200 响应的时序判断。
5. 点击“导出 CSV”，检查导出的规则、来源、请求路径和命中说明。
6. 上传课程提供的 combined 格式日志，最后点击“恢复样例”回到演示状态。

## 主要功能

- 解析 Apache / Nginx combined 格式，并兼容缺少 Referer、User-Agent 的 common 格式。
- 提取客户端地址、时间、方法、路径、协议、状态码、响应字节数、Referer 和 User-Agent。
- 统计访问趋势、Top 10 IP、Top 10 URL、状态码分布、方法分布、错误比例和异常类别。
- 检测可疑请求特征、工具 User-Agent、单 IP 高频访问、单 IP 4xx / 5xx 比例异常，以及登录失败后出现成功响应的情况。
- 支持风险、类别和关键字筛选，异常结果分页查看并导出为带 UTF-8 BOM 的 CSV。
- 项目不会持久保存上传日志文件；分析结果由当前 Flask 进程保留。当前版本面向本机课堂演示，进程内只保存一份当前分析结果。

## 检测规则

请求特征和阈值放在 `config/detection_rules.json`，可调整而无需修改分析逻辑。规则命中是需要人工复核的信号，不能单独证明攻击成功。

| 类别 | 规则示例 | 默认风险 |
| --- | --- | --- |
| SQL 注入 | UNION SELECT、恒真条件、SLEEP / BENCHMARK、information_schema | 高 / 中 |
| 路径遍历 | `../`、编码与双重编码目录穿越 | 高 |
| 目录扫描 | `.env`、`.git`、phpMyAdmin、备份文件、管理入口 | 中 |
| 方法探测 | TRACE、CONNECT | 中 |
| 可疑 User-Agent | sqlmap、Hydra、dirsearch、Nikto、Masscan 等工具标识 | 高 / 中 / 低 |
| 高频访问 | 同一 IP 在当前导入文件中请求数达到 120 次 | 高 |
| 4xx 比例 | 单 IP 至少 10 次请求且 4xx 占比达到 72% | 高 / 中 |
| 5xx 比例 | 单 IP 至少 10 次请求且 5xx 占比达到 25% | 高 |
| 登录爆破 | POST 登录请求中至少 8 次 401/403；失败后出现 200 时升为高风险 | 中 / 高 |

SQL 与路径规则会先进行 URL 解码，包含一次额外解码以覆盖常见双重编码。高频和错误比例是按整份导入文件计算的，不是滑动时间窗口。检测结果和阈值适合课程演示，不应直接用作生产拦截策略。

## 项目结构

```text
app.py                         Flask 页面与 JSON / CSV API
log_analyzer.py                日志解析、统计和规则检测
config/detection_rules.json    可配置特征与阈值
data/sample_access.log         10,301 行演示日志
scripts/generate_sample_logs.py 可重复生成的样例日志脚本
static/css/dashboard.css      页面样式
static/js/dashboard.js        图表与交互
static/vendor/echarts.min.js  本地 ECharts 5.5.1
static/vendor/THIRD-PARTY-NOTICE.md
templates/index.html          页面结构
 tests/                         自动化测试
 report/                         项目报告与渲染质检文件
```

演示日志由 `scripts/generate_sample_logs.py` 使用固定随机种子构造，不含真实访客记录。所有地址使用 RFC 5737 文档示例网段（192.0.2.0/24、198.51.100.0/24、203.0.113.0/24）。重新生成：

```bash
python scripts/generate_sample_logs.py
```

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 服务状态 |
| GET | `/api/summary` | 指标和图表数据 |
| GET | `/api/anomalies` | 异常明细；支持 `severity`、`category`、`q`、`page`、`page_size` |
| GET | `/api/anomalies/export.csv` | 按当前筛选条件导出 CSV |
| POST | `/api/upload` | 上传 `logfile` 字段中的 `.log` / `.txt` 文件 |
| POST | `/api/sample` | 恢复内置样例 |

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖日志字段解析、格式错误容错、规则命中、爆破时序判断、10,000 行以上样例、页面和 API、文件上传、筛选及 CSV 导出。

## 重新生成项目报告

报告 Word 文件、Markdown 源稿和架构图已放在 `report/`。如需从 `scripts/build_report.py` 重新生成：

```bash
python -m pip install -r requirements-report.txt
python scripts/build_report.py
```

如果系统字体目录未自动识别中文字体，可通过 `LOGSCOPE_CJK_FONT` 指向一份本机可用的中文 `.ttf`、`.ttc` 或 `.otf` 字体文件。

## 已知边界

- 仅按日志首字段作为来源 IP，不会自行信任或解析代理头；若要识别真实访客 IP，应由 Nginx / Apache 配置可信的 real-IP 字段并让其进入日志。
- 只分析日志中可见的请求行与 User-Agent，不读取请求体，因此无法发现只出现在 POST 请求体中的注入内容。
- 上传后以当前 Python 进程中的一份结果供页面读取；适合本地演示，不支持多用户隔离和持久化。
- User-Agent 和 URL 特征可能被伪造或编码，规则会有误报和漏报，应结合状态码、频率、时间与业务背景复核。
