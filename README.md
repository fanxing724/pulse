<!-- fanxing-style:start -->
<picture>
  <source media="(prefers-color-scheme: light)" srcset="https://fanxing724.github.io/new-make/fanxing724/projects/pulse/cover.light.svg">
  <img alt="Pulse · 给小站留一盏灯" src="https://fanxing724.github.io/new-make/fanxing724/projects/pulse/cover.svg" width="100%">
</picture>

**浏览器关了，小站的心跳还在记录。**

个人服务器上的小站，也值得有一个能随时查看的状态面板。Pulse 定时检查网站，把响应、耗时与历史留在一个轻量面板里；保活效果仍取决于目标平台规则。

<sub>番星 / 星轨手记 · <a href="https://fanxing724.github.io/new-make/fanxing724/projects/style.html">风格样板</a> · <a href="https://fanxing724.github.io/">个人小站</a></sub>
<!-- fanxing-style:end -->

# Pulse · 网站保活与监控

轻量级网站保活与可用性监控面板。使用 Python 标准库和 SQLite，浏览器关闭后仍会定时检查网站，适合部署在小内存服务器上。

## 功能

- 添加、编辑、删除、暂停和恢复网站；间隔可选 1、5、10、30 分钟。
- 真实 HTTP 状态码、响应时间、连续成功/失败次数和过去 24 小时可用率。
- 24 小时 / 7 天趋势图、最近 500 条记录、搜索筛选和 CSV 导出。
- 七天历史自动清理；最多 30 个目标，检查并发为 2。
- 公共状态面板与管理员登录；初始密码 `admin`，首次登录设置自己的密码。
- 后台修改密码、退出登录；改密后其他会话失效，重启不会恢复初始密码。
- 深浅色模式、移动端导航和实色登录弹窗。

保活效果取决于目标平台的休眠规则。结果代表源站观察点，不代表所有地区的访问质量。异常提醒目前显示在面板中，不发送外部通知。

## 快速开始

需要 Python 3.10+，无需安装 pip 包、Node 或数据库服务。

```bash
git clone git@github.com:fanxing724/pulse.git
cd pulse
python3 scripts/create_config.py
python3 adapt_frontend.py
PULSE_CONFIG="$PWD/.state/config.json" PULSE_BIND=127.0.0.1 PULSE_PORT=8080 python3 server.py
```

访问 `http://127.0.0.1:8080`，点击右上角“管理员登录”，用 `admin` 登录并设置新密码。之后在“账号设置”中改密或退出。
配置创建脚本不会覆盖已有文件，也不会重置已初始化数据库中的密码。

## 目录

| 路径 | 内容 |
| --- | --- |
| `server.py` | HTTP/HTTPS、SQLite、后台巡检和管理接口 |
| `public/` | 页面、样式、前端接口及编译资源 |
| `vendor/` | 原始界面编译资源 |
| `adapt_frontend.py` | 可重复适配，替换演示逻辑并连接真实接口 |
| `scripts/create_config.py` | 创建私有初始配置 |
| `deploy/` | 已有服务器的 systemd 服务与安装脚本 |
| `docs/DEPLOYMENT.md` | 部署、CDN、备份及维护说明 |
| `test_monitor.py` | 地址、重定向、统计及账号检查 |
| `licenses/` | 第三方许可文本 |

前端来自用户提供的 Claude 基础框架，原始站点为 `https://bh.xingbox.me/`。目前没有原始 TSX 工程、依赖锁文件或 source map；仓库保存原始编译资源和适配源码，后端为完整 Python 源码。拿到原始前端工程后可替换编译资源适配流程。

## 配置

| 环境变量 | 默认值 / 用途 |
| --- | --- |
| `PULSE_CONFIG` | 必填；私有 JSON 配置路径 |
| `PULSE_STATE` | 项目下 `.state/`，保存 SQLite |
| `PULSE_BIND` | `0.0.0.0`；本地使用 `127.0.0.1`，双栈使用 `::` |
| `PULSE_PORT` | HTTP 端口，默认 `8080` |
| `PULSE_CERT`、`PULSE_KEY` | 同时设置时启用 HTTPS |
| `PULSE_TLS_PORT` | HTTPS 端口，默认 `8443` |

`public_origin` 是浏览器访问地址，通过 CDN 时设为实际 HTTPS 域名。初始配置只保存 PBKDF2 哈希，首次初始化后密码以数据库为准。
管理接口只接受 HTTPS、本机请求，或带私有 `origin_secret` 的可信回源请求。会话采用 HttpOnly/SameSite，写操作校验 CSRF。目标仅支持标准 HTTP/HTTPS 公网端口，校验全部 DNS 地址并固定连接 IP，逐跳校验重定向。

生产部署见 [部署说明](docs/DEPLOYMENT.md)。不要将配置、证书私钥、密码或数据库提交到仓库。

## 检查

```bash
python3 -m unittest -v test_monitor.py
python3 adapt_frontend.py
```

已有部署还通过了浏览器登录、改密、退出、网站管理、真实巡检、历史记录、移动端和公网 HTTPS 验证。

## 开源协议

项目原创代码使用 [MIT License](LICENSE)。第三方代码保留各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。
