# 悟空GitHub数据分析工具

一个基于 Streamlit 的 GitHub 数据采集与分析工具，

支持GitHub用户数据采集与开发者画像分析，

支持在线或者本地下载软件使用。

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

## 网站

https://gokuscraper.com

## 常见问题

- 启动后无界面：请确认浏览器是否打开 `http://localhost:8501`。

## 免责声明

本项目为数据分析与可视化工具，仅处理公开数据用于研究分析。

本项目与任何第三方平台无关联或授权关系。

禁止用于任何违法或侵犯他人权益的用途，使用者需自行承担全部责任。
