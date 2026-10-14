# Pulse 网站保活与监控

保留用户提供的 https://bh.xingbox.me/ 的界面、CSS、图标和主要交互，替换演示逻辑为真实后端。
原网站没有可获取的源码及 source map，因此 vendor/ 保存下载的原始编译资源，adapt_frontend.py 用锚点校验进行可重复适配。拿到源码后建议改为源码构建；不要直接覆盖适配后的 JS。

## 功能

- 公共面板；添加、编辑、删除、暂停、恢复、手动巡检和设置保存需要管理员登录。
- SQLite 持久保存，后台每五秒调度到期网站，网站间隔可选 1/5/10/30 分钟。
- GET 检查标准 HTTP/HTTPS 公网网站，校验 TLS，最多三次重定向，仅读取前 1KB 响应。
- 状态码、响应时长、连续成功/失败、过去 24 小时可用率、7 天历史及真实趋势。
- 记录页面展示最近 500 次检查，趋势从七天数据按 30 分钟聚合；支持筛选与 CSV 导出。
- 右上角“管理员登录 / 账号设置”，初始密码 admin；首次登录设置新密码，后续可在账号设置修改或退出。修改后其他会话失效。
- 默认设置及面板异常提醒阈值持久化；不发送 Telegram/邮件等外部通知。
- 最多 30 个网站，检查并发 2；检查结果代表服务器观察点，不代表国内用户的访问状况。

## 安全和边界

管理操作只允许 TLS 连接、本机访问或带服务器私有 origin_secret 的可信 CDN 请求。
管理密码只存 PBKDF2 哈希；修改后的密码哈希保存在 SQLite，重启不会恢复初始密码；会话 HttpOnly/SameSite；写操作要求 CSRF token。
不接受带凭据、非标准端口及内网地址；DNS 全部结果须为公网地址，连接固定到验证后的 IP，逐跳检查重定向。
系统服务限制 CPU 40%、内存 128MB、48 个任务、HTTP 并发 16。
网站可以公开显示 URL，请勿添加含私密 token 的查询参数。

## 本地运行

Python 3 标准库，无额外依赖。配置放在源码与 public/ 之外。

```bash
python3 adapt_frontend.py
PULSE_CONFIG=/private/config.json PULSE_BIND=127.0.0.1 PULSE_PORT=8080 python3 server.py
python3 -m unittest -v test_monitor.py
```

config.json 包含初始 password_salt（16字节十六进制）、password_hash（PBKDF2-HMAC-SHA256，200000轮）、must_change_password、public_origin、可选 origin_secret。只有首次初始化数据库时使用该初始密码；之后以数据库中的账号配置为准。
PULSE_STATE 控制数据库目录。配置和密码不要提交 Git 或复制到 public/。

## 服务器

- 地址：23.246.165.183，服务 pulse.service。
- 程序：/home/fanxing/services/pulse。
- 配置、证书：/etc/pulse；数据库：/var/lib/pulse/pulse.sqlite3。
- HTTP 80 为公共页面；HTTPS 443 提供管理操作。初始证书为自签，IP 直接访问会提示证书不受信任。
- EdgeOne 接入后使用域名的受信任边缘证书。HTTPS 回源 443；上游自签证书需按控制台能力设置信任或替换为受信任源站证书。
- /api/state 是公共数据，可缓存 15 秒；其余 /api/* 禁止强制缓存，登录和管理响应 no-store；静态 /assets/* 可缓存；首页及 /mount.js、/pulse-client.js 更新后刷新 CDN 缓存。
- 当前源域名的 DNS/CDN 仍需配置；部署脚本不会修改原 Netlify 网站或 DNS。

运行：systemctl status pulse；日志：journalctl -u pulse；重启：systemctl restart pulse。
备份数据库时使用 SQLite backup API，不能只复制运行中的主文件而忽略 WAL。
暂停：systemctl disable --now pulse；程序和数据库保留。防火墙修改前备份在 /root/maintenance/pulse-20261014/nftables.before，回退须先 nft -c 校验再应用。
