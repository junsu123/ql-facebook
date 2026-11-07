/* AI Fanpage Company — local-first SPA (no external JS dependencies). */
'use strict';
const ROUTES=[
  ['office','🏢','Văn phòng 3D'],['ceo','🧠','AI CEO'],['growth','🚀','Tăng trưởng 7 ngày'],['pages','📣','100 Fanpage'],
  ['accounts','🦊','Tài khoản Firefox'],['content','📝','Nội dung & Lịch'],
  ['tasks','✅','Nhiệm vụ AI'],['insights','📊','Báo cáo & Bộ nhớ'],['brains','🧠','Bộ não nhân viên'],['academy','🎓','Học viện 10M'],['settings','⚙️','Cài đặt']
];
const S={data:null,route:(location.hash.slice(1)||'office'),busy:false,taskFilter:'all',growthDetailId:null};
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const F=(date)=>date?new Date(date).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}):'—';
const short=(s,n=105)=>String(s||'').length>n?String(s).slice(0,n)+'…':String(s||'');
const locate=()=>new Date().toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'full',timeStyle:'short'});
const V=id=>(S.data?.[id]||[]);
const selected=(x,y)=>x===y?'selected':'';
const agentName=id=>V('agents').find(a=>a.id===id)?.name||id;
const pageName=id=>V('pages').find(a=>a.id===id)?.name||'Không có Page';
const badge=(s)=>{
  const labels={queued:['Chờ xử lý','yellow'],running:['Đang làm','blue'],done:['Hoàn thành','green'],failed:['Lỗi','red'],
    draft:['Bản nháp',''],approved:['Đã duyệt','green'],needs_revision:['Cần sửa','red'],scheduled:['Đã lên lịch','blue'],ready:['Đến lịch / Chờ đăng','yellow'],published_manual:['Đã đăng (tự xác nhận)','green'],
    created:['Mới tạo',''],open:['Firefox đang mở','blue'],closed:['Đã đóng',''],confirmed:['Đã xác nhận','green']};
  const b=labels[s]||[s||'Chưa rõ',''];return `<span class="badge ${b[1]}">${E(b[0])}</span>`;
};
async function api(path,method='GET',body=undefined){
  const opts={method,headers:{}};
  if(body instanceof FormData){opts.body=body;}
  else if(body!==undefined){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body);}
  let response;
  try{response=await fetch(path,opts);}catch(err){throw new Error('Không kết nối được máy chủ: '+err.message);}
  const obj=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof obj.detail==='string'?obj.detail:JSON.stringify(obj.detail||obj));
  return obj;
}
let toastTimer=0;
function toast(message,bad=false){
  const root=document.getElementById('toast-root');const item=document.createElement('div');item.className='toast'+(bad?' bad':'');item.textContent=message;root.append(item);setTimeout(()=>item.remove(),5400);
}
function modal(title,html,actionLabel='',onSubmit=null){
  const root=document.getElementById('modal-root');
  root.innerHTML=`<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true"><div class="modal-head"><h2>${E(title)}</h2><button class="x-button" data-action="modal.close">✕</button></div><form id="modal-form">${html}<div class="modal-actions"><button type="button" data-action="modal.close" class="btn ghost">Hủy</button>${onSubmit?`<button class="btn primary" type="submit">${E(actionLabel||'Lưu')}</button>`:''}</div></form></div></div>`;
  root.querySelector('.modal-backdrop').addEventListener('click',e=>{if(e.target.classList.contains('modal-backdrop'))closeModal();});
  if(onSubmit)root.querySelector('#modal-form').addEventListener('submit',async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;try{await onSubmit(Object.fromEntries(new FormData(e.target).entries()),e.target);closeModal();await reload();}catch(err){toast(err.message,true);btn.disabled=false;}});
}
function closeModal(){document.getElementById('modal-root').innerHTML='';}
const field=(label,name,value='',kind='text',extra='')=>`<div class="form-field"><label>${E(label)}</label>${kind==='textarea'?`<textarea class="textarea" name="${name}" ${extra}>${E(value)}</textarea>`:`<input class="input" type="${kind}" name="${name}" value="${E(value)}" ${extra}>`}</div>`;
const pick=(label,name,options,value='',none='— Chọn —')=>`<div class="form-field"><label>${E(label)}</label><select class="select" name="${name}"><option value="">${E(none)}</option>${options.map(o=>`<option value="${E(o.value)}" ${selected(o.value,value)}>${E(o.label)}</option>`).join('')}</select></div>`;
const pageOptions=()=>V('pages').map(p=>({value:p.id,label:p.name}));
const accountOptions=()=>V('accounts').map(p=>({value:p.id,label:p.label+' ('+p.id+')'}));
function heading(title,subtitle,actions=''){
  return `<div class="page-heading"><div><span class="smallcaps">AI FANPAGE COMPANY</span><h1>${title}</h1><p>${subtitle}</p></div><div class="toolbar">${actions}</div></div>`;
}
function empty(emoji,text,desc=''){
  return `<div class="empty"><span class="big">${emoji}</span><strong>${text}</strong><span>${desc}</span></div>`;
}
function nav(){
  document.getElementById('sidebar-nav').innerHTML=ROUTES.map(([id,icon,label])=>`<button class="nav-item ${id===S.route?'active':''}" data-route="${id}"><span class="nav-ico">${icon}</span><span>${label}</span></button>`).join('');
  const current=ROUTES.find(r=>r[0]===S.route)||ROUTES[0];
  document.getElementById('topbar').innerHTML=`<div class="crumb">🏠 / <strong>${current[2]}</strong></div><div class="top-actions"><span class="status-bubble"><span class="dot green"></span><span>Hệ thống nội bộ</span></span><span class="top-label">${E(locate())}</span><button class="btn ghost sm" data-action="refresh" title="Làm mới">↻</button><div class="avatar">👤</div></div>`;
}
function stat(icon,name,value,mini,color){return `<div class="stat" style="--color:${color}"><span class="stat-icon">${icon}</span><div class="name">${name}</div><div class="value">${E(value)}</div><div class="mini">${mini}</div></div>`;}
function renderOffice(){
  const d=S.data,c=d.counts,activity=V('activities');
  return `${heading('Văn phòng AI sống động','Nhân vật tí hon 3D phong cách isometric có thể đi lại, trao đổi và làm việc theo trạng thái nhiệm vụ.',`<button class="btn primary" data-route="ceo">🧠 Giao việc cho CEO</button>`)}
    <div class="stat-grid" id="office-stats">${stat('📣','Fanpage đã liên kết',c.pages+'/100','Hồ sơ nội bộ','#9782ff')}${stat('🦊','Profile Firefox',c.accounts,'Tài khoản độc lập','#78baff')}${stat('⚡','Nhiệm vụ đang xử lý',c.running,'Trạng thái backend','#64e6b4')}${stat('📝','Nội dung chờ xử lý',c.drafts+c.ready,'Bản nháp và bài đến lịch','#ffc17c')}</div>
    <div class="office-live-toolbar">
      <div class="office-live-title"><span class="live-mark">✦</span><strong>Văn phòng tí hon trực tiếp</strong><span class="badge blue" id="office-live-state">${c.running?'Có nhân viên đang làm việc':'Đang sẵn sàng'}</span></div>
      <div class="toolbar"><button class="btn sm ghost" data-action="office.toggle" id="office-toggle">⏸ Tạm dừng</button>
        <button class="btn sm ghost" data-action="office.speed" id="office-speed">⚡ 1x</button>
        <button class="btn sm ghost" data-action="office.zoom-in" aria-label="Phóng to">＋</button>
        <button class="btn sm ghost" data-action="office.zoom-out" aria-label="Thu nhỏ">－</button>
        <button class="btn sm ghost" data-action="office.reset">⤾ Về mặc định</button></div>
    </div>
    <div class="office-layout"><div>
      <div class="office-live-stage" id="office-live-stage"><div class="office-live-loading">Đang khởi tạo văn phòng hoạt hình...</div></div>
      <div class="office-note">Nhân vật đi lại, trò chuyện và thao tác bàn làm việc là <strong>chuyển động minh họa</strong>. Chỉ trạng thái nhiệm vụ, số lượng công việc và nhật ký mới là dữ liệu backend thật. Nhấp một nhân viên để xem nhiệm vụ; kéo để di chuyển góc nhìn, cuộn để phóng to.</div>
      <div class="grid-2" style="margin-top:16px"><div class="card"><div class="space-between"><h2>📅 Công việc xuất bản</h2><button class="btn sm ghost" data-route="content">Xem lịch →</button></div><div class="subtle-divider"></div><p>${c.scheduled} bài đã lên lịch, ${c.ready} bài đến giờ cần đăng thủ công.</p><p class="card-sub">Không dùng Facebook API hay bot đăng bài. Firefox mở đúng Page để bạn hoàn tất xuất bản.</p></div><div class="card"><div class="space-between"><h2>🧠 Bộ nhớ doanh nghiệp</h2><button class="btn sm ghost" data-route="insights">KPI →</button></div><div class="subtle-divider"></div><p>Đã ghi nhận ${V('metrics').length} dòng KPI gần đây.</p><p class="card-sub">Khi đủ số liệu hợp lệ, hệ thống có thể ghi nhớ và tổng hợp kinh nghiệm theo từng Page.</p></div></div>
    </div><div class="office-side"><div class="card"><div class="space-between"><h2>👥 Nhân viên AI</h2><span class="badge blue">9 Agent</span></div><div class="subtle-divider"></div><div id="office-agent-list">${officeAgentList(d.agents)}</div></div><div class="card"><div class="space-between"><h2>🔔 Nhật ký mới nhất</h2><button class="btn sm ghost" data-route="tasks">Tất cả →</button></div><div id="office-activity-list">${officeActivityList(activity)}</div></div></div></div>`;
}
function officeAgentList(agents){
  return agents.map(a=>`<button class="agent-mini agent-mini-button" data-action="agent.details" data-id="${E(a.id)}" title="Xem ${E(a.name)}">
    <span class="agent-face">${a.emoji}</span><span style="flex:1;text-align:left"><strong>${E(a.name)}</strong><small>${a.active_tasks?`Đang thực hiện ${a.active_tasks} việc`:a.queued_tasks?`${a.queued_tasks} việc chờ`:'Sẵn sàng nhận việc'}</small></span><span class="dot ${a.active_tasks?'green':a.queued_tasks?'yellow':''}"></span></button>`).join('');
}
function officeActivityList(activity){
  return activity.length?activity.slice(0,7).map(a=>`<div class="activity-item"><strong>${E(a.agent_name||'Hệ thống')} · ${E(a.kind)}</strong><p>${E(short(a.message,115))}</p><time>${F(a.created)}</time></div>`).join(''):empty('📋','Chưa có hoạt động','Thử tạo tài khoản hoặc giao việc cho CEO.');
}
function updateOfficeData(){
  const c=S.data?.counts;if(!c)return;
  const values=[c.pages+'/100',c.accounts,c.running,c.drafts+c.ready];
  document.querySelectorAll('#office-stats .stat .value').forEach((x,i)=>x.textContent=values[i]);
  const status=document.getElementById('office-live-state');if(status)status.textContent=c.running?'Có nhân viên đang làm việc':'Đang sẵn sàng';
  const staff=document.getElementById('office-agent-list');if(staff)staff.innerHTML=officeAgentList(V('agents'));
  const activity=document.getElementById('office-activity-list');if(activity)activity.innerHTML=officeActivityList(V('activities'));
  window.OfficeLive?.update(S.data);
}
function renderCEO(){
  const chat=V('chat');
  return `${heading('Phòng điều hành AI CEO','Bạn chỉ giao việc cho CEO. CEO phân tích mục tiêu và tạo nhiệm vụ cho đội ngũ.',`<button class="btn ghost" data-action="tasks.run-queued">▶ Chạy nhiệm vụ chờ</button><button class="btn primary" data-action="ceo.campaign">✦ Tạo chiến dịch nhiều Page</button>`)}
  <div class="columns"><div class="card chat-room"><div class="space-between"><div><h2>🧠 Trao đổi trực tiếp với CEO</h2><div class="card-sub">Claude AI · ${S.data.settings.claude_configured?'Đã có API key':'Chưa có API key'} · Tự chọn model tiết kiệm</div></div><span class="badge blue">CEO</span></div>
    <div class="chat-messages" id="chatMessages">${chat.length?chat.map(m=>`<div class="chat-msg ${m.role==='user'?'owner':''}"><div class="chat-av">${m.role==='user'?'👤':'🧠'}</div><div><div class="chat-bubble">${E(m.body)}</div><small class="muted">${F(m.created)}</small></div></div>`).join(''):empty('🧠','Bắt đầu giao việc cho CEO','Ví dụ: Lập chiến lược 7 ngày cho các Page về trà thảo mộc.')}</div>
    <form id="chatForm" class="chat-compose"><textarea class="textarea" name="message" maxlength="6000" required placeholder="CEO, hãy lập kế hoạch nội dung cho các Fanpage của công ty..."></textarea><button class="btn primary" ${S.busy?'disabled':''}>${S.busy?'Đang suy luận…':'Giao việc ↗'}</button></form></div>
    <div class="stack"><div class="card"><h2>🎯 Nguyên tắc quản trị</h2><div class="subtle-divider"></div><p>CEO chỉ được giao nhiệm vụ nội bộ, tạo kế hoạch và đề xuất. Nhân viên không được tự nhận đã đăng bài hay thu thập dữ liệu không có thật.</p><div class="status-bubble">🔒 Chỉ tự động hóa nội bộ; không tự thao tác Facebook</div></div>
      <div class="card"><h2>🔍 Công việc gần đây</h2>${V('tasks').slice(0,6).map(t=>`<div class="agent-mini"><div class="agent-face">${V('agents').find(a=>a.id===t.agent_id)?.emoji||'🤖'}</div><div style="flex:1"><strong>${E(short(t.title,50))}</strong><small>${E(agentName(t.agent_id))} · ${F(t.created)}</small></div>${badge(t.status)}</div>`).join('')||empty('📭','Chưa có nhiệm vụ')}</div>
      <div class="card"><h2>⚙️ Kết nối trí tuệ AI</h2><p class="muted">Chỉ cần nhập một Claude API key trong phần Cài đặt. Không có API key, CEO chỉ lưu yêu cầu vào hàng đợi và không bịa ra hành động đã thực hiện.</p><button class="btn ghost" data-route="settings">Mở cài đặt AI →</button></div>
    </div></div>`;
}
function firefoxInstallerNotice(){
  const state=S.data?.firefox_installer||{};
  if(state.installed||S.data?.firefox_available){
    return `<div class="ok-note">✅ Firefox đã được phát hiện trên máy. <span class="meta">${E(state.executable||'')}</span></div>`;
  }
  const support=state.support||{};
  const working=['downloading','verifying','installer_opened','checking'].includes(state.state);
  const pct=typeof state.percent==='number'?Math.min(100,Math.max(0,state.percent)):null;
  const detail=state.state==='downloading'?(pct!==null?`Đã tải ${pct}%`:'Đang tải bộ cài…'):
    state.state==='verifying'?'Đang kiểm tra chữ ký số của Mozilla…':
    state.state==='installer_opened'?'Trình cài Firefox đã mở. Vui lòng hoàn tất cài đặt và chấp thuận UAC nếu đồng ý.':
    state.message||'Không tìm thấy Firefox trên máy chạy phần mềm.';
  return `<div class="card" style="margin-bottom:16px;border-color:rgba(255,187,78,.35)">
    <h2>🦊 Firefox chưa được cài đặt</h2>
    <p class="muted">${E(detail)}</p>
    ${pct!==null&&state.state==='downloading'?`<div style="width:100%;height:9px;border-radius:99px;background:rgba(120,130,155,.25);overflow:hidden"><div style="height:100%;width:${pct}%;background:#8d7bff;transition:width .25s"></div></div>`:''}
    ${state.error?`<div class="warn">${E(state.error)}</div>`:''}
    ${!support.supported?`<div class="warn">${E(support.reason||'Cài đặt tự động không khả dụng trên hệ điều hành này.')}</div>`:''}
    <div class="actions">
      ${support.supported&&!working?'<button class="btn primary" data-action="firefox.install">⬇️ Tải và cài Firefox</button>':''}
      <button class="btn ghost" data-action="firefox.recheck">↻ Kiểm tra lại</button>
      <a class="btn ghost" target="_blank" rel="noopener noreferrer" href="https://www.firefox.com/vi/firefox/new/">Trang Mozilla chính thức</a>
    </div>
    <p class="meta">Phần mềm chỉ tải bản Firefox ổn định phù hợp với kiến trúc Windows; xác minh chữ ký số trước khi chạy. Việc cài đặt được thực hiện qua trình cài chính thức, không âm thầm thay đổi máy.</p>
  </div>`;
}
let firefoxPoll=null;
function startFirefoxInstallerPoll(){
  if(firefoxPoll)return;
  firefoxPoll=setInterval(async()=>{
    try{
      const x=await api('/api/firefox/installer');
      if(!S.data)return;
      S.data.firefox_installer=x;S.data.firefox_available=x.installed;
      if((S.route==='accounts'||S.route==='settings')&&!document.querySelector('#modal-root .modal'))render();
      if(x.state==='completed'||x.state==='error'||x.state==='attention'||x.state==='idle'){
        clearInterval(firefoxPoll);firefoxPoll=null;
        if(x.state==='completed'){toast('Firefox đã được cài đặt và nhận diện. Bạn có thể tạo tài khoản.');await reload();}
        else if(x.state==='error')toast(x.error||'Cài Firefox không thành công.',true);
      }
    }catch(err){clearInterval(firefoxPoll);firefoxPoll=null;toast(err.message,true);}
  },1500);
}
function firefoxInstallerDialog(){
  const info=S.data?.firefox_installer;
  if(info?.installed||S.data?.firefox_available){toast('Firefox đã được cài đặt.');return;}
  if(!info?.support?.supported){toast(info?.support?.reason||'Không hỗ trợ cài Firefox trên hệ điều hành này.',true);return;}
  modal('⬇️ Cài đặt Firefox từ Mozilla',
    `<p>Phần mềm sẽ tự chọn bộ cài Firefox <strong>${E(info.support.architecture)}</strong> cho máy Windows của bạn, tải qua HTTPS và kiểm tra chữ ký số <strong>Mozilla Corporation</strong>.</p>
     <div class="office-note">Sau khi xác minh, trình cài Firefox sẽ mở để <strong>bạn tự xác nhận cài đặt/UAC</strong>. Không cài đặt âm thầm, không cài extension và không truy cập mật khẩu Facebook.</div>
     <p class="muted">Nguồn: <a href="https://www.firefox.com/vi/firefox/new/" target="_blank" rel="noopener noreferrer">Mozilla Firefox chính thức</a></p>`,
    'Tôi đồng ý tải và mở bộ cài',async()=>{
      await api('/api/firefox/installer','POST');
      toast('Đang tải bộ cài từ Mozilla…');
      startFirefoxInstallerPoll();
    });
}
function renderAccounts(){
  const accounts=V('accounts');
  return `${heading('Tài khoản Facebook','Mỗi tài khoản = một Firefox Profile cố định trên máy Windows.',`<button class="btn primary" data-action="account.add">＋ Thêm tài khoản</button>`)}
    <div class="stat-grid">${stat('🦊','Profile hiện có',accounts.length,'Lưu tại máy chủ cục bộ','#b887ff')}${stat('🟢','Firefox đang mở',accounts.filter(a=>a.browser_open).length,'Tiến trình được nhận diện','#74dbae')}${stat('✅','Đã xác nhận thủ công',accounts.filter(a=>a.confirmed).length,'Không xác minh qua Facebook','#7faaff')}${stat('📣','Fanpage đã liên kết',V('pages').filter(p=>p.account_id).length,'Theo khai báo chủ sở hữu','#ffcd83')}</div>
    ${S.data.firefox_available?'':firefoxInstallerNotice()}
    <div class="warn">⚠️ Phiên đăng nhập Facebook chỉ được bạn xác nhận thủ công. Phần mềm không đọc cookie, không lấy mật khẩu, không cài extension, không khẳng định tự kiểm tra quyền Page.</div>
    <div class="grid-2" style="margin-top:17px">${accounts.length?accounts.map(a=>`<div class="item-card"><div class="space-between"><div><h3>🦊 ${E(a.label)}</h3><div class="meta">${E(a.id)} · ${V('pages').filter(p=>p.account_id===a.id).length} Fanpage</div></div>${badge(a.browser_open?'open':a.status)}</div>
      <p>Đăng nhập: ${a.confirmed?'<span class="badge green">Người dùng đã xác nhận</span>':'<span class="badge yellow">Chưa xác nhận</span>'}</p><p class="meta">Lần xác nhận: ${F(a.last_checked)}</p><p class="meta" style="overflow-wrap:anywhere">📁 ${E(a.profile_path)}</p>
      <div class="actions"><button class="btn sm primary" data-action="account.open" data-id="${a.id}">Mở Firefox</button><button class="btn sm ghost" data-action="account.confirm" data-id="${a.id}">Xác nhận đăng nhập</button><button class="btn sm ghost" data-action="account.reload" data-id="${a.id}">↻ Reload</button><button class="btn sm ghost" data-action="account.close" data-id="${a.id}">Đóng</button><button class="btn sm danger" data-action="account.delete" data-id="${a.id}">Xóa</button></div></div>`).join(''):empty('🦊','Chưa có tài khoản Firefox','Bấm Thêm tài khoản để tạo profile và mở trình duyệt.')}</div>
    <div class="footer-tip">Nếu máy chưa có Firefox, hãy tải và cài từ Mozilla bằng nút ở trên trước khi thêm tài khoản. Không tự đóng trình duyệt khi bạn đang nhập 2FA.</div>`;
}
function renderPages(){
  const pages=V('pages');
  return `${heading('Quản lý 100 Fanpage','Hồ sơ, chiến lược, thông tin sản phẩm và Firefox Profile gắn với từng Page.',`<button class="btn primary" data-action="page.add">＋ Thêm Fanpage</button>`)}
    <div class="card"><div class="space-between"><h2>📣 Danh sách Fanpage (${pages.length}/100)</h2><span class="badge">Không dùng Meta API</span></div><div class="subtle-divider"></div>
    ${pages.length?`<div class="table-scroll"><table class="data-table"><thead><tr><th>Fanpage</th><th>Ngành hàng</th><th>Tài khoản Firefox</th><th>Dữ liệu sản phẩm</th><th>Thao tác</th></tr></thead><tbody>${pages.map(p=>`<tr><td><strong>${E(p.name)}</strong><div class="meta">Mã: ${E(p.id)}</div><div class="meta"><a href="${E(p.url)}" target="_blank" rel="noopener noreferrer">${E(short(p.url,60))}</a></div></td><td>${E(p.category||'—')}</td><td>${E(V('accounts').find(a=>a.id===p.account_id)?.label||'Chưa liên kết')}</td><td>${p.facts?'<span class="badge green">Đã nhập dữ liệu</span>':'<span class="badge yellow">Chưa có dữ liệu</span>'}</td><td><div class="toolbar"><button class="btn sm ghost" data-action="page.edit" data-id="${p.id}">Sửa</button><button class="btn sm ghost" data-action="page.memory" data-id="${p.id}">Bộ nhớ</button><button class="btn sm danger" data-action="page.delete" data-id="${p.id}">Xóa</button></div></td></tr>`).join('')}</tbody></table></div>`:empty('📣','Chưa có Fanpage','Thêm Fanpage bằng URL và tài khoản Firefox có quyền quản trị.')}</div>
    <div class="office-note">Nhập URL chỉ tạo liên kết trong cơ sở dữ liệu; quyền quản trị Facebook chưa được kiểm tra tự động. Một tài khoản Firefox có thể liên kết nhiều Page nếu bạn thực sự có quyền.</div>`;
}
function renderContent(){
  const posts=V('contents');
  return `${heading('Trung tâm nội dung & Lịch','Tạo bài, kiểm duyệt tự động theo quy tắc, lên lịch và mở Firefox để đăng thủ công.',`<button class="btn ghost" data-action="content.generate">✦ AI viết bài</button><button class="btn primary" data-action="content.add">＋ Bản nháp</button>`)}
  <div class="stat-grid">${stat('📝','Bản nháp',posts.filter(p=>['draft','needs_revision'].includes(p.status)).length,'Chưa đạt yêu cầu','#a78af5')}${stat('✅','Được duyệt',posts.filter(p=>p.status==='approved').length,'Sẵn sàng lập lịch','#65ddb7')}${stat('📅','Lên lịch',posts.filter(p=>p.status==='scheduled').length,'Chờ đến giờ','#7abaff')}${stat('🚀','Đến lịch',posts.filter(p=>p.status==='ready').length,'Cần thao tác đăng','#ffc67e')}</div>
  <div class="stack">${posts.length?posts.map(p=>`<div class="item-card"><div class="space-between"><div><h3>${E(p.topic)}</h3><div class="meta">📣 ${E(p.page_name)} · ${F(p.created)} · Mã ${E(p.id)}</div></div>${badge(p.status)}</div>
    <p class="editor-preview">${E(short(p.body,650))}</p>${p.media_path?`<img src="${E(p.media_path)}" style="width:145px;max-height:100px;object-fit:cover;border-radius:9px" alt="Media đã tải lên">`:''}
    ${p.review_details?`<p class="meta">🛡️ ${E(short(p.review_details,350))}</p>`:''}${p.scheduled_at?`<p class="meta">📆 Lịch: ${F(p.scheduled_at)}</p>`:''}
    <div class="actions"><button class="btn sm ghost" data-action="content.edit" data-id="${p.id}">✏️ Sửa</button><button class="btn sm ghost" data-action="content.review" data-id="${p.id}">🛡️ Kiểm duyệt</button>
    ${p.status==='approved'?`<button class="btn sm primary" data-action="content.schedule" data-id="${p.id}">📅 Lên lịch</button>`:''}
    ${['approved','ready','scheduled'].includes(p.status)?`<button class="btn sm ghost" data-action="content.prepare" data-id="${p.id}">🦊 Mở để đăng</button>`:''}
    ${['approved','ready','scheduled'].includes(p.status)?`<button class="btn sm ghost" data-action="content.complete" data-id="${p.id}">✅ Đã đăng</button>`:''}
    ${['ready','scheduled'].includes(p.status)?`<button class="btn sm ghost" data-action="content.cancel" data-id="${p.id}">Hủy lịch</button>`:''}
    <button class="btn sm ghost" data-action="content.media" data-id="${p.id}">🖼️ Thêm ảnh</button>
    </div></div>`).join(''):empty('📝','Chưa có nội dung','Tạo bản nháp mới hoặc kết nối AI để viết nội dung theo Page.')}</div>
  <div class="warn">Lịch tự động chuyển bài sang trạng thái “Đến lịch”; không tự nhấn Đăng trên Facebook vì không sử dụng Meta API và không được giả định quyền tự động hóa giao diện.</div>`;
}
function renderGrowth(){
  const campaigns=V('growth_sprints');
  const active=campaigns.find(x=>x.id===S.growthDetailId)||campaigns[0];
  const actionButtons=`<button class="btn primary" data-action="growth.new">＋ Lập kế hoạch từ sản phẩm</button>`;
  const cards=campaigns.length?campaigns.map(g=>{
    const rep=g.report||{};
    const target=g.target_new_follows||0;
    const current=rep.net_new_follows;
    return `<button class="growth-sprint-option ${active?.id===g.id?'selected':''}" data-action="growth.detail" data-id="${E(g.id)}">
      <strong>${E(g.product_name)}</strong><span class="meta">${E(g.start_date)} → ${E(g.end_date)} · ${E(g.page_id?pageName(g.page_id):'Chưa gắn Page')}</span>
      <span class="meta">Mục tiêu: +${target} follow · ${current===null||current===undefined?'Chưa có KPI':('Thực tế: '+(current>=0?'+':'')+current)}</span>
      <span class="badge ${g.status==='ready'?'green':'yellow'}">${E(g.status==='ready'?'Đã có bản AI':'Khung kế hoạch / đang xử lý')}</span>
    </button>`;
  }).join(''):empty('🚀','Chưa có chiến dịch','Nhập tên và thành phần sản phẩm để CEO giao việc cho các agent.');
  let detail='';
  if(active){
    const plan=active.ai_plan?.seven_day_plan?.length===7?active.ai_plan:active.outline;
    const report=active.report||{};
    const baseline=active.baseline_followers;
    detail=`<div class="card growth-detail">
       <div class="space-between"><div><h2>🎯 ${E(active.product_name)}</h2><p class="meta">${E(active.ingredients)}</p></div><span class="badge ${active.goal_basis==='provisional_experiment'?'yellow':'blue'}">${E(active.goal_basis==='provisional_experiment'?'Mục tiêu giả định':'Mục tiêu nội bộ')}</span></div>
       <div class="growth-summary">
         <div><strong>+${active.target_new_follows}</strong><span>Follow mới mục tiêu / 7 ngày</span></div>
         <div><strong>${report.net_new_follows===null?'—':(report.net_new_follows>=0?'+':'')+report.net_new_follows}</strong><span>Follow mới thực tế (nhập thủ công)</span></div>
         <div><strong>${report.completion_pct===null?'—':report.completion_pct+'%'}</strong><span>Tiến độ đạt mục tiêu</span></div>
       </div><p class="meta">Tổng view do bạn nhập: <strong>${report.total_views||0}</strong> · Tương tác: <strong>${report.total_interactions||0}</strong>. Không phải Insights tự lấy từ Facebook.</p>
       <p class="card-sub">Đây là mục tiêu để thử nghiệm, không phải dự báo hoặc cam kết lượt follow. Chưa kết nối Meta API; KPI chỉ do bạn tự nhập.</p>
       ${baseline===null?`<div class="warn">Chưa có số người theo dõi ban đầu. Hãy nhập mốc đầu tuần để đo tiến độ.</div><button class="btn ghost" data-action="growth.baseline" data-id="${E(active.id)}">📌 Nhập số follow ban đầu</button>`:''}
       <div class="actions">${!active.page_id?`<button class="btn ghost" data-action="growth.link" data-id="${E(active.id)}">📣 Gắn Fanpage đã có</button>`:""}<button class="btn primary" data-action="growth.progress" data-id="${E(active.id)}">📊 Cập nhật follow, view trong ngày</button>
       <button class="btn ghost" data-action="growth.generate" data-id="${E(active.id)}" ${active.status==='generating'?'disabled':''}>🧠 CEO viết lại chiến lược bằng Claude</button>
       <button class="btn ghost" data-route="tasks">👥 Xem nhiệm vụ</button></div>
       ${active.ai_error?`<div class="warn">Lỗi tạo kế hoạch AI: ${E(active.ai_error)}</div>`:''}
       <div class="subtle-divider"></div><h3>🧠 Định vị nội dung</h3><p>${E(plan.positioning||'Đang xác định định vị theo dữ liệu sản phẩm.')}</p>
       <p class="card-sub">${E(plan.audience_hypothesis||plan.target_audience||'Chưa có số liệu khách hàng; Research phải nghiên cứu thêm.')}</p>
       <div class="subtle-divider"></div><h3>🎬 Kịch bản & lịch 7 ngày</h3>
       ${(plan.seven_day_plan||[]).map(d=>`<details class="growth-day" ${d.day===1?'open':''}><summary><strong>Ngày ${Number(d.day)}: ${E(d.topic)}</strong><span class="badge blue">${E(d.format||'reel')} · Mốc kiểm tra +${Math.ceil(active.target_new_follows*d.day/7)} follow</span></summary>
          <p><strong>Hook:</strong> ${E(d.hook)}</p><ol>${(d.scenes||[]).map(x=>`<li>${E(x)}</li>`).join('')}</ol><p><strong>CTA:</strong> ${E(d.cta)}</p>
          <p class="meta">${active.ai_plan?'Bản nháp Claude, vẫn cần kiểm duyệt.':'Khung kịch bản miễn phí, chưa được Claude hoàn thiện.'}</p>
        </details>`).join('')}
       <div class="subtle-divider"></div><h3>📋 Nhân viên được CEO giao việc (${active.tasks?.length||0})</h3>
       <div class="growth-agents">${(active.tasks||[]).map(t=>`<div class="growth-agent"><span>${E(agentName(t.agent_id))}</span>${badge(t.status)}<small>${E(short(t.title,92))}</small></div>`).join('')}</div>
       <div class="subtle-divider"></div><h3>📈 Dữ liệu theo ngày</h3>
       ${(active.progress||[]).length?`<div class="table-scroll"><table class="data-table"><thead><tr><th>Ngày</th><th>Follow tổng</th><th>View</th><th>Tương tác</th></tr></thead><tbody>${active.progress.map(row=>`<tr><td>${row.day}</td><td>${row.followers_total}</td><td>${row.views}</td><td>${row.interactions}</td></tr>`).join('')}</tbody></table></div>`:empty('📊','Chưa có số liệu','Sau khi đăng thủ công, hãy nhập Insights thật để CEO đối chiếu với mục tiêu.')}
       <div class="warn">Tất cả kịch bản cần kiểm duyệt nội dung, quyền sử dụng hình ảnh và tuyên bố sản phẩm trước khi xuất bản. Không dùng bot tăng tương tác hoặc tài khoản giả.</div>
     </div>`;
  }
  return `${heading('CEO · Tăng trưởng Fanpage 7 ngày','Nhập tên sản phẩm và thành phần. CEO lập lịch và kịch bản, giao nhiệm vụ 8 agent, theo dõi follow/view thật.',actionButtons)}
    <div class="grid-2 growth-layout"><div class="card"><h2>📅 Các chiến dịch đang theo dõi</h2><div class="stack">${cards}</div></div><div>${detail||empty('🧠','Chọn chiến dịch','Kế hoạch được lưu cục bộ ngay khi tạo.')}</div></div>`;
}
function growthForm(){
  modal('🚀 CEO xây dựng Page từ sản phẩm',
    '<p class="muted">Chỉ cần tên sản phẩm và thành phần. Các thông tin khác là tùy chọn giúp CEO đặt chỉ tiêu sát thực tế.</p>'+
    field('Tên sản phẩm','product_name','','text','required minlength="3" maxlength="180" placeholder="Ví dụ: Trà thảo mộc Ba Kích"')+
    field('Thành phần sản phẩm','ingredients','','textarea','rows="4" required placeholder="Mỗi thành phần cách nhau bằng dấu phẩy"')+
    pick('Fanpage đã có (không bắt buộc)','page_id',pageOptions(),'','Chưa gắn Fanpage')+
    field('Đối tượng khách hàng dự kiến','target_audience','','text','placeholder="Nếu chưa biết, CEO giao Research tìm hiểu"')+
    field('Tổng follow hiện tại','baseline_followers','','number','min="0" placeholder="Để trống nếu chưa biết"')+
    field('Follow mới 7 ngày vừa qua','previous_week_new_follows','','number','min="0" placeholder="Có số liệu thì CEO đặt mục tiêu +20%"')+
    field('Chỉ tiêu tự đặt (+follow/tuần)','goal_override','','number','min="1" placeholder="Để CEO tự đề xuất nếu chưa có"')+
    '<div class="office-note">Nếu chưa có số liệu: mặc định đặt mục tiêu <strong>thử nghiệm +25 follow/7 ngày</strong>, không phải dự báo. Bản AI chỉ chạy nếu đã cài Claude key và còn ngân sách.</div>',
    'CEO lập chiến dịch & giao việc',async f=>{
      const parseOptional=n=>f[n]===''||f[n]===undefined?null:Number(f[n]);
      const r=await api('/api/growth/sprints','POST',{
        product_name:f.product_name,ingredients:f.ingredients,page_id:f.page_id||null,
        target_audience:f.target_audience||'',baseline_followers:parseOptional('baseline_followers'),
        previous_week_new_follows:parseOptional('previous_week_new_follows'),goal_override:parseOptional('goal_override'),auto_generate:true});
      S.growthDetailId=r.id;toast('CEO đã lập chiến dịch, tạo 14 nhiệm vụ và 7 khung kịch bản.');
    });
}
function renderTasks(){
  const tasks=V('tasks').filter(t=>S.taskFilter==='all'||t.status===S.taskFilter);
  return `${heading('Nhật ký nhiệm vụ AI','Mỗi nhiệm vụ có nhân viên phụ trách, trạng thái, kết quả và nhật ký.',`<button class="btn primary" data-action="tasks.run-queued">▶ Chạy hàng đợi</button>`)}
    <div class="toolbar" style="margin-bottom:15px">${['all','queued','running','done','failed'].map(st=>`<button class="btn sm ${S.taskFilter===st?'primary':'ghost'}" data-action="task.filter" data-id="${st}">${{all:'Tất cả',queued:'Đang chờ',running:'Đang làm',done:'Đã xong',failed:'Lỗi'}[st]}</button>`).join('')}</div>
    <div class="stack">${tasks.length?tasks.map(t=>`<div class="item-card"><div class="space-between"><div><h3>${E(t.title)}</h3><div class="meta">${E(agentName(t.agent_id))} · ${t.page_id?E(pageName(t.page_id))+' · ':''}${F(t.created)}</div></div>${badge(t.status)}</div>
    <p>${E(short(t.instructions,280))}</p>${t.result?`<details><summary class="linkish">Xem kết quả thực hiện</summary><p class="editor-preview">${E(t.result)}</p></details>`:''}${t.error?`<div class="warn">${E(t.error)}</div>`:''}
    <div class="actions">${['queued','failed'].includes(t.status)?`<button class="btn sm primary" data-action="task.run" data-id="${t.id}">▶ Thực hiện bằng AI</button>`:''}<span class="code-pill">${E(t.id)}</span></div></div>`).join(''):empty('📋','Không có nhiệm vụ','CEO sẽ tạo nhiệm vụ khi nhận chỉ đạo.')}</div>`;
}
function renderInsights(){
  const rows=V('metrics'), pages=V('pages');
  const dayMap=new Map();for(const r of rows){const v=dayMap.get(r.date)||0;dayMap.set(r.date,v+Number(r.likes)+Number(r.comments)+Number(r.shares));}
  const chart=[...dayMap.entries()].sort((a,b)=>a[0].localeCompare(b[0])).slice(-14);const max=Math.max(1,...chart.map(c=>c[1]));
  const bars=chart.map(([day,num])=>`<div class="metric-bar" style="--h:${Math.max(2,num/max*95)}%" title="${E(day)}: ${num}"><span>${E(day.slice(5))}</span></div>`).join('');
  return `${heading('Báo cáo & Bộ nhớ AI','Số liệu do bạn nhập, không thu thập hoặc giả lập số liệu từ Facebook.',`<button class="btn primary" data-action="metrics.import">＋ Nhập KPI</button>`)}
    <div class="grid-2"><div class="card"><div class="space-between"><h2>📈 Tương tác theo ngày</h2><span class="badge">Dữ liệu nhập thủ công</span></div><div class="subtle-divider"></div>${chart.length?`<div class="metric-bars">${bars}</div><div class="card-sub" style="margin-top:28px">Tổng lượt thích + bình luận + chia sẻ (không bao gồm lượt xem).</div>`:empty('📊','Chưa có số liệu','Nhập KPI theo Page để xem biểu đồ.')}</div>
    <div class="card"><h2>🧠 Học từ dữ liệu thực tế</h2><p class="muted">Khi có ít nhất 5 ngày KPI cho một Page, hệ thống tính toán số liệu quan sát được và lưu vào trí nhớ. Không tự suy đoán quan hệ nhân quả.</p>${pick('Chọn Fanpage','learnpage',pageOptions())}<button class="btn primary" data-action="metrics.learn">Tổng hợp thành bài học</button><div class="warn">KPI nhập thủ công chưa được đối chiếu với Facebook. Nên nhập từ báo cáo hợp lệ do doanh nghiệp sở hữu.</div></div></div>
    <div class="card" style="margin-top:16px"><h2>📋 Dữ liệu KPI gần nhất</h2>${rows.length?`<div class="table-scroll"><table class="data-table"><thead><tr><th>Ngày</th><th>Page</th><th>Lượt xem</th><th>Thích</th><th>Bình luận</th><th>Chia sẻ</th></tr></thead><tbody>${rows.slice(0,45).map(r=>`<tr><td>${E(r.date)}</td><td>${E(r.page_name)}</td><td>${r.views}</td><td>${r.likes}</td><td>${r.comments}</td><td>${r.shares}</td></tr>`).join('')}</tbody></table></div>`:empty('📭','Chưa có KPI')}</div>`;
}
function renderBrains(){
  const b=S.data?.brain_overview||{};
  const cost=b.cost||{};
  const agents=b.agents||[];
  return `${heading('Bộ não 9 nhân viên AI','Mỗi agent học từ sự kiện nội bộ, lưu bộ nhớ độc lập và chỉ gọi Claude khi thật sự cần.',`<button class="btn primary" data-action="brain.learn-now">↻ Xử lý bài học chờ</button>`)}
  <div class="stat-grid">${stat('🧠','Bộ não',agents.length,'Không dùng chung lịch sử','#9782ff')}${stat('📚','Kinh nghiệm đã lưu',agents.reduce((n,a)=>n+Number(a.memory_count||0),0),'Lưu trên máy chủ của bạn','#64e6b4')}${stat('⏳','Bài học chờ xử lý',agents.reduce((n,a)=>n+Number(a.pending_learning||0),0),'Xử lý nội bộ, không tốn token','#ffc17c')}${stat('💵','Claude hôm nay','$'+Number(cost.today_usd||0).toFixed(4),'Giới hạn $'+Number(cost.daily_limit_usd||0).toFixed(2)+'/ngày','#79c4ff')}</div>
  <div class="card" style="margin-top:17px"><div class="space-between"><h2>🧠 Bộ nhớ riêng từng agent</h2><span class="badge green">Học theo sự kiện</span></div><p class="muted">Dịch vụ học chạy khi máy chủ phần mềm hoạt động. Agent ghi chú kết quả làm việc nhưng chỉ dữ liệu được xác minh mới được đánh dấu xác thực. Không gọi Claude liên tục khi không có nhiệm vụ.</p><div class="table-scroll"><table class="data-table"><thead><tr><th>Nhân viên</th><th>Ghi nhớ</th><th>Đang chờ</th><th>Đã xử lý</th><th>Claude hôm nay</th><th>Chi tiết</th></tr></thead><tbody>
    ${agents.map(a=>`<tr><td><strong>${E(a.name)}</strong></td><td>${Number(a.memory_count||0)}</td><td>${Number(a.pending_learning||0)}</td><td>${Number(a.processed_events||0)}</td><td>$${Number(cost.agents?.[a.id]||0).toFixed(4)}</td><td><button class="btn sm ghost" data-action="brain.memory" data-id="${E(a.id)}">Xem trí nhớ</button></td></tr>`).join('')}</tbody></table></div></div>
  <div class="card" style="margin-top:17px"><div class="space-between"><h2>🤖 Model đã tự chọn gần đây</h2><span class="badge blue">Tự động</span></div>
  <p class="muted">Lịch sử gọi Claude thực tế (không bao gồm câu trả lời lấy từ bộ nhớ cache). Model được chọn theo độ khó, không cấu hình thủ công.</p>
  ${(b.routing?.recent||[]).length?`<div class="table-scroll"><table class="data-table"><thead><tr><th>Nhân viên</th><th>Model</th><th>Nguyên nhân</th><th>Chi phí ước tính</th><th>Trạng thái</th></tr></thead><tbody>
  ${(b.routing?.recent||[]).map(x=>`<tr><td>${E(agentName(x.agent_id))}</td><td><code>${E(x.model)}</code></td><td>${E(({routine_low_cost:'Việc thường',complex_explicit:'Nhiệm vụ phức tạp',complex_keywords:'Nhiệm vụ có rủi ro',long_complex_plan:'Kế hoạch dài'})[x.route_reason]||x.route_reason||'Từ bản cũ')}</td><td>$${Number(x.cost_usd||0).toFixed(5)}</td><td>${E(x.status)}</td></tr>`).join('')}</tbody></table></div>`:empty('🤖','Chưa có lời gọi Claude','Sau khi nhân viên xử lý nhiệm vụ, bảng sẽ hiển thị model thực sự được sử dụng.')}</div>
  <div class="grid-2" style="margin-top:17px"><div class="card"><h2>⚙️ Tối ưu chi phí Claude</h2><p>① Ưu tiên bộ nhớ và quy tắc cục bộ. ② Dùng model Haiku cho việc thường. ③ Chỉ nâng lên Sonnet khi khó, có yêu cầu hoặc khi model nhỏ không giải quyết được. ④ Tái dùng câu trả lời trùng khớp trong 6 giờ. ⑤ Khóa ngân sách mỗi agent và toàn công ty.</p><button class="btn ghost" data-route="settings">Đi đến cài đặt ngân sách</button></div><div class="card"><h2>🛡️ Điều kiện tự học</h2><p>Học và ghi nhớ 24/24 nghĩa là xử lý các sự kiện khi phần mềm đang chạy, không phải tạo yêu cầu AI liên tục hay tự suy đoán dữ liệu Facebook. Khi tắt máy, hoạt động dừng; sự kiện còn trong database sẽ được xử lý khi mở lại.</p><p class="muted">Dữ liệu mỗi agent lưu riêng. CEO chỉ giao việc và đọc báo cáo, không mặc định xem mọi thông tin nhạy cảm.</p></div></div>`;
}
function renderAcademy(){
  const a=S.data.academy||{},c=a.counts||{},u=a.usage||{};
  const limit=Number(a.daily_token_limit||10000000),used=Number(u.used_quota_today||0),pct=Math.min(100,Math.max(0,used/Math.max(limit,1)*100));
  const trainingCount=Number(c.jobs_done||0),totalJobs=Number(c.jobs||0);
  return `${heading('Học viện AI · 10 triệu quota/ngày','9 nhân viên học từ tài liệu có nguồn, tóm tắt chung một lần rồi ghi nhớ theo chuyên môn. Không tự quét Facebook.',`<button class="btn ghost" data-action="academy.toggle">${a.enabled?"⏸ Tạm dừng học tự động":"▶ Bật học tự động"}</button><button class="btn primary" data-action="academy.step">▶ Học một bước ngay</button>`)}
    <div class="stat-grid">${stat('📚','Nguồn đã nạp',c.sources||0,'Tài liệu có quyền sử dụng','#9782ff')}${stat('🧩','Đoạn kiến thức',c.chunks||0,`${c.digests_done||0} đã tóm tắt`,'#64e6b4')}${stat('🎓','Bài huấn luyện',trainingCount+'/'+totalJobs,`${c.jobs_queued||0} đang chờ`,'#ffc17c')}${stat('🪙','Quota MiraiAPI hôm nay',Number(used).toLocaleString('vi-VN'),`Hạn mức: ${limit.toLocaleString('vi-VN')}`,'#79c4ff')}</div>
    <div class="card" style="margin-top:18px"><div class="space-between"><h2>📈 Hạn mức quota MiraiAPI</h2><span class="badge ${a.enabled?'green':'yellow'}">${a.enabled?'Đang bật học tự động':'Học tự động đang tắt'}</span></div>
       <p class="muted">Hệ thống ước tính quota = (input + 5 × output) × hệ số model. Yêu cầu đang chạy giữ khoản dự trù để tránh vượt hạn mức.</p>
       <div class="academy-progress"><div class="academy-progress-fill" style="width:${pct}%"></div></div>
       <div class="space-between"><strong>${used.toLocaleString('vi-VN')} / ${limit.toLocaleString('vi-VN')} quota</strong><span class="muted">${pct.toFixed(2)}%</span></div>
       <p class="card-sub">Model Học viện: <strong>${E(u.model||'chưa cấu hình')}</strong> · hệ số quota: <strong>${Number(u.model_ratio||1)}</strong>. Học viện không trừ ngân sách Claude trực tiếp; quota thực tế do MiraiAPI quyết định.</p>
       <div class="warn">Đây là quota <strong>ước tính nội bộ</strong>, không phải số dư đã xác minh. Kiểm tra quota thực tại <a href="https://miraiapi.com/usage/" target="_blank" rel="noopener noreferrer">miraiapi.com/usage</a>. Mỗi model có hệ số khác nhau; nhập đúng hệ số từ bảng Model &amp; giá. ${u.configured?'':'<strong>Chưa có MiraiAPI Key.</strong>'}</div>
    </div>
    <div class="grid-2" style="margin-top:17px"><div class="card"><h2>📥 Nạp nguồn đào tạo</h2><p class="muted">Dán tài liệu bạn sở hữu hoặc được phép sử dụng. Bản này nhận văn bản thuần tối đa 300.000 ký tự/lần; không tự thu thập dữ liệu Facebook.</p>
      <form id="academyForm">
        ${field('Tên tài liệu','title','','text','minlength="3" maxlength="180" placeholder="Ví dụ: Quy trình chăm sóc Fanpage" required')}
        ${field('Nguồn / liên kết gốc (tùy chọn)','source_ref','','text','maxlength="350" placeholder="https://... hoặc Sổ tay nội bộ"')}
        <div class="form-field"><label>Nội dung tài liệu</label><textarea class="textarea" name="content" rows="9" minlength="160" maxlength="300000" required placeholder="Dán nội dung tài liệu vào đây... Không dán API key, mật khẩu hoặc cookie."></textarea></div>
        <label class="brain-option"><input type="checkbox" name="owner_has_rights" required> Tôi có quyền sử dụng tài liệu này để đào tạo AI</label>
        <button class="btn primary block" type="submit">＋ Nạp tài liệu & tạo nhiệm vụ đào tạo</button>
      </form></div>
    <div class="card"><h2>👥 Tiến độ đào tạo theo agent</h2><p class="muted">Một đoạn tài liệu được tóm tắt chung, sau đó mỗi agent rút bài học phù hợp với chức năng. Bộ nhớ từng người vẫn được cách ly.</p>
    <div class="table-scroll"><table class="data-table"><thead><tr><th>Nhân viên</th><th>Đã học</th><th>Chờ học</th></tr></thead><tbody>
    ${(a.agents||[]).map(x=>`<tr><td>${E(x.name)}</td><td>${Number(x.done||0)}</td><td>${Number(x.queued||0)}</td></tr>`).join('')}</tbody></table></div>
    <div class="subtle-divider"></div><h2>📁 Tài liệu gần đây</h2>
    ${(a.sources||[]).length?(a.sources||[]).map(x=>`<div class="activity-item"><strong>${E(x.title)}</strong><p>${Number(x.chunks)} đoạn · ${E(x.source_ref||'Tài liệu nội bộ')}</p><small>${F(x.created)}</small></div>`).join(''):empty('📭','Chưa có nguồn học','Nạp dữ liệu để khởi động học viện.')}
    </div></div>`;
}

function renderSettings(){
  const cfg=S.data.settings;
  const brain=S.data.brain_overview||{};
  const routing=brain.routing||{};
  return `${heading('Cài đặt phần mềm','CEO dùng Claude trực tiếp; Học viện 10M dùng MiraiAPI độc lập.',`<span class="badge green">🔒 Localhost only</span>`)}
    <div class="columns"><div class="card"><h2>🔵 Kết nối Claude AI</h2><p class="card-sub">Chỉ cần một Claude API key cho 9 agent. Lưu key trước khi bấm Kiểm tra. Key được mã hóa trong dữ liệu cục bộ; không hiển thị lại sau khi lưu.</p>
    <form id="settingsForm" style="margin-top:17px">
    ${field('Claude API key'+(cfg.claude_configured?' · Đã lưu':''),'claude_key','','password','placeholder="Để trống nếu muốn giữ API key đã lưu"')}
    <div class="office-note">🧠 <strong>Tự chọn model:</strong> Việc thông thường → <code>${E(routing.routine_model||'claude-haiku-5-5')}</code> (tiết kiệm). Nhiệm vụ khó/rủi ro hoặc cần nâng cấp → <code>${E(routing.complex_model||'claude-sonnet-5-5')}</code>. Không cần chọn model thủ công, không mặc định gọi model đắt nhất.</div>
    <div class="actions"><button class="btn ghost" type="button" data-action="claude.check">🔎 Kiểm tra Claude đã lưu</button></div>
    <div class="subtle-divider"></div><h2>💵 Ngân sách và vận hành</h2>
    ${field('Hạn mức Claude toàn công ty (USD/ngày)','claude_daily_budget_usd',cfg.claude_daily_budget_usd??'1.00','number','min="0" max="1000" step="0.01" required')}
    ${field('Hạn mức Claude mỗi agent (USD/ngày)','claude_agent_daily_budget_usd',cfg.claude_agent_daily_budget_usd??'0.25','number','min="0" max="1000" step="0.01" required')}
    ${field('Giới hạn lượt gọi Claude/ngày','daily_llm_call_limit',cfg.daily_llm_call_limit??'200','number','min="1" max="10000" required')}
    <div class="subtle-divider"></div><h2>🎓 MiraiAPI – chỉ dùng cho Học viện 10M</h2>
    <p class="muted">Base URL cố định: <code>https://api.miraiapi.com/v1</code> (không phải mirapi.ai). Key được lưu mã hóa riêng với Claude. Nguồn tài liệu của học viện sẽ được gửi đến MiraiAPI sau khi bạn bật tự học.</p>
    ${field('MiraiAPI Key'+(cfg.mirai_configured?' · Đã lưu':''),'mirai_key','','password','placeholder="Để trống để giữ key đã lưu" autocomplete="off"')}
    ${field('Model MiraiAPI cho Học viện','academy_mirai_model',cfg.academy_mirai_model||'claude-opus-4.8','text','placeholder="Dùng tên model được phép của key" required')}
    ${field('Hệ số quota của model (từ bảng giá MiraiAPI)','academy_mirai_ratio',cfg.academy_mirai_ratio||'1','number','min="0.01" max="100" step="0.01" required')}
    <div class="actions"><button class="btn ghost" type="button" data-action="mirai.check">🔎 Xem danh sách model (không tốn token suy luận)</button>
    <button class="btn primary" type="button" data-action="mirai.test-call">⚡ Test gọi API Mirai (tốn ít quota)</button></div>
    <div class="office-note" id="mirai-test-result" role="status" aria-live="polite">Nhập API Key, model và hệ số quota rồi bấm Test. Cấu hình MiraiAPI sẽ được lưu trước khi kiểm tra. Kết quả hiển thị ở đây.</div>
    <p class="muted">Quota được tính (input + output × 5) × hệ số model. Hệ số mặc định 1 chỉ là giá trị mẫu; hãy xác nhận trên <a href="https://miraiapi.com/usage/#models" target="_blank" rel="noopener noreferrer">MiraiAPI Model & giá</a> trước khi bật học.</p>
    ${field('Hạn mức quota MiraiAPI/ngày','academy_daily_token_limit',cfg.academy_daily_token_limit??'10000000','number','min="10000" max="100000000" step="10000" required')}
    ${field('Khoảng cách giữa các bước học (giây)','academy_interval_seconds',cfg.academy_interval_seconds??'35','number','min="10" max="3600" required')}
    <label class="brain-option"><input type="checkbox" name="academy_enabled" ${cfg.academy_enabled==='1'?'checked':''}> Bật Học viện AI bằng MiraiAPI khi server đang chạy (có thể tiêu quota MiraiAPI)</label>
    <label class="brain-option"><input type="checkbox" name="claude_cache_enabled" ${cfg.claude_cache_enabled==='1'?'checked':''}> Dùng lại kết quả giống hệt trong 6 giờ & prompt caching</label>
    <label class="brain-option"><input type="checkbox" name="brain_learning_enabled" ${cfg.brain_learning_enabled==='1'?'checked':''}> Học từ sự kiện nội bộ khi chương trình đang chạy (không tốn Claude khi rảnh)</label>
    <label class="brain-option"><input type="checkbox" name="auto_run_agents" ${cfg.auto_run_agents==='1'?'checked':''}> Tự chạy hàng đợi agent trong giới hạn ngân sách</label>
    <button class="btn primary block">💾 Lưu cài đặt</button></form></div>
    <div class="stack"><div class="card"><h2>🦊 Firefox</h2><p class="muted">Trạng thái trên máy chạy server: ${S.data.firefox_available?'<span class="badge green">Đã tìm thấy</span>':'<span class="badge red">Chưa tìm thấy</span>'}</p>
    ${S.data.firefox_available?'':firefoxInstallerNotice()}
    <form id="firefoxForm">${field('Đường dẫn Firefox (tùy chọn)','firefox_path',cfg.firefox_path,'text','placeholder="C:\\Program Files\\Mozilla Firefox\\firefox.exe"')}<button class="btn ghost">Lưu đường dẫn</button></form>
    <div class="office-note">Chạy phần mềm trên chính máy Windows có Firefox. Profile được lưu dưới %LOCALAPPDATA%\\AI-Fanpage-Company\\profiles.</div></div>
    <div class="card"><h2>🔄 Cập nhật phần mềm</h2><p>Khi phần mềm được mở bằng <code>start_windows.bat</code>, bộ giám sát sẽ phát hiện mã nguồn mới sau <code>git pull</code>, đợi nhân viên AI hoàn tất công việc rồi tự khởi động lại backend. Giao diện sẽ tự tải lại khi máy chủ mới sẵn sàng.</p><p class="muted">Bạn có thể chạy <code>update_windows.bat</code> trong thư mục phần mềm để tải bản mới an toàn (chỉ fast-forward). Nếu đang chạy bản cũ chưa có supervisor, cần khởi động lại thủ công một lần để kích hoạt.</p></div>
    <div class="card"><h2>🔐 Bảo mật</h2><p>Backend chỉ nghe <code>127.0.0.1:8765</code>. Không mở cổng công khai. Tài khoản Facebook đăng nhập trực tiếp trong Firefox, không lưu mật khẩu vào ứng dụng.</p><p class="muted">Bảo vệ toàn bộ thư mục dữ liệu của ứng dụng và khóa mã hóa bằng tài khoản Windows hoặc mã hóa ổ đĩa.</p></div>
    <div class="card"><h2>📌 Phạm vi V1</h2><p>✅ CEO AI thật (khi có key), phân công và nhật ký.</p><p>✅ Profile Firefox cố định, đăng nhập thủ công.</p><p>✅ Nội dung, kiểm duyệt, lịch, bộ nhớ, KPI.</p><p>⚠️ Không tự đăng Facebook bằng UI bot; không tự đọc quyền/Insights.</p></div></div></div>`;
}
function render(){
  if(!S.data)return;
  window.OfficeLive?.unmount();
  nav();const dict={office:renderOffice,ceo:renderCEO,pages:renderPages,accounts:renderAccounts,content:renderContent,tasks:renderTasks,insights:renderInsights,brains:renderBrains,academy:renderAcademy,growth:renderGrowth,settings:renderSettings};
  document.getElementById('view').innerHTML=(dict[S.route]||renderOffice)();
  if(S.route==='office'){
    const scene=window.OfficeLive?.mount(document.getElementById('office-live-stage'),S.data,id=>action('agent.details',id).catch(err=>toast(err.message,true)));
    const toggle=document.getElementById('office-toggle');if(toggle&&scene?.paused)toggle.textContent='▶ Tiếp tục';
  }
  if(S.route==='ceo'){const el=document.getElementById('chatMessages');if(el)el.scrollTop=el.scrollHeight;}
}
async function reload(){S.data=await api('/api/bootstrap');render();}
function navigate(route){if(!ROUTES.some(r=>r[0]===route))return;S.route=route;location.hash=route;render();window.scrollTo({top:0,behavior:'smooth'});}
function pageForm(page=null){
  modal(page?'Sửa hồ sơ Fanpage':'Thêm Fanpage',
    field('Tên Fanpage','name',page?.name||'','text','required minlength="2"')+field('Đường dẫn Facebook','url',page?.url||'','url','placeholder="https://www.facebook.com/your-page" required')+
    field('Ngành hàng','category',page?.category||'')+field('Giọng văn, định vị','tone',page?.tone||'','textarea')+
    field('Thông tin sản phẩm/kiến thức đã xác thực','facts',page?.facts||'','textarea','rows="6" placeholder="Thông số, thành phần, lưu ý, giá..."')+
    pick('Tài khoản Firefox quản lý','account_id',accountOptions(),page?.account_id||'','Chưa liên kết')+
    '<div class="office-note">Fanpage phải thuộc quyền quản lý thực tế của tài khoản đã chọn. URL không chứng minh quyền sở hữu.</div>',
    page?'Lưu thay đổi':'Thêm Fanpage',
    async f=>api('/api/pages'+(page?'/'+page.id:''),page?'PUT':'POST',{...f,account_id:f.account_id||null}));
}
function contentForm(post=null){
  modal(post?'Sửa nội dung':'Tạo bản nháp',
    post?`<p class="card-sub">📣 ${E(pageName(post.page_id))}</p>`:pick('Fanpage','page_id',pageOptions())+
    field('Chủ đề','topic',post?.topic||'','text','required')+
    field('Nội dung bài viết','body',post?.body||'','textarea','rows="12" required')+
    '<p class="hint">Nội dung phải dựa trên dữ liệu đã được kiểm tra, không cam kết công dụng không có bằng chứng.</p>',
    post?'Cập nhật bản nháp':'Tạo bản nháp',async f=>{
      if(post)return api('/api/contents/'+post.id,'PUT',{topic:f.topic,body:f.body});
      return api('/api/contents','POST',f);
    });
}
function generateForm(){
  modal('✦ AI tạo bài Facebook',pick('Fanpage có dữ liệu xác thực','page_id',pageOptions())+field('Chủ đề cần viết','topic','','text','required')+
    '<div class="office-note">LLM tạo nội dung từ thông tin bạn đã cung cấp. Bài phải được kiểm duyệt trước khi lập lịch.</div>',
    'Yêu cầu AI viết bài',async f=>{await api('/api/contents/generate','POST',f);toast('AI đã tạo bản nháp thực tế.')});
}
function campaignForm(){
  const categories=[...new Set(V('pages').map(p=>p.category).filter(Boolean))].map(cat=>({value:cat,label:cat}));
  modal('✦ CEO tạo chiến dịch theo lô',
    field('Chủ đề nội dung','topic','','text','required minlength="5" placeholder="Ví dụ: Giới thiệu sản phẩm và cách sử dụng an toàn"')+
    pick('Nhóm Fanpage','category',categories,'','Tất cả các Page đã có dữ kiện')+
    field('Số Page tối đa','max_pages','100','number','min="1" max="100" required')+
    '<div class="office-note">CEO sẽ tạo 1 nhiệm vụ viết bài riêng cho mỗi Page đã có dữ kiện sản phẩm. Không tự đăng Facebook. Có thể bật tự chạy agent trong Cài đặt, áp dụng hạn mức API/ngày.</div>',
    'Giao nhiệm vụ cho các Page',async f=>{
      const r=await api('/api/ceo/campaigns','POST',{topic:f.topic,category:f.category,max_pages:Number(f.max_pages)});
      toast('CEO đã tạo '+r.queued+' nhiệm vụ. Chưa đăng bài nào.');
    });
}
function accountForm(){
  if(!S.data?.firefox_available){firefoxInstallerDialog();return;}
  modal('🦊 Thêm tài khoản Facebook',field('Tên dễ nhận biết (có thể bỏ trống)','label','','text','placeholder="Facebook Marketing 01"')+
    '<div class="ok-note">Hệ thống tạo profile riêng và tự mở Firefox để bạn đăng nhập trực tiếp. Không lưu mật khẩu, không cài extension.</div>',
    'Tạo và mở Firefox',async f=>{
      const data=await api('/api/accounts','POST',{label:f.label,auto_open:true});
      if(data.warning)toast('Đã tạo profile nhưng chưa mở Firefox: '+data.warning,true);
      else toast('Đã tạo profile '+data.account.id+' và gửi lệnh mở Firefox.');
    });
}
function metricImportForm(){
  modal('📊 Nhập KPI thủ công',`<p class="muted">Dán CSV có tiêu đề: <code>page_id,date,views,likes,comments,shares</code>. Mỗi dòng tương ứng một ngày của Page.</p>
    <div class="form-field"><label>CSV</label><textarea name="csv" class="textarea" rows="9" required placeholder="page_id,date,views,likes,comments,shares\nP...,2026-11-06,100,10,2,1"></textarea></div>
    <div class="office-note">Bạn có thể lấy Page ID bằng cách mở hồ sơ Fanpage, xem trong danh sách nội bộ. Dữ liệu được đánh dấu do người dùng nhập.</div>`,
    'Nhập số liệu',async f=>{
      const lines=f.csv.trim().split(/\r?\n/).map(s=>s.trim()).filter(Boolean);if(lines.length<2)throw new Error('Cần ít nhất một dòng dữ liệu.');
      const keys=lines[0].split(',').map(x=>x.trim().toLowerCase());const required=['page_id','date','views','likes','comments','shares'];
      if(required.some(x=>!keys.includes(x)))throw new Error('CSV thiếu cột bắt buộc: '+required.join(','));
      const rows=lines.slice(1).map(row=>{const vals=row.split(',');const o={};keys.forEach((key,i)=>o[key]=vals[i]?.trim());required.slice(2).forEach(k=>o[k]=Number(o[k]||0));return o;});
      const result=await api('/api/metrics/import','POST',{rows});toast('Đã nhập '+result.imported+' dòng KPI.');
    });
}
function memoryModal(pageId){
  api('/api/pages/'+encodeURIComponent(pageId)+'/memory').then(data=>{
    modal('🧠 Bộ nhớ · '+pageName(pageId),
      `<div style="max-height:270px;overflow:auto">${data.length?data.map(m=>`<div class="activity-item"><strong>${E(m.source)}</strong><p>${E(m.note)}</p><time>${F(m.created)}</time></div>`).join(''):empty('🧠','Chưa có bộ nhớ')}</div><div class="subtle-divider"></div>`+
      field('Thêm thông tin xác thực','note','','textarea','rows="4" required minlength="5"'),
      'Ghi nhớ',async f=>{await api('/api/pages/'+pageId+'/memory','POST',{note:f.note});toast('Đã thêm bộ nhớ của Page.');}
    );
  }).catch(e=>toast(e.message,true));
}
function scheduleModal(id){
  modal('📅 Đặt lịch nội dung',field('Thời gian (giờ trên máy của bạn)','scheduled_at','','datetime-local','required'),
    'Lên lịch',async f=>{await api('/api/contents/'+id+'/schedule','POST',f);toast('Đã lập lịch. Khi đến giờ bài sẽ chuyển sang trạng thái chờ đăng.');});
}
function publishModal(id){
  const post=V('contents').find(c=>c.id===id);
  modal('✅ Xác nhận đã đăng thủ công',`<p>Bạn phải thật sự đăng bài trên Facebook trước khi xác nhận.</p><div class="editor-preview" style="max-height:140px">${E(post?.body||'')}</div>`+
    field('Đường dẫn bài đã đăng (không bắt buộc)','post_url','','url','placeholder="https://www.facebook.com/..."')+
    '<label style="display:flex;align-items:center;gap:9px"><input type="checkbox" name="confirmed" value="yes" required> Tôi xác nhận đã tự đăng bài trên Facebook.</label>',
    'Lưu xác nhận',async f=>{await api('/api/contents/'+id+'/complete','POST',{confirmed:f.confirmed==='yes',post_url:f.post_url||''});toast('Đã lưu xác nhận của người dùng, chưa xác thực độc lập từ Meta.');});
}
async function action(name,id,el){
  switch(name){
    case 'refresh':await reload();toast('Đã cập nhật trạng thái.');break;
    case 'office.toggle':{const paused=window.OfficeLive?.toggle();if(el)el.textContent=paused?'▶ Tiếp tục':'⏸ Tạm dừng';break;}
    case 'office.speed':{const speed=window.OfficeLive?.speed();if(el)el.textContent='⚡ '+(speed||1)+'x';break;}
    case 'office.zoom-in':window.OfficeLive?.current?.zoomAt(1.16);break;
    case 'office.zoom-out':window.OfficeLive?.current?.zoomAt(.86);break;
    case 'office.reset':window.OfficeLive?.reset();break;
    case 'modal.close':closeModal();break;
    case 'account.add':accountForm();break;
    case 'firefox.install':firefoxInstallerDialog();break;
    case 'firefox.recheck':{const inst=await api('/api/firefox/installer');S.data.firefox_installer=inst;S.data.firefox_available=inst.installed;render();toast(inst.installed?'Đã tìm thấy Firefox.':'Chưa tìm thấy Firefox, hãy hoàn tất cài đặt.',!inst.installed);break;}
    case 'ceo.campaign':campaignForm();break;
    case 'growth.new':growthForm();break;
    case 'growth.detail':S.growthDetailId=id;render();break;
    case 'growth.generate':{const g=await api('/api/growth/sprints/'+encodeURIComponent(id)+'/generate','POST');toast(g.status==='submitted'?'Đã gửi yêu cầu Claude cho CEO.':'CEO đang chuẩn bị kịch bản.');setTimeout(reload,1400);break;}
    case 'growth.link':{modal('Liên kết Fanpage với chiến dịch',pick('Fanpage thuộc công ty','page_id',pageOptions())+'<div class="office-note">Liên kết này chỉ cập nhật dữ liệu nội bộ; không chứng minh quyền quản trị Facebook.</div>', 'Liên kết',async f=>{if(!f.page_id)throw new Error('Hãy chọn Fanpage.');await api('/api/growth/sprints/'+encodeURIComponent(id)+'/page','POST',{page_id:f.page_id});});break;}
    case 'growth.baseline':{modal('Mốc follow đầu tuần',field('Tổng người theo dõi ban đầu','baseline_followers','','number','min="0" required'), 'Lưu mốc',async f=>api('/api/growth/sprints/'+encodeURIComponent(id)+'/baseline','POST',{baseline_followers:Number(f.baseline_followers)}));break;}
    case 'growth.progress':{modal('Nhập KPI thực tế cho chiến dịch',field('Ngày thứ mấy (1–7)','day','1','number','min="1" max="7" required')+field('Tổng người theo dõi hiện tại','followers_total','','number','min="0" required')+field('Tổng view trong ngày','views','0','number','min="0" required')+field('Lượt tương tác trong ngày','interactions','0','number','min="0" required')+field('Ghi chú tình hình','notes','','textarea','rows="2"')+'<div class="office-note">KPI do bạn nhập thủ công. Nếu chưa có mốc follower ban đầu, tiến độ chỉ hiển thị sau khi bạn khai báo mốc.</div>', 'Lưu KPI',async f=>api('/api/growth/sprints/'+encodeURIComponent(id)+'/progress','POST',{day:Number(f.day),followers_total:Number(f.followers_total),views:Number(f.views),interactions:Number(f.interactions),notes:f.notes||''}));break;}

    case 'account.open':await api('/api/accounts/'+id+'/open','POST');await reload();toast('Đã gửi lệnh mở profile Firefox.');break;
    case 'account.reload':await api('/api/accounts/'+id+'/reload','POST');await reload();toast('Firefox đã mở để bạn kiểm tra và xác nhận phiên.');break;
    case 'account.close':await api('/api/accounts/'+id+'/close','POST');await reload();toast('Đã gửi lệnh đóng profile.');break;
    case 'account.confirm':{
      const a=V('accounts').find(p=>p.id===id);
      modal('Xác nhận đăng nhập thủ công',field('Tên tài khoản Facebook','name',a?.label||'','text','required')+
      '<div class="warn">Chỉ xác nhận khi bạn đã nhìn thấy tài khoản đăng nhập thành công trong Firefox. Đây không phải kiểm tra tự động.</div>',
      'Tôi đã kiểm tra',async f=>api('/api/accounts/'+id+'/confirm','POST',{name:f.name}));break;
    }
    case 'account.delete':if(confirm('Xóa vĩnh viễn Firefox Profile '+id+'? Dữ liệu phiên đăng nhập sẽ mất.')){await api('/api/accounts/'+id,'DELETE');await reload();toast('Đã xóa profile.')}break;
    case 'page.add':pageForm();break;
    case 'page.edit':pageForm(V('pages').find(p=>p.id===id));break;
    case 'page.memory':memoryModal(id);break;
    case 'page.delete':if(confirm('Xóa Fanpage và tất cả nội dung/KPI/bộ nhớ trong phần mềm?')){await api('/api/pages/'+id,'DELETE');await reload();}break;
    case 'content.add':contentForm();break;
    case 'content.edit':contentForm(V('contents').find(p=>p.id===id));break;
    case 'content.generate':if(!V('pages').length)toast('Cần tạo Fanpage trước.',true);else generateForm();break;
    case 'content.review':{const r=await api('/api/contents/'+id+'/review','POST');toast(r.status==='approved'?'Nội dung đạt quy tắc nội bộ cơ bản.':'Cần chỉnh sửa: '+r.issues.join(' | '),r.status!=='approved');await reload();break;}
    case 'content.schedule':scheduleModal(id);break;
    case 'content.prepare':{const r=await api('/api/contents/'+id+'/prepare','POST');await reload();
      modal('🦊 Firefox đã mở để đăng',`<p class="muted">Đã mở Page trong profile Firefox được liên kết. Phần mềm CHƯA đăng nội dung.</p><div class="editor-preview" style="max-height:220px">${E(r.body)}</div><div class="ok-note">Sử dụng nút Sao chép, dán vào trình soạn Facebook, tự đăng và quay lại xác nhận kết quả.</div>`, '',null);
      const m=document.querySelector('.modal-actions');m.innerHTML=`<button class="btn primary" id="copyPost">📋 Sao chép nội dung</button><button class="btn ghost" data-action="modal.close">Đóng</button>`;
      document.getElementById('copyPost').addEventListener('click',async e=>{e.preventDefault();try{await navigator.clipboard.writeText(r.body);toast('Đã sao chép nội dung.')}catch(_){toast('Trình duyệt không cấp quyền clipboard. Hãy tự sao chép nội dung.',true)}});break;
    }
    case 'content.complete':publishModal(id);break;
    case 'content.cancel':await api('/api/contents/'+id+'/cancel-schedule','POST');await reload();break;
    case 'content.media':{
      modal('🖼️ Tải ảnh cho bài đăng','<div class="form-field"><label>Ảnh PNG, JPG hoặc WEBP (tối đa 12MB)</label><input name="file" type="file" accept="image/png,image/jpeg,image/webp" required></div>','Tải lên và liên kết',async (_f,form)=>{
        const file=form.querySelector('input[type=file]').files[0];if(!file)throw new Error('Hãy chọn ảnh.');
        const data=new FormData();data.append('file',file);
        const result=await api('/api/media','POST',data);await api('/api/contents/'+id+'/media','POST',{path:result.url});toast('Đã tải lên và gắn ảnh; nội dung cần được duyệt lại.');
      });break;
    }
    case 'task.run':await api('/api/tasks/'+id+'/run','POST');toast('Đã gửi tác vụ vào worker.');setTimeout(reload,1200);break;
    case 'tasks.run-queued':{const r=await api('/api/tasks/run-queued','POST');toast('Đã gửi '+r.submitted+' nhiệm vụ vào worker.');setTimeout(reload,1200);break;}
    case 'task.filter':S.taskFilter=id;render();break;
    case 'metrics.import':metricImportForm();break;
    case 'metrics.learn':{
      const p=document.querySelector('select[name="learnpage"]')?.value;
      if(!p)throw new Error('Hãy chọn Fanpage trước.');
      const r=await api('/api/pages/'+p+'/learn','POST');toast('Đã lưu bài học từ '+r.samples+' dòng số liệu.');modal('🧠 Kết quả học từ dữ liệu',`<p>${E(r.note)}</p>`);break;
    }
    case 'mirai.check':{const r=await api('/api/mirai/check','POST');toast(r.ok?('MiraiAPI kết nối. Model khả dụng: '+(r.models||[]).slice(0,10).join(', ')):'Không thể kiểm tra MiraiAPI',!r.ok);break;}
    case 'mirai.test-call':{
      const button=el;
      const form=document.getElementById('settingsForm');
      const output=document.getElementById('mirai-test-result');
      const fields=new FormData(form);
      const model=String(fields.get('academy_mirai_model')||'').trim();
      const ratio=Number(fields.get('academy_mirai_ratio'));
      if(!model||!Number.isFinite(ratio)||ratio<0.01||ratio>100)throw new Error('Hãy nhập model và hệ số quota hợp lệ.');
      const settings={academy_mirai_model:model,academy_mirai_ratio:ratio};
      const freshKey=String(fields.get('mirai_key')||'').trim();
      if(freshKey)settings.mirai_key=freshKey;
      button.disabled=true;
      button.textContent='⏳ Đang gọi MiraiAPI...';
      if(output)output.textContent='Đang gửi yêu cầu ngắn để xác minh API thực tế. Có thể phát sinh một ít quota.';
      try{
        await api('/api/settings','POST',settings);
        const r=await api('/api/mirai/test-call','POST');
        const used=r.quota_status==='actual_usage'?`${Number(r.quota_used).toLocaleString('vi-VN')} quota`:`dự trù ${Number(r.quota_used).toLocaleString('vi-VN')} quota`;
        if(output)output.innerHTML='<strong>✅ Test API thành công</strong><div>Model: '+E(r.model)+' · Phản hồi: '+E(r.reply)+'</div><div>Thời gian: '+Number(r.latency_ms)+' ms · Input: '+(r.prompt_tokens??'không có')+' · Output: '+(r.completion_tokens??'không có')+' · '+E(used)+'</div><small>'+E(r.note||'')+'</small>';
        toast('MiraiAPI gọi model thành công. '+used);
        const previous=await api('/api/bootstrap');
        S.data=previous;
      }catch(err){
        if(output)output.innerHTML='<strong>❌ Không gọi được MiraiAPI</strong><div>'+E(err.message)+'</div><small>Kiểm tra API Key, model, hạn mức và mạng. API key không được hiển thị.</small>';
        toast(err.message,true);
      }finally{button.disabled=false;button.textContent='⚡ Test gọi API Mirai (tốn ít quota)';}
      break;
    }

    case 'claude.check':{const r=await api('/api/claude/check','POST');toast(r.ok?('Claude đã kết nối. Haiku: '+(r.haiku_available?'Có':'Không')+'; Sonnet: '+(r.sonnet_available?'Có':'Không')):'Không thể kiểm tra Claude',!r.ok);break;}
    case 'academy.toggle':{const was=!!S.data.academy?.enabled;await api('/api/settings','POST',{academy_enabled:!was});toast(was?'Đã tạm dừng học tự động.':'Đã bật học tự động khi server đang chạy.');await reload();break;}
    case 'academy.step':{const x=await api('/api/academy/step','POST');toast(x.status==='started'?'Đã gửi một bước học vào hàng đợi.':'Học viện đang xử lý.');setTimeout(reload,1500);break;}
    case 'brain.learn-now':{
      const result=await api('/api/brains/learn-now','POST');toast('Đã xử lý '+result.processed+' sự kiện học tập cục bộ, không dùng Claude.');await reload();break;
    }
    case 'brain.memory':{
      const res=await api('/api/brains/'+encodeURIComponent(id)+'/memories');
      const a=V('agents').find(x=>x.id===id)||{name:id};
      modal('🧠 Bộ não '+a.name,`<p class="muted">Bộ nhớ nội bộ, phân biệt dữ kiện được xác minh và nhận xét chưa xác minh. Không phải nhật ký suy nghĩ ẩn của mô hình.</p><div class="brain-memories">${res.items?.length?res.items.slice(0,35).map(m=>`<div class="activity-item"><strong>${E(m.kind)} · ${m.confidence==='verified'?'✅ Đã xác minh':'◌ Chưa xác minh'}</strong><p>${E(m.content)}</p><small class="muted">${E(m.source_ref||'Nội bộ')} · ${F(m.created)}</small></div>`).join(''):empty('📭','Chưa có bài học','Agent sẽ ghi nhớ khi hoàn thành nhiệm vụ hoặc có KPI thực tế.')}</div>`);break;
    }
    case 'agent.details':{
      const a=V('agents').find(x=>x.id===id);
      if(!a)return;const tasks=V('tasks').filter(t=>t.agent_id===id).slice(0,6);
      modal(a.emoji+' '+a.name,`<p>${E(a.description)}</p><p>${a.active_tasks} nhiệm vụ đang chạy · ${a.queued_tasks} nhiệm vụ chờ</p><div class="subtle-divider"></div>`+
      (tasks.map(t=>`<div class="activity-item"><strong>${E(t.title)}</strong><p>${E(t.status)} · ${F(t.created)}</p></div>`).join('')||empty('📭','Chưa có nhiệm vụ cho agent này'))+`<div class="actions"><button type="button" class="btn ghost sm" data-action="brain.memory" data-id="${E(id)}">🧠 Xem trí nhớ agent</button></div>`);break;
    }
  }
}
document.addEventListener('click',async e=>{
  const route=e.target.closest('[data-route]');if(route){navigate(route.dataset.route);return;}
  const target=e.target.closest('[data-action]');if(!target)return;
  if(target.disabled)return;target.disabled=true;
  try{await action(target.dataset.action,target.dataset.id,target);}catch(err){toast(err.message,true);}finally{if(target.isConnected)target.disabled=false;}
});
document.addEventListener('submit',async e=>{
  if(e.target.id==='chatForm'){
    e.preventDefault();if(S.busy)return;const input=e.target.elements.message;const msg=input.value.trim();if(!msg)return;
    S.busy=true;render();try{const r=await api('/api/ceo/chat','POST',{message:msg});await reload();if(r.mode==='error')toast('CEO AI gặp lỗi: xem trả lời trong hội thoại.',true);}
    catch(err){toast(err.message,true)}finally{S.busy=false;render();}
  }
  if(e.target.id==='academyForm'){
    e.preventDefault();const values=Object.fromEntries(new FormData(e.target).entries());
    try{const r=await api('/api/academy/sources','POST',{title:values.title,source_ref:values.source_ref||'',content:values.content,owner_has_rights:!!values.owner_has_rights});toast(r.duplicate?'Tài liệu đã có, không nạp trùng.':'Đã tạo '+r.jobs+' bài đào tạo cho 9 agent.');e.target.reset();await reload();}catch(err){toast(err.message,true);}
  }
  if(e.target.id==='settingsForm'||e.target.id==='firefoxForm'){
    e.preventDefault();const f=Object.fromEntries(new FormData(e.target).entries());const current=S.data.settings;
    const payload={};
    if(e.target.id==='settingsForm'){
      payload.daily_llm_call_limit=Number(f.daily_llm_call_limit);
      payload.claude_daily_budget_usd=Number(f.claude_daily_budget_usd);
      payload.claude_agent_daily_budget_usd=Number(f.claude_agent_daily_budget_usd);
      payload.academy_daily_token_limit=Number(f.academy_daily_token_limit);
      payload.academy_interval_seconds=Number(f.academy_interval_seconds);
      payload.academy_enabled=!!f.academy_enabled;
      payload.auto_run_agents=!!f.auto_run_agents;
      payload.claude_cache_enabled=!!f.claude_cache_enabled;
      payload.brain_learning_enabled=!!f.brain_learning_enabled;
      if(f.claude_key?.trim())payload.claude_key=f.claude_key.trim();
      if(f.mirai_key?.trim())payload.mirai_key=f.mirai_key.trim();
      payload.academy_mirai_model=(f.academy_mirai_model||'').trim();
      payload.academy_mirai_ratio=Number(f.academy_mirai_ratio);
    }else if(e.target.id==='firefoxForm'){
      payload.firefox_path=f.firefox_path??current.firefox_path;
    }
    try{await api('/api/settings','POST',payload);await reload();toast('Đã lưu cấu hình.');}catch(err){toast(err.message,true);}
  }
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();if(e.key==='Enter'&&e.ctrlKey&&e.target.closest('#chatForm')){e.preventDefault();e.target.closest('form').requestSubmit();}});
window.addEventListener('hashchange',()=>{const route=location.hash.slice(1);if(ROUTES.some(r=>r[0]===route)&&route!==S.route){S.route=route;render();}});
(async()=>{try{await reload();if(['downloading','verifying','installer_opened','checking'].includes(S.data?.firefox_installer?.state))startFirefoxInstallerPoll();setInterval(async()=>{if(S.busy||document.querySelector('#modal-root .modal')||document.activeElement?.matches('input,textarea,select'))return;
  try{S.data=await api('/api/bootstrap');if(S.route==='office')updateOfficeData();else if(['tasks','accounts','insights','brains','academy','growth'].includes(S.route))render();}catch(_){}},12000);}catch(e){document.getElementById('view').innerHTML=`<div class="card"><h2>⚠️ Không thể kết nối backend</h2><p>${E(e.message)}</p><p>Khởi động: <code>python -m uvicorn app.main:app --host 127.0.0.1 --port 8765</code></p></div>`;}})();


// Keep the currently open dashboard in sync with a restarted local backend.
// A failed health check is expected while Python restarts; reload only after
// a NEW instance ID appears, never on an intermittent network error.
let bootInstanceId=null;
let healthPollBusy=false;
async function watchBackendRestart(){
  if(healthPollBusy)return;
  healthPollBusy=true;
  try{
    const resp=await fetch('/api/health',{cache:'no-store'});
    if(!resp.ok)return;
    const state=await resp.json();
    if(!state.ok||!state.instance_id)return;
    if(bootInstanceId===null){bootInstanceId=state.instance_id;return;}
    if(bootInstanceId!==state.instance_id){
      window.location.reload();  // Preserve current route/hash.
    }
  }catch(_){/* server is briefly offline during the restart */}
  finally{healthPollBusy=false;}
}
watchBackendRestart();
setInterval(watchBackendRestart,3000);
