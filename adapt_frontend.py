"""Adapt the supplied compiled UI; keep original layout, CSS and interactions.

The immutable downloaded bundles live under vendor/ for reproducible adaptation.
Replace this bridge with a source build when the original source becomes available.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parent
vendor = ROOT / 'vendor'
assets = ROOT / 'public' / 'assets'
s = (vendor / 'page.js').read_text()


def replace(old, new):
    global s
    if s.count(old) != 1:
        raise RuntimeError('Expected one frontend anchor: ' + old[:100])
    s = s.replace(old, new)


replace('C.useState(ws)', 'C.useState([])')
replace('C.useState(wa)', 'C.useState([])')
replace('C.useState("14:59:52")', 'C.useState("等待检查")')
anchor = 'function Dt(p){'
hook = '''const prefRef=C.useRef(null);C.useEffect(()=>{let alive=true;const load=event=>{if(!alive)return;const data=event.detail;t(data.sites);i(data.history);go(data.updated);const prefs=JSON.stringify(data.settings);if(prefs!==prefRef.current){prefRef.current=prefs;Ct(String(data.settings.interval));Pt(String(data.settings.threshold));fo(data.settings.alerts)}};window.addEventListener("pulse:state",load);const fetchData=()=>window.Pulse.refresh().catch(error=>{if(alive)Dt(error.message)});fetchData();const timer=setInterval(fetchData,15000);return()=>{alive=false;clearInterval(timer);window.removeEventListener("pulse:state",load)}},[]);'''
replace(anchor, hook + anchor)
replace('function Q(p,O=null){M(O),y(p),pt(""),z(null)}', 'function Q(p,O=null){if(["add","edit","delete","settings"].includes(p)){window.Pulse.ensureAdmin().then(()=>{M(O),y(p),pt(""),z(null)}).catch(error=>Dt(error.message));return}M(O),y(p),pt(""),z(null)}')
start = s.index('function xo(p){')
end = s.index('function yo(){', start)
s = s[:start] + '''async function xo(p){p.preventDefault();const form=new FormData(p.currentTarget);const payload={id:v==="edit"?k?.id:null,name:String(form.get("name")||"").trim(),url:String(form.get("url")||"").trim(),interval:Number(form.get("interval")),category:String(form.get("category"))};try{await window.Pulse.write("/api/sites/save",payload);Dt(v==="edit"?"网站配置已保存":"网站已添加，后台即将检查");y(null);u("");g("all")}catch(error){pt(error.message)}}async function _o(){if(!Xs.length){Dt("请先添加或启用一个网站");return}X(true);try{await window.Pulse.write("/api/check",{});Dt("后台巡检已启动，结果将自动更新")}catch(error){Dt(error.message)}finally{X(false)}}''' + s[end:]
replace('onClick:()=>{t(O=>O.map(H=>H.id===p.id?{...H,status:H.status==="paused"?"pending":"paused"}:H)),z(null),Dt(p.status==="paused"?"已恢复，等待演示检查":"已暂停演示监控")}', 'onClick:async()=>{try{await window.Pulse.write("/api/sites/toggle",{id:p.id});z(null);Dt(p.status==="paused"?"已恢复监控":"已暂停监控")}catch(error){Dt(error.message)}}')
replace('onClick:()=>{t(p=>p.filter(O=>O.id!==k.id)),i(p=>p.filter(O=>O.siteId!==k.id)),w===k.id&&j("all"),at(1),y(null),Dt("网站已从演示工作空间移除")}', 'onClick:async()=>{try{await window.Pulse.write("/api/sites/delete",{id:k.id});w===k.id&&j("all");at(1);y(null);Dt("网站及访问记录已删除")}catch(error){Dt(error.message)}}')
replace('onClick:()=>{y(null),Dt("演示偏好已应用")}', 'onClick:async()=>{try{await window.Pulse.write("/api/settings",{interval:Number(mt),threshold:Number(st),alerts:it});y(null);Dt("监控设置已保存")}catch(error){Dt(error.message)}}')
replace('h.jsx(qh,{range:m,metric:x,dark:a,siteId:w})', 'h.jsx(qh,{range:m,metric:x,dark:a,siteId:w,version:Ys})')
replace('children:p.status==="pending"?"等待检查":p.status==="paused"?"已暂停":Ys', 'children:p.status==="pending"?"等待检查":p.status==="paused"?"已暂停":p.lastCheck')
start = s.index('function qh(')
end = s.index('function ', start+10)
chart = s[start:end]
chart_start = chart.index('const n=')
chart_end = chart.index('h.jsx(Yh,')
chart = chart[:chart_start] + 'const graph=window.Pulse.graph(s,t,i),a=graph.values,l=graph.labels;return a.length?' + chart[chart_end:]
chart = chart.replace('演示趋势图', '真实趋势图').replace('callback:(c,d)=>s==="24h"?`${String(Math.floor(d/2)).padStart(2,"0")}:00`:r(d)', 'callback:(c,d)=>l[d]').replace('min:t==="response"?0:95', 'min:0')
s = s[:start] + chart + s[end:]
start=s.index('function yn(')
end=s.index('function ',start+10)
s=s[:start]+'''function yn({failing:s=!1,siteId:id="all"}){const data=window.Pulse.graph("24h","response",id).values.slice(-16);if(data.length<2)return null;const low=Math.min(...data),high=Math.max(...data);const path=data.map((v,i)=>(i?"L":"M")+(i*100/(data.length-1)).toFixed(1)+" "+(24-(v-low)/(high-low||1)*20).toFixed(1)).join("");return h.jsx("svg",{viewBox:"0 0 100 28",className:`sparkline ${s?"failing":""}`,"aria-hidden":"true",children:h.jsx("path",{d:path,fill:"none",stroke:"currentColor",strokeWidth:1.6})})}'''+s[end:]
replace('h.jsx(yn,{failing:p.status==="error"||p.status==="timeout"})','h.jsx(yn,{failing:p.status==="error"||p.status==="timeout",siteId:p.id})')
translations = {
 'pulse-demo-history.csv':'pulse-history.csv', '已导出当前筛选的演示记录':'已导出当前筛选的访问记录',
 '系统演示正常运行':'后台定时巡检运行中', '演示工作空间':'公开监控面板', '所有网站演示均值':'过去 24 小时各网站均值',
 '演示数据':'真实数据', '历史示例 · 不含新增网站实测':'历史实测 · 北京时间',
 '演示状态 · 最近更新于 ':'数据同步于 ', '操作仅在当前页面有效':'服务器持久保存配置和检查记录',
 '」将从当前演示工作空间移除，对应的演示记录也会一并删除。':'」将从工作空间移除，对应检查记录也会一并删除。',
 '为新网站设置默认规则。以下偏好仅在当前演示页面生效。':'为新网站设置默认规则，保存后会在服务器持久生效。',
 '自动巡检与持久化配置将在后续阶段接入；此处不启动定时任务。':'浏览器关闭后，服务器仍会按网站设置的间隔执行检查。',
 '此版本是可交互产品预览，全部指标与巡检结果均为演示，不进行真实请求。':'指标来自本服务器的真实 HTTP 检查，不代表所有地区的访问质量。历史保留 7 天。',
 '新增网站的真实趋势将在巡检引擎接入后展示。':'首次巡检后会开始累计真实历史。',
 '接入 Netlify Database，保存网站配置与检查历史。':'SQLite 保存网站配置与检查历史，管理操作需要登录。',
 '接入 Deno Cron / fetch，处理超时、重试和按间隔调度。':'服务器按间隔执行 HTTP 检查，限制并发和请求时长。',
 '当前为交互演示，网站配置不会永久保存，也不会自动发出请求。':'网站配置保存在服务器，添加后会按间隔自动检查。',
 '真实统计与异常通知':'真实统计与面板提醒',
 '连接实时趋势与可用率，扩展 Telegram / Discord 通知。':'真实趋势、24 小时可用率与连续失败横幅；暂不发送外部通知。',
}
for old,new in translations.items():
    s=s.replace(old,new)
s=s.replace('done:!1', 'done:!0')
s=s.replace('演示','真实')
start=s.index('ws=[')
end=s.index('function pe(',start)
s=s[:start]+'ws=[],Ie={online:"在线",error:"异常",timeout:"超时",paused:"已暂停",pending:"待检查"},wa=[],kn=[],wn=[],ja=[],Ma=[];'+s[end:]
(assets/'index-Cko_AG74.js').write_text(s)
runtime=(vendor/'runtime.js').read_text()
old='st.startTransition(()=>{rS.hydrateRoot(document,$.jsx(st.StrictMode,{children:$.jsx(PE,{})}))});'
assert runtime.count(old)==1
runtime=runtime.replace(old,'')
runtime=runtime.replace('export{$ as j,st as r};','export{$ as j,st as r,rS as dom};')
(assets/'index-B_1BCP1J.js').write_text(runtime)
