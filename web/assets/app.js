/* AI Fanpage Company — local-first SPA (no external JS dependencies). */
'use strict';
const ROUTES=[
  ['office','🏢','Văn phòng 3D'],['ceo','🧠','AI CEO'],['pages','📣','100 Fanpage'],
  ['accounts','🦊','Tài khoản Firefox'],['content','📝','Nội dung & Lịch'],
  ['tasks','✅','Nhiệm vụ AI'],['insights','📊','Báo cáo & Bộ nhớ'],['settings','⚙️','Cài đặt']
];
const S={data:null,route:(location.hash.slice(1)||'office'),busy:false,taskFilter:'all'};
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
  <div class="columns"><div class="card chat-room"><div class="space-between"><div><h2>🧠 Trao đổi trực tiếp với CEO</h2><div class="card-sub">Kết nối ${E(S.data.settings.provider||'chưa có')} ${S.data.settings[S.data.settings.provider+'_configured']?'· Đã có API key':'· Chưa có API key'}</div></div><span class="badge blue">CEO</span></div>
    <div class="chat-messages" id="chatMessages">${chat.length?chat.map(m=>`<div class="chat-msg ${m.role==='user'?'owner':''}"><div class="chat-av">${m.role==='user'?'👤':'🧠'}</div><div><div class="chat-bubble">${E(m.body)}</div><small class="muted">${F(m.created)}</small></div></div>`).join(''):empty('🧠','Bắt đầu giao việc cho CEO','Ví dụ: Lập chiến lược 7 ngày cho các Page về trà thảo mộc.')}</div>
    <form id="chatForm" class="chat-compose"><textarea class="textarea" name="message" maxlength="6000" required placeholder="CEO, hãy lập kế hoạch nội dung cho các Fanpage của công ty..."></textarea><button class="btn primary" ${S.busy?'disabled':''}>${S.busy?'Đang suy luận…':'Giao việc ↗'}</button></form></div>
    <div class="stack"><div class="card"><h2>🎯 Nguyên tắc quản trị</h2><div class="subtle-divider"></div><p>CEO chỉ được giao nhiệm vụ nội bộ, tạo kế hoạch và đề xuất. Nhân viên không được tự nhận đã đăng bài hay thu thập dữ liệu không có thật.</p><div class="status-bubble">🔒 Chỉ tự động hóa nội bộ; không tự thao tác Facebook</div></div>
      <div class="card"><h2>🔍 Công việc gần đây</h2>${V('tasks').slice(0,6).map(t=>`<div class="agent-mini"><div class="agent-face">${V('agents').find(a=>a.id===t.agent_id)?.emoji||'🤖'}</div><div style="flex:1"><strong>${E(short(t.title,50))}</strong><small>${E(agentName(t.agent_id))} · ${F(t.created)}</small></div>${badge(t.status)}</div>`).join('')||empty('📭','Chưa có nhiệm vụ')}</div>
      <div class="card"><h2>⚙️ Kết nối trí tuệ AI</h2><p class="muted">Cấu hình Gemini hoặc Groq trong phần Cài đặt. Không có API key, CEO chỉ lưu yêu cầu vào hàng đợi và không bịa ra hành động đã thực hiện.</p><button class="btn ghost" data-route="settings">Mở cài đặt AI →</button></div>
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
function renderSettings(){
  const cfg=S.data.settings;
  return `${heading('Cài đặt phần mềm','Tùy chỉnh mô hình AI, hạn mức và đường dẫn Firefox.',`<span class="badge green">🔒 Localhost only</span>`)}
    <div class="columns"><div class="card"><h2>🧠 AI API Settings</h2><p class="card-sub">API key được mã hóa trong thư mục dữ liệu cục bộ; không đưa vào log hay trả về frontend.</p><form id="settingsForm" style="margin-top:17px">
    <div class="form-field"><label>Nhà cung cấp AI chính</label><select class="select" name="provider"><option ${selected(cfg.provider,'gemini')} value="gemini">Google Gemini</option><option ${selected(cfg.provider,'groq')} value="groq">Groq</option></select></div>
    ${field('Model Gemini','gemini_model',cfg.gemini_model,'text','required')}${field('Gemini API key'+(cfg.gemini_configured?' · Đã lưu':''),'gemini_key','','password','placeholder="Để trống nếu giữ key hiện tại"')}
    ${field('Model Groq','groq_model',cfg.groq_model,'text','required')}${field('Groq API key'+(cfg.groq_configured?' · Đã lưu':''),'groq_key','','password','placeholder="Để trống nếu giữ key hiện tại"')}
    ${field('Giới hạn lượt gọi LLM/ngày','daily_llm_call_limit',cfg.daily_llm_call_limit,'number','min="1" max="10000" required')}<label style="display:flex;align-items:center;gap:10px;margin:8px 0 19px;font-size:13px"><input type="checkbox" name="auto_run_agents" ${cfg.auto_run_agents==='1'?'checked':''}> Tự chạy nhiệm vụ AI trong hàng đợi (có dùng API và hạn mức ngày)</label>
    <button class="btn primary block">💾 Lưu cài đặt</button></form></div>
    <div class="stack"><div class="card"><h2>🦊 Firefox</h2><p class="muted">Trạng thái trên máy chạy server: ${S.data.firefox_available?'<span class="badge green">Đã tìm thấy</span>':'<span class="badge red">Chưa tìm thấy</span>'}</p>
    ${S.data.firefox_available?'':firefoxInstallerNotice()}
    <form id="firefoxForm">${field('Đường dẫn Firefox (tùy chọn)','firefox_path',cfg.firefox_path,'text','placeholder="C:\\Program Files\\Mozilla Firefox\\firefox.exe"')}<button class="btn ghost">Lưu đường dẫn</button></form>
    <div class="office-note">Chạy phần mềm trên chính máy Windows có Firefox. Profile được lưu dưới %LOCALAPPDATA%\\AI-Fanpage-Company\\profiles.</div></div>
    <div class="card"><h2>🔐 Bảo mật</h2><p>Backend chỉ nghe <code>127.0.0.1:8765</code>. Không mở cổng công khai. Tài khoản Facebook đăng nhập trực tiếp trong Firefox, không lưu mật khẩu vào ứng dụng.</p><p class="muted">Bảo vệ toàn bộ thư mục dữ liệu của ứng dụng và khóa mã hóa bằng tài khoản Windows hoặc mã hóa ổ đĩa.</p></div>
    <div class="card"><h2>📌 Phạm vi V1</h2><p>✅ CEO AI thật (khi có key), phân công và nhật ký.</p><p>✅ Profile Firefox cố định, đăng nhập thủ công.</p><p>✅ Nội dung, kiểm duyệt, lịch, bộ nhớ, KPI.</p><p>⚠️ Không tự đăng Facebook bằng UI bot; không tự đọc quyền/Insights.</p></div></div></div>`;
}
function render(){
  if(!S.data)return;
  window.OfficeLive?.unmount();
  nav();const dict={office:renderOffice,ceo:renderCEO,pages:renderPages,accounts:renderAccounts,content:renderContent,tasks:renderTasks,insights:renderInsights,settings:renderSettings};
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
    case 'agent.details':{
      const a=V('agents').find(x=>x.id===id);
      if(!a)return;const tasks=V('tasks').filter(t=>t.agent_id===id).slice(0,6);
      modal(a.emoji+' '+a.name,`<p>${E(a.description)}</p><p>${a.active_tasks} nhiệm vụ đang chạy · ${a.queued_tasks} nhiệm vụ chờ</p><div class="subtle-divider"></div>`+
      (tasks.map(t=>`<div class="activity-item"><strong>${E(t.title)}</strong><p>${E(t.status)} · ${F(t.created)}</p></div>`).join('')||empty('📭','Chưa có nhiệm vụ cho agent này')));break;
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
  if(e.target.id==='settingsForm'||e.target.id==='firefoxForm'){
    e.preventDefault();const f=Object.fromEntries(new FormData(e.target).entries());const current=S.data.settings;
    const payload={provider:f.provider||current.provider,gemini_model:f.gemini_model||current.gemini_model,
      groq_model:f.groq_model||current.groq_model,daily_llm_call_limit:Number(f.daily_llm_call_limit||current.daily_llm_call_limit),
      firefox_path:f.firefox_path??current.firefox_path,auto_run_agents:e.target.id==='settingsForm'?(!!f.auto_run_agents):(current.auto_run_agents==='1')};
    if(f.gemini_key?.trim())payload.gemini_key=f.gemini_key.trim();
    if(f.groq_key?.trim())payload.groq_key=f.groq_key.trim();
    try{await api('/api/settings','POST',payload);await reload();toast('Đã lưu cấu hình.');}catch(err){toast(err.message,true);}
  }
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();if(e.key==='Enter'&&e.ctrlKey&&e.target.closest('#chatForm')){e.preventDefault();e.target.closest('form').requestSubmit();}});
window.addEventListener('hashchange',()=>{const route=location.hash.slice(1);if(ROUTES.some(r=>r[0]===route)&&route!==S.route){S.route=route;render();}});
(async()=>{try{await reload();if(['downloading','verifying','installer_opened','checking'].includes(S.data?.firefox_installer?.state))startFirefoxInstallerPoll();setInterval(async()=>{if(S.busy||document.querySelector('#modal-root .modal')||document.activeElement?.matches('input,textarea,select'))return;
  try{S.data=await api('/api/bootstrap');if(S.route==='office')updateOfficeData();else if(['tasks','accounts','insights'].includes(S.route))render();}catch(_){}},12000);}catch(e){document.getElementById('view').innerHTML=`<div class="card"><h2>⚠️ Không thể kết nối backend</h2><p>${E(e.message)}</p><p>Khởi động: <code>python -m uvicorn app.main:app --host 127.0.0.1 --port 8765</code></p></div>`;}})();
