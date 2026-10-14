window.Pulse = {
  state: {sites: [], history: [], trend: [], settings: {}},
  csrf: null,
  async refresh() {
    const response = await fetch('/api/state');
    if (!response.ok) throw new Error('无法读取监控数据');
    const data = await response.json();
    this.state = data;
    window.dispatchEvent(new CustomEvent('pulse:state', {detail: data}));
    return data;
  },
  async auth() {
    const response = await fetch('/api/session', {cache: 'no-store'});
    if (!response.ok) throw new Error('无法读取登录状态');
    const info = await response.json();
    this.csrf = info.csrf;
    return info;
  },
  async ensureAdmin() {
    const info = await this.auth();
    if (info.authenticated) return;
    if (!info.secure) {
      alert('当前为公开查看入口。管理操作请使用 HTTPS 安全入口。');
      throw new Error('请使用 HTTPS 安全入口');
    }
    if (this.loginPending) return this.loginPending;
    this.loginPending = new Promise((resolve, reject) => {
      const overlay = document.createElement('div');
      overlay.className = 'modal-backdrop pulse-login';
      const modal = document.createElement('div');
      modal.className = 'modal';
      modal.setAttribute('role', 'dialog');
      modal.setAttribute('aria-modal', 'true');
      modal.setAttribute('aria-label', '管理员登录');
      modal.innerHTML = '<div class="modal-header"><div><span class="eyebrow">PULSE WORKSPACE</span><h2>管理员登录</h2></div></div><form><p class="modal-description">登录后可管理网站和运行巡检。公开访客可以查看状态。</p><label class="form-label">管理密码<input type="password" name="password" autocomplete="current-password" required maxlength="256"></label><p class="form-error" role="alert" hidden></p><div class="modal-actions"><button class="button secondary" type="button">取消</button><button class="button primary" type="submit">登录</button></div></form>';
      overlay.appendChild(modal);
      document.body.appendChild(overlay);
      const input = modal.querySelector('input');
      input.focus();
      const cancel = () => { overlay.remove(); reject(new Error('已取消登录')); };
      modal.querySelector('button[type=button]').onclick = cancel;
      overlay.onkeydown = event => {
        if (event.key === 'Escape') cancel();
        if (event.key === 'Tab') {
          const items = [...modal.querySelectorAll('input,button')];
          const index = items.indexOf(document.activeElement);
          if (event.shiftKey && index === 0) {event.preventDefault(); items.at(-1).focus();}
          if (!event.shiftKey && index === items.length - 1) {event.preventDefault(); input.focus();}
        }
      };
      modal.querySelector('form').onsubmit = async event => {
        event.preventDefault();
        const error = modal.querySelector('.form-error');
        const submit = modal.querySelector('button[type=submit]');
        submit.disabled = true;
        try {
          const response = await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:input.value})});
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || '登录失败');
          this.csrf = result.csrf;
          overlay.remove(); resolve();
        } catch(e) {error.hidden = false; error.textContent = e.message;}
        finally {submit.disabled = false;}
      };
    }).finally(() => {this.loginPending = null;});
    return this.loginPending;
  },
  async write(path, body) {
    await this.ensureAdmin();
    const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-Pulse-CSRF':this.csrf}, body:JSON.stringify(body)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '操作失败');
    await this.refresh();
    return result;
  },
  graph(range, metric, siteId) {
    const cutoff = Date.now()/1000 - (range === '24h' ? 86400 : 604800);
    const buckets = new Map();
    for (const sample of this.state.trend) {
      if (sample.timestamp < cutoff || (siteId !== 'all' && sample.siteId !== siteId)) continue;
      if (!buckets.has(sample.timestamp)) buckets.set(sample.timestamp, []);
      buckets.get(sample.timestamp).push(sample[metric]);
    }
    const entries = [...buckets.entries()].sort((a,b) => a[0]-b[0]);
    return {
      labels: entries.map(([time]) => new Date(time*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})),
      values: entries.map(([,samples]) => Math.round(samples.reduce((a,b)=>a+b,0)/samples.length*100)/100)
    };
  }
};
