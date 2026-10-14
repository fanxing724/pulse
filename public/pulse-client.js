window.Pulse = {
  state: {sites: [], history: [], trend: [], settings: {}},
  csrf: null,
  authenticated: false,
  mustChangePassword: false,
  updateAuth(info) {
    this.csrf = info.csrf ?? this.csrf;
    this.authenticated = !!info.authenticated;
    this.mustChangePassword = !!info.mustChangePassword;
    if (this.state.generatedAt) window.dispatchEvent(new CustomEvent('pulse:state', {detail: this.state}));
  },
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
    this.updateAuth(info);
    return info;
  },
  dialog({title,description,fields,primary='保存',onSubmit,onAction}) {
    return new Promise((resolve,reject) => {
      const overlay = document.createElement('div');
      overlay.className = 'modal-backdrop pulse-dialog';
      const app = document.querySelector('.app');
      if (app) {
        const style = getComputedStyle(app);
        for (const name of ['bg','surface','text','muted','border','green','light-green','hover','soft','red','orange'])
          overlay.style.setProperty('--'+name, style.getPropertyValue('--'+name));
      }
      const modal = document.createElement('div');
      modal.className = 'modal';
      modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-label',title);
      // These strings are static application templates; never insert server/user input here.
      modal.innerHTML = '<div class="modal-header"><div><span class="eyebrow">PULSE WORKSPACE</span><h2>'+title+'</h2></div><button class="icon-button pulse-close" type="button" aria-label="关闭账号弹窗">×</button></div><form><p class="modal-description">'+description+'</p>'+fields+'<p class="form-error" role="alert" hidden></p><div class="modal-actions"><button class="button secondary pulse-cancel" type="button">取消</button><button class="button primary" type="submit">'+primary+'</button></div></form>';
      overlay.appendChild(modal);document.body.appendChild(overlay);
      const previousFocus = document.activeElement, previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      const close = () => {overlay.remove();document.body.style.overflow=previousOverflow;previousFocus?.focus();};
      const cancel = () => {close();reject(new Error('已取消操作'));};
      modal.querySelector('.pulse-close').onclick=cancel;modal.querySelector('.pulse-cancel').onclick=cancel;
      modal.querySelector('input')?.focus();
      overlay.onkeydown=event=>{
        if (event.key==='Escape') cancel();
        if (event.key==='Tab') {
          const items=[...modal.querySelectorAll('input,button')].filter(x=>!x.disabled);
          const index=items.indexOf(document.activeElement);
          if(event.shiftKey&&index===0){event.preventDefault();items.at(-1).focus();}
          if(!event.shiftKey&&index===items.length-1){event.preventDefault();items[0].focus();}
        }
      };
      modal.querySelector('form').onsubmit=async event=>{
        event.preventDefault();const error=modal.querySelector('.form-error');const submit=modal.querySelector('button[type=submit]');
        submit.disabled=true;error.hidden=true;
        try {await onSubmit(new FormData(event.currentTarget));close();resolve();}
        catch(e){error.hidden=false;error.textContent=e.message;}
        finally{submit.disabled=false;}
      };
      for (const button of modal.querySelectorAll('[data-account-action]')) {
        button.onclick=async()=>{
          close();
          try{await onAction(button.dataset.accountAction);resolve();}
          catch(error){reject(error);}
        };
      }
    });
  },
  async ensureAdmin() {
    const info = await this.auth();
    if (!info.secure) {
      alert('当前为公开查看入口。管理操作请使用 HTTPS 安全入口。');
      throw new Error('请使用 HTTPS 安全入口');
    }
    if (!info.authenticated) {
      if (!this.loginPending) this.loginPending=this.dialog({
        title:'管理员登录',description:'登录后可管理网站、查看检查结果和修改账号密码。',
        fields:'<label class="form-label">管理员密码<input type="password" name="password" autocomplete="current-password" placeholder="请输入密码" required maxlength="256"></label>',primary:'登录',
        onSubmit:async form=>{
          const response=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:form.get('password')})});
          const result=await response.json();if(!response.ok)throw new Error(result.error||'登录失败');this.updateAuth(result);
        }
      }).finally(()=>{this.loginPending=null;});
      await this.loginPending;
    }
    if (this.mustChangePassword) await this.changePassword(true);
  },
  async changePassword(initial=false) {
    if (this.passwordPending) return this.passwordPending;
    this.passwordPending=this.dialog({
      title:initial?'设置管理密码':'修改管理密码',description:initial?'首次登录，请将初始密码 admin 改为你自己的密码。':'修改后，其他浏览器中的登录会失效。',
      fields:'<label class="form-label">当前密码<input type="password" name="currentPassword" autocomplete="current-password" required maxlength="256"></label><label class="form-label">新密码<input type="password" name="newPassword" autocomplete="new-password" placeholder="8–128 个字符" required minlength="8" maxlength="128"></label><label class="form-label">确认新密码<input type="password" name="confirmation" autocomplete="new-password" required minlength="8" maxlength="128"></label>',
      primary:'保存密码',onSubmit:async form=>{
        if(form.get('newPassword')!==form.get('confirmation'))throw new Error('两次输入的新密码不一致');
        const response=await fetch('/api/password',{method:'POST',headers:{'Content-Type':'application/json','X-Pulse-CSRF':this.csrf},body:JSON.stringify({currentPassword:form.get('currentPassword'),newPassword:form.get('newPassword')})});
        const result=await response.json();if(!response.ok)throw new Error(result.error||'密码修改失败');await this.auth();
      }
    }).finally(()=>{this.passwordPending=null;});
    return this.passwordPending;
  },
  async openAccount() {
    const wasAuthenticated=(await this.auth()).authenticated;
    await this.ensureAdmin();
    if (!wasAuthenticated) return;
    await this.dialog({title:'账号设置',description:'你已登录管理员账号。可以修改密码或退出当前登录。',
      fields:'<div class="pulse-account-actions"><button type="button" class="button secondary" data-account-action="password">修改密码</button><button type="button" class="button secondary" data-account-action="logout">退出登录</button></div>',primary:'关闭',onSubmit:async()=>{},
      onAction:async action=>{if(action==='password')await this.changePassword();else if(action==='logout')await this.logout();}
    }).catch(error=>{if(error.message!=='已取消操作')throw error;});
  },
  async logout() {
    const response=await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json','X-Pulse-CSRF':this.csrf},body:'{}'});
    if(!response.ok)throw new Error('退出失败');this.csrf=null;this.updateAuth({authenticated:false,mustChangePassword:false});
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
