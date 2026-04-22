# 悟空GitHub采集器

![https://asiaassets.gokuscraper.com/images/2026/04/20/645c271762df3d49.webp](https://asiaassets.gokuscraper.com/images/2026/04/20/645c271762df3d49.webp)

一个面向开发者的 GitHub 数据分析工具，

支持从用户维度进行数据采集与开发者画像分析，

帮助快速洞察技术栈、活跃度与项目影响力。

## 核心优势

- 无需复杂配置，开箱即用
- 支持免登录与 Token 双模式
- 一键生成开发者画像分析
- 本地运行，数据可控

## 在线体验

[https://goku-dev-scraper.streamlit.app/](https://goku-dev-scraper.streamlit.app/)

[https://modelscope.cn/studios/GokuScrpaer/GokuGitHubScraper](https://modelscope.cn/studios/GokuScrpaer/GokuGitHubScraper)

## 功能特性

- 免登录 / Token 双模式
- 基础信息采集
- 仓库信息采集
- Commit 信息采集（支持仓库数量与分页上限控制）
- 开发者画像分析：
  - 技术栈分布
  - Star 与活跃度
  - 开发峰值
  - 存储占用
  - 仓库影响力评分
  - 许可证合规分布

## 项目结构

- `streamlit_app.py`：主应用
- `start_ui.py`：启动入口
- `requirements.txt`：依赖清单
- `logo.svg` / `gzh.jpg`：界面资源文件

## 环境要求

- Python 3.10+（推荐 3.11）
- Windows

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动方式

### 方式一（推荐）

```bash
python start_ui.py
```

### 方式二（直接运行 Streamlit）

```bash
streamlit run streamlit_app.py
```

启动后默认访问：

- <http://localhost:8501>

## 使用流程

1. 在“配置与额度检查”页输入 GitHub 用户名或主页 URL。
2. 选择运行模式：
   - 免登录（额度较低）
   - Token（额度更高）
3. 执行额度检查并通过校验。
4. 按页签顺序执行：
   - 基础信息采集
   - 仓库信息采集
   - commit 信息采集
   - 开发者画像分析
5. 下载 CSV 或保存到导出目录。

# 公众号和交流群

![交流群](https://asiaassets.gokuscraper.com/%E6%82%9F%E7%A9%BA%E7%88%AC%E8%99%AB%E5%85%AC%E4%BC%97%E5%8F%B7.jpg)

## 官方网站

https://gokuscraper.com

在线体验工具，或了解更多数据分析能力。

如有定制化数据分析或工具需求，欢迎交流。

## 常见问题

- 启动后无界面：请确认浏览器是否打开 `http://localhost:8501`。

## 免责声明

本项目为数据分析与可视化工具，仅处理公开数据用于研究分析。

本项目与任何第三方平台无关联或授权关系。

禁止用于任何违法或侵犯他人权益的用途，使用者需自行承担全部责任。
