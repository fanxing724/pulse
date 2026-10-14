#!/usr/bin/env python3
"""Small, dependency-free Pulse origin. Public reads; authenticated writes."""
import concurrent.futures
import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import ssl
import threading
import time
from datetime import datetime, timezone, timedelta
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urljoin, unquote
import uuid

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('PULSE_STATE', ROOT / '.state'))
STATE.mkdir(parents=True, exist_ok=True)
DB = STATE / 'pulse.sqlite3'
CONFIG = json.loads(Path(os.environ['PULSE_CONFIG']).read_text())
LOCK = threading.RLock()
CHECK_LOCK = threading.Lock()
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)
SESSIONS = {}
LOGIN_FAILURES = {}
MAX_SITES = 30
TZ = timezone(timedelta(hours=8))
DEFAULTS = {'interval': 5, 'threshold': 3, 'alerts': True}
CACHE = {'expires': 0, 'data': None}


def connection():
    c = sqlite3.connect(DB, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def initialize():
    with LOCK, connection() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS sites (
          id TEXT PRIMARY KEY, name TEXT, url TEXT UNIQUE, interval INTEGER,
          category TEXT, paused INTEGER DEFAULT 0, next_due REAL DEFAULT 0,
          status TEXT DEFAULT 'pending', response INTEGER DEFAULT 0, code INTEGER,
          streak INTEGER DEFAULT 0, failures INTEGER DEFAULT 0, last_check REAL);
        CREATE TABLE IF NOT EXISTS checks (
          id INTEGER PRIMARY KEY, site_id TEXT REFERENCES sites(id) ON DELETE CASCADE,
          checked_at REAL, response INTEGER, code INTEGER, status TEXT, error TEXT);
        CREATE INDEX IF NOT EXISTS checks_time ON checks(checked_at);
        CREATE INDEX IF NOT EXISTS checks_site_time ON checks(site_id,checked_at);
        CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS admin_credentials (
          id INTEGER PRIMARY KEY, salt TEXT NOT NULL, password_hash TEXT NOT NULL,
          must_change INTEGER NOT NULL DEFAULT 0);
        ''')
        c.execute('INSERT OR IGNORE INTO settings VALUES (1, ?)', (json.dumps(DEFAULTS),))
        c.execute('INSERT OR IGNORE INTO admin_credentials VALUES (1,?,?,?)',
                  (CONFIG['password_salt'], CONFIG['password_hash'], int(CONFIG.get('must_change_password', False))))


def credentials():
    with LOCK, connection() as c:
        return dict(c.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone())


def password_matches(password, auth):
    if not isinstance(password, str) or len(password) > 256:
        return False
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(auth['salt']), 200000).hex()
    return hmac.compare_digest(digest, auth['password_hash'])


def validated_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(x) < 33 or ord(x) == 127 for x in value):
        raise ValueError('网站地址格式不正确')
    p = urlsplit(value)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError('仅支持不含凭据和片段的 HTTP / HTTPS 地址')
    if p.port not in (None, 80 if p.scheme == 'http' else 443):
        raise ValueError('仅支持标准网站端口 80 / 443')
    host = p.hostname.encode('idna').decode('ascii')
    if host.endswith('.'):
        host = host[:-1]
    addresses = socket.getaddrinfo(host, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError('域名没有可用地址')
    for entry in addresses:
        addr = ipaddress.ip_address(entry[4][0])
        if not addr.is_global or (addr.version == 6 and addr.ipv4_mapped and not addr.ipv4_mapped.is_global):
            raise ValueError('只能监控公网网站，禁止访问内网和本机地址')
    return p, host, addresses


def request_target(url):
    """Resolve once, validate ALL addresses, connect to a pinned IP; check every redirect."""
    deadline = time.monotonic() + 12
    for redirect in range(4):
        p, host, addresses = validated_url(url)
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError('检查超时')
        af, kind, proto, _, address = addresses[0]
        sock = socket.socket(af, kind, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(address)
            if p.scheme == 'https':
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            conn = http.client.HTTPConnection(host, timeout=timeout)
            conn.sock = sock
            target = p.path or '/'
            if p.query:
                target += '?' + p.query
            conn.request('GET', target, headers={'Host': '[' + host + ']' if ':' in host else host,
                         'User-Agent': 'Pulse-Monitor/1.0', 'Accept': '*/*', 'Connection': 'close'})
            response = conn.getresponse()
            code = response.status
            location = response.getheader('Location')
            response.read(1024)
            conn.close()
        finally:
            sock.close()
        if code in (301, 302, 303, 307, 308) and location:
            if redirect == 3:
                raise ValueError('重定向次数过多')
            url = urljoin(url, location)
            continue
        return code
    raise ValueError('重定向次数过多')


def check_site(site):
    started = time.monotonic()
    code, error = None, ''
    try:
        code = request_target(site['url'])
        status = 'online' if 200 <= code < 400 else 'error'
    except (TimeoutError, socket.timeout):
        status, error = 'timeout', '请求超时'
    except Exception as e:
        status, error = 'error', type(e).__name__
    duration = round((time.monotonic() - started) * 1000)
    now = time.time()
    with LOCK, connection() as c:
        current = c.execute('SELECT * FROM sites WHERE id=?', (site['id'],)).fetchone()
        if not current or current['paused'] or current['url'] != site['url']:
            return
        c.execute('INSERT INTO checks(site_id,checked_at,response,code,status,error) VALUES(?,?,?,?,?,?)',
                  (site['id'], now, duration, code, status, error))
        c.execute('UPDATE sites SET status=?,response=?,code=?,streak=?,failures=?,last_check=? WHERE id=?',
                  (status, duration, code, current['streak'] + 1 if status == 'online' else 0,
                   0 if status == 'online' else current['failures'] + 1, now, site['id']))
        c.execute('DELETE FROM checks WHERE checked_at<?', (now - 7 * 86400,))
        CACHE['expires'] = 0


def run_checks(force=False):
    if not CHECK_LOCK.acquire(blocking=False):
        return False
    try:
        with LOCK, connection() as c:
            rows = c.execute('SELECT * FROM sites WHERE paused=0 AND (? OR next_due<=?)', (force, time.time())).fetchall()
            for s in rows:
                c.execute('UPDATE sites SET next_due=? WHERE id=?', (time.time() + s['interval'] * 60, s['id']))
        for f in [POOL.submit(check_site, dict(s)) for s in rows]:
            f.result()
        return True
    finally:
        CHECK_LOCK.release()


def scheduler():
    while True:
        try:
            run_checks()
        except Exception:
            logging.exception('Scheduled checks failed')
        time.sleep(5)


def snapshot():
    with LOCK:
        if CACHE['expires'] > time.monotonic():
            return CACHE['data']
        data = build_snapshot()
        CACHE.update(expires=time.monotonic()+15, data=data)
        return data


def build_snapshot():
    now = time.time()
    with LOCK, connection() as c:
        sites = []
        for row in c.execute('SELECT * FROM sites ORDER BY rowid'):
            s = dict(row)
            total, good = c.execute("SELECT count(*),sum(status='online') FROM checks WHERE site_id=? AND checked_at>=?", (s['id'], now - 86400)).fetchone()
            s.update(initial=s['name'][0].upper(), color='mint', status='paused' if s['paused'] else s['status'],
                     uptime=round(100 * (good or 0) / total, 2) if total else 0,
                     lastCheck=datetime.fromtimestamp(s['last_check'], TZ).strftime('%H:%M:%S') if s['last_check'] else '等待检查')
            for key in ('paused', 'next_due', 'last_check'):
                s.pop(key)
            sites.append(s)
        history = [dict(r) for r in c.execute('''SELECT checks.id,site_id AS siteId,name,checked_at AS timestamp,
                    checks.response,checks.code,checks.status FROM checks JOIN sites ON sites.id=checks.site_id
                    ORDER BY checked_at DESC LIMIT 500''')]
        for h in history:
            h['time'] = datetime.fromtimestamp(h['timestamp'], TZ).strftime('%Y-%m-%d %H:%M:%S')
        # All seven days are aggregated into 30-minute bins. Never synthesize samples.
        trend = [dict(r) for r in c.execute('''SELECT site_id AS siteId,cast(checked_at/1800 AS INTEGER)*1800 AS timestamp,
                   avg(response) AS response,100.0*sum(status='online')/count(*) AS uptime
                   FROM checks WHERE checked_at>=? GROUP BY site_id,cast(checked_at/1800 AS INTEGER)
                   ORDER BY timestamp''', (now - 7 * 86400,))]
        settings = json.loads(c.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
    return {'sites': sites, 'history': history, 'trend': trend, 'settings': settings,
            'updated': datetime.now(TZ).strftime('%H:%M:%S'), 'generatedAt': now}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    slots = threading.BoundedSemaphore(16)
    request_queue_size = 32

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class IPv6Server(Server):
    address_family = socket.AF_INET6


class Handler(SimpleHTTPRequestHandler):
    server_version = 'Pulse'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'public'), **kwargs)

    def setup(self):
        self.request.settimeout(15)
        if isinstance(self.request, ssl.SSLSocket):
            self.request.do_handshake()
        super().setup()

    def secure(self):
        address = ipaddress.ip_address(self.client_address[0])
        loopback = address.is_loopback or bool(address.version == 6 and address.ipv4_mapped and address.ipv4_mapped.is_loopback)
        if isinstance(self.connection, ssl.SSLSocket) or loopback:
            return True
        secret = CONFIG.get('origin_secret', '')
        return bool(secret and hmac.compare_digest(self.headers.get('X-Pulse-Origin', ''), secret))

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['pulse_session'].value
        except Exception:
            return None
        with LOCK:
            session = SESSIONS.get(hashlib.sha256(token.encode()).hexdigest())
            return session if session and session['expires'] > time.time() else None

    def json_response(self, body, status=200, cookie=None, public=False):
        data = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'public, max-age=0, s-maxage=15' if public else 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlsplit(self.path).path
        if p == '/api/state':
            self.json_response(snapshot(), public=True)
        elif p == '/api/session':
            s = self.session()
            self.json_response({'authenticated': bool(s), 'csrf': s['csrf'] if s else None, 'secure': self.secure(),
                                'mustChangePassword': bool(s and credentials()['must_change'])})
        elif p == '/healthz':
            self.json_response({'ok': True})
        elif p.startswith('/api/') or any(x.startswith('.') for x in unquote(p).split('/') if x):
            self.send_error(404)
        else:
            super().do_GET()

    def do_HEAD(self):
        if urlsplit(self.path).path.startswith('/api/'):
            self.send_error(405)
        else:
            super().do_HEAD()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        if not self.path.startswith('/api/') and self.path != '/healthz':
            self.send_header('Cache-Control', 'public, max-age=300' if self.path.startswith('/assets/') else 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        super().end_headers()

    def body(self):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('不支持此请求编码')
        length = int(self.headers.get('Content-Length', '0'))
        if length < 0 or length > 16384:
            raise ValueError('请求过大')
        body = json.loads(self.rfile.read(length) or b'{}')
        if not isinstance(body, dict):
            raise ValueError('请求格式不正确')
        return body

    def do_POST(self):
        try:
            self.post()
        except (ValueError, json.JSONDecodeError, socket.gaierror) as e:
            self.json_response({'error': str(e)}, 400)
        except Exception:
            logging.exception('API request failed')
            self.json_response({'error': '操作失败，请重试'}, 500)

    def post(self):
        p = urlsplit(self.path).path
        if not self.secure():
            self.json_response({'error': '管理操作需要 HTTPS，请使用安全入口'}, 403)
            return
        origin = self.headers.get('Origin')
        allowed = {CONFIG.get('public_origin', ''), 'https://' + self.headers.get('Host', ''), 'http://' + self.headers.get('Host', '')}
        if origin and origin not in allowed:
            self.json_response({'error': '请求来源不匹配'}, 403)
            return
        body = self.body()
        if p == '/api/login':
            address = self.client_address[0]
            with LOCK:
                recent = [t for t in LOGIN_FAILURES.get(address, []) if t > time.time() - 900]
                if len(recent) >= 8:
                    self.json_response({'error': '尝试过多，请 15 分钟后再试'}, 429)
                    return
            auth = credentials()
            if not password_matches(body.get('password'), auth):
                with LOCK:
                    LOGIN_FAILURES[address] = recent + [time.time()]
                    if len(LOGIN_FAILURES) > 1024:
                        LOGIN_FAILURES.clear()
                self.json_response({'error': '密码不正确'}, 401)
                return
            token = secrets.token_urlsafe(32)
            s = {'csrf': secrets.token_urlsafe(24), 'expires': time.time() + 43200}
            with LOCK:
                for k in [k for k, v in SESSIONS.items() if v['expires'] < time.time()]:
                    SESSIONS.pop(k)
                SESSIONS[hashlib.sha256(token.encode()).hexdigest()] = s
            secure_cookie = '; Secure' if isinstance(self.connection, ssl.SSLSocket) or CONFIG.get('origin_secret') else ''
            self.json_response({'authenticated': True, 'csrf': s['csrf'], 'mustChangePassword': bool(auth['must_change'])}, cookie='pulse_session=' + token + '; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200' + secure_cookie)
            return
        session = self.session()
        if not session:
            self.json_response({'error': '请先以管理员身份登录'}, 401)
            return
        if not hmac.compare_digest(self.headers.get('X-Pulse-CSRF', ''), session['csrf']):
            self.json_response({'error': '请求校验失败，请重新登录'}, 403)
            return
        if credentials()['must_change'] and p not in ('/api/password', '/api/logout'):
            self.json_response({'error': '请先修改初始密码，再进行管理操作'}, 403)
            return
        if p == '/api/logout':
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            with LOCK:
                SESSIONS.pop(hashlib.sha256(cookie['pulse_session'].value.encode()).hexdigest(), None)
            self.json_response({'ok': True}, cookie='pulse_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
        elif p == '/api/password':
            new = body.get('newPassword')
            if not isinstance(new, str) or not 8 <= len(new) <= 128 or new != new.strip():
                raise ValueError('新密码需为 8–128 个字符，首尾不能包含空格')
            with LOCK, connection() as c:
                auth = dict(c.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone())
                if not password_matches(body.get('currentPassword'), auth):
                    self.json_response({'error': '当前密码不正确'}, 401)
                    return
                if password_matches(new, auth):
                    raise ValueError('新密码不能与当前密码相同')
                salt = secrets.token_hex(16)
                digest = hashlib.pbkdf2_hmac('sha256', new.encode(), bytes.fromhex(salt), 200000).hex()
                c.execute('UPDATE admin_credentials SET salt=?,password_hash=?,must_change=0 WHERE id=1', (salt,digest))
                # Invalidate other browsers while preserving the caller's session.
                for key in [key for key,value in SESSIONS.items() if value is not session]:
                    SESSIONS.pop(key)
                LOGIN_FAILURES.clear()
            self.json_response({'ok': True, 'mustChangePassword': False})
        elif p in ('/api/sites/save', '/api/sites/delete', '/api/sites/toggle'):
            with LOCK, connection() as c:
                site_id = body.get('id')
                if p == '/api/sites/save':
                    name, url = str(body.get('name', '')).strip(), str(body.get('url', '')).strip()
                    if not name or len(name) > 40:
                        raise ValueError('网站名称为 1–40 个字符')
                    if body.get('interval') not in (1, 5, 10, 30):
                        raise ValueError('检查间隔必须为 1、5、10 或 30 分钟')
                    validated_url(url)
                    category = str(body.get('category', '其他网站'))[:40]
                    existing = c.execute('SELECT id FROM sites WHERE url=? AND id!=?', (url, site_id or '')).fetchone()
                    if existing:
                        raise ValueError('这个网站已经存在')
                    if site_id:
                        if not c.execute('SELECT id FROM sites WHERE id=?', (site_id,)).fetchone():
                            raise ValueError('网站不存在')
                        c.execute("UPDATE sites SET name=?,url=?,interval=?,category=?,next_due=0,status='pending' WHERE id=?", (name,url,body['interval'],category,site_id))
                    else:
                        if c.execute('SELECT count(*) FROM sites').fetchone()[0] >= MAX_SITES:
                            raise ValueError('最多监控 30 个网站')
                        c.execute('INSERT INTO sites(id,name,url,interval,category) VALUES(?,?,?,?,?)', (uuid.uuid4().hex,name,url,body['interval'],category))
                elif p == '/api/sites/delete':
                    c.execute('DELETE FROM sites WHERE id=?', (site_id,))
                else:
                    c.execute("UPDATE sites SET paused=1-paused,status='pending',next_due=0 WHERE id=?", (site_id,))
                CACHE['expires'] = 0
            self.json_response({'ok': True})
        elif p == '/api/settings':
            if body.get('interval') not in (1,5,10,30) or body.get('threshold') not in (2,3,5) or type(body.get('alerts')) is not bool:
                raise ValueError('设置格式不正确')
            with LOCK, connection() as c:
                c.execute('UPDATE settings SET body=? WHERE id=1', (json.dumps({k: body[k] for k in DEFAULTS}),))
                CACHE['expires'] = 0
            self.json_response({'ok': True})
        elif p == '/api/check':
            with LOCK:
                if time.time() - getattr(self.server, 'last_manual', 0) < 30:
                    self.json_response({'error': '请等待 30 秒后再次巡检'}, 429)
                    return
                self.server.last_manual = time.time()
            threading.Thread(target=run_checks, args=(True,), daemon=True).start()
            self.json_response({'ok': True, 'queued': True}, 202)
        else:
            self.json_response({'error': '接口不存在'}, 404)


def main():
    initialize()
    threading.Thread(target=scheduler, daemon=True).start()
    bind = os.environ.get('PULSE_BIND', '0.0.0.0')
    server_class = IPv6Server if ':' in bind else Server
    http = server_class((bind, int(os.environ.get('PULSE_PORT', '8080'))), Handler)
    cert, key = os.environ.get('PULSE_CERT'), os.environ.get('PULSE_KEY')
    if cert and key:
        secure = server_class((bind, int(os.environ.get('PULSE_TLS_PORT', '8443'))), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        secure.socket = context.wrap_socket(secure.socket, server_side=True, do_handshake_on_connect=False)
        threading.Thread(target=secure.serve_forever, daemon=True).start()
    http.serve_forever()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
