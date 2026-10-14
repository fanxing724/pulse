# 部署与维护

## 通用部署

使用 Python 3.10+，将程序目录设为运行账号只读，将 `PULSE_STATE` 目录设为该账号可写。配置、证书私钥和数据库放在 `public/` 之外。

```bash
python3 scripts/create_config.py --output /private/pulse/config.json --origin https://pulse.example.com
```

设置 `PULSE_CONFIG`、`PULSE_STATE`、监听地址和端口。生产环境使用 HTTPS；HTTP 公开页面可以浏览，但外部管理操作需要安全连接。

`deploy/pulse.service` 是已有 Debian 服务器的模板，包含 CPU 40%、内存 128MB、任务数 48 等限制。用于其他服务器前，修改账号、程序目录、配置和证书路径。`deploy/install.sh` 针对原部署服务器，包含主机名校验、固定路径、IP 和防火墙锚点，不是通用一键安装脚本。

## EdgeOne

域名接入后使用边缘 HTTPS 证书，固定 HTTPS 回源至源站 443。将私有配置的 `public_origin` 设为实际访问域名，回源 Host/SNI 与证书匹配。

- `/api/state` 为公开数据，可缓存 15 秒。
- 其余 `/api/*` 不缓存，尤其是会话、登录、密码和管理接口。
- `/assets/*` 可缓存。发布后刷新首页和变更资源，避免旧页面引用旧接口。
- 浏览器 HTTPS 跳转与回源协议是两段连接，后台保持 HTTPS 回源。

自签源站证书不会自动成为浏览器受信任证书。EdgeOne 支持按套餐能力配置指定可信 CA 的回源校验，见[官方说明](https://edgeone.ai/document/74344)。

## 管理密码

初始密码 `admin` 登录后须设置新密码，后续在“账号设置”中修改或退出。其他会话会在改密后失效。
盐值和哈希位于 SQLite `admin_credentials` 表，修改配置中的初始密码不会重置已有账号。

## 日志与备份

```bash
systemctl status pulse
journalctl -u pulse
systemctl restart pulse
```

备份配置、证书和程序，并使用 SQLite backup API 备份数据库，避免遗漏 WAL 中的变更：

```python
import sqlite3
source = sqlite3.connect('/var/lib/pulse/pulse.sqlite3')
target = sqlite3.connect('/private/backup/pulse.sqlite3')
source.backup(target)
target.close()
source.close()
```

备份文件和配置使用私有权限，不提交 Git。停止服务可使用 `systemctl disable --now pulse`，保留数据目录以便恢复。

## 实现边界

- 并发 2，最多 30 个公网网站，不支持自定义请求头、认证信息或任意端口。
- 七天历史按 30 分钟聚合，页面记录展示最近 500 条。
- 当前为单管理员面板，不是多用户 SaaS。
- 原始前端只有编译资源，适配脚本以锚点校验替换模拟逻辑；取得原始源码后可转向常规构建。
