/* AI Fanpage Company — animated miniature isometric office.
   Zero external dependencies. Motion is a visualization, not a claim that
   agents spoke or acted: real task counts/logs remain separate from animation. */
(() => {
  'use strict';
  const W = 1200, H = 680;
  const TAU = Math.PI * 2;
  const DEFINITIONS = [
    ['ceo','CEO',2.6,3.12,'#5867d9','#402a28','#f5bb92'],
    ['research','Nghiên cứu',4.4,5.96,'#3fb4b0','#3f313b','#edbd97'],
    ['strategy','Chiến lược',6.8,4.90,'#8a70d5','#41281d','#edb48b'],
    ['content','Content',3.0,9.45,'#e789a1','#43302b','#f1c49b'],
    ['creative','Thiết kế',6.0,10.15,'#e9a74b','#6c3e22','#e9b38f'],
    ['publishing','Xuất bản',10.3,9.8,'#5f9ad7','#383037','#edbf9a'],
    ['customer','CSKH',13.45,9.42,'#db88c8','#352934','#e6b18b'],
    ['analytics','Phân tích',12.4,6.20,'#4bbd9d','#4a3930','#f3c49f'],
    ['compliance','Kiểm duyệt',9.05,7.1,'#d37d78','#342721','#e7b48e']
  ];
  const clamp = (x,a,b)=>Math.max(a,Math.min(b,x));
  const mix = (a,b,t)=>a+(b-a)*t;
  const hash = value => [...String(value)].reduce((n,c)=>(n*33+c.charCodeAt(0))>>>0,5381);
  function path(ctx,pts){ctx.beginPath();ctx.moveTo(...pts[0]);for(let i=1;i<pts.length;i++)ctx.lineTo(...pts[i]);ctx.closePath();}
  function rr(ctx,x,y,w,h,r){const q=Math.min(r,w/2,h/2);ctx.beginPath();ctx.roundRect(x,y,w,h,q);}
  class OfficeScene {
    constructor(host,data,agentClick){
      this.host=host; this.data=data; this.agentClick=agentClick;this.frame=0;this.destroyed=false;
      this.canvas=document.createElement('canvas');this.canvas.className='live-office-canvas';
      this.canvas.setAttribute('aria-label','Văn phòng hoạt hình isometric với 9 nhân viên AI tí hon đang làm việc và di chuyển');
      this.canvas.setAttribute('role','img');
      host.querySelector?.('.office-live-loading')?.remove();
      host.appendChild(this.canvas);
      this.ctx=this.canvas.getContext('2d',{alpha:false});
      this.zoom=1;this.offsetX=0;this.offsetY=0;this.paused=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches||false;
      this.speed=1;this.lastTime=0;this.clock=0;this.nextChat=9;this.chat=null;this.particles=[];
      this.hovered=null;this.drag=null;this.activityEvent=null;this.lastActivityId=0;this.hasSeenActivity=false;this.staff=DEFINITIONS.map((d,i)=>({id:d[0],short:d[1],home:{x:d[2],z:d[3]},x:d[2],z:d[3],color:d[4],hair:d[5],skin:d[6],index:i,
        state:'work',target:null,queue:[],phase:i*.75,rest:0,meeting:false,busy:false,queued:false,walkPhase:i*.5,
        direction:i%2?-1:1,speechUntil:0}));
      this.onDown=e=>this.pointerDown(e);this.onMove=e=>this.pointerMove(e);this.onUp=e=>this.pointerUp(e);
      this.onWheel=e=>{e.preventDefault();const v=e.deltaY>0?.91:1.1;this.zoomAt(v,e);};
      this.onDbl=e=>{this.resetCamera();};
      this.canvas.addEventListener('pointerdown',this.onDown);this.canvas.addEventListener('pointermove',this.onMove);
      window.addEventListener('pointerup',this.onUp);this.canvas.addEventListener('wheel',this.onWheel,{passive:false});this.canvas.addEventListener('dblclick',this.onDbl);
      this.resizeObserver=typeof ResizeObserver!=='undefined'?new ResizeObserver(()=>this.resize()):null;
      if(this.resizeObserver)this.resizeObserver.observe(host);
      this.resize();this.setData(data);
      this.loop=(t)=>{
        if(this.destroyed)return;
        const dt=Math.min((t-(this.lastTime||t))/1000,.08);this.lastTime=t;
        if(!this.paused)this.update(dt*this.speed);
        this.draw();this.frame=requestAnimationFrame(this.loop);
      };
      this.frame=requestAnimationFrame(this.loop);
    }
    setData(data){
      this.data=data;
      const agents=new Map((data?.agents||[]).map(a=>[a.id,a]));
      for(const p of this.staff){const a=agents.get(p.id);p.busy=!!a?.active_tasks;p.queued=!!a?.queued_tasks;p.name=a?.name||p.short;}
      const latest=(data?.activities||[]).find(a=>a.agent_id && this.staff.some(p=>p.id===a.agent_id))||null;
      const currentId=Number(latest?.id)||0;
      if(this.hasSeenActivity && currentId>this.lastActivityId && latest?.agent_id)this.activityEvent=latest.agent_id;
      this.lastActivityId=Math.max(this.lastActivityId,currentId);
      this.hasSeenActivity=true;
    }
    resize(){
      const rect=this.host.getBoundingClientRect();const ratio=Math.min(window.devicePixelRatio||1,2);
      const width=Math.max(240,rect.width||900),height=Math.max(180,rect.height||530);
      this.canvas.width=Math.round(width*ratio);this.canvas.height=Math.round(height*ratio);
      this.ctx.setTransform(this.canvas.width/W,0,0,this.canvas.height/H,0,0);
    }
    project(x,z,y=0){const scale=34.3*this.zoom;return {x:580+(x-z)*scale+this.offsetX,y:110+(x+z)*scale*.515-y*scale*1.27+this.offsetY};}
    poly(worldPoints,color,stroke=null){const ctx=this.ctx;path(ctx,worldPoints.map(p=>{const s=this.project(...p);return [s.x,s.y];}));ctx.fillStyle=color;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1;ctx.stroke();}}
    shadow(x,z,sx=30,sy=12,alpha=.21){const ctx=this.ctx,p=this.project(x,z);ctx.fillStyle=`rgba(24,29,75,${alpha})`;ctx.beginPath();ctx.ellipse(p.x,p.y+2,sx*this.zoom,sy*this.zoom,0,0,TAU);ctx.fill();}
    prism(x,z,w,d,h,color,top='#fff',side='#8d8bb9'){
      this.poly([[x,z,0],[x+w,z,0],[x+w,z,h],[x,z,h]],side);
      this.poly([[x+w,z,0],[x+w,z+d,0],[x+w,z+d,h],[x+w,z,h]],color);
      this.poly([[x,z+d,0],[x+w,z+d,0],[x+w,z+d,h],[x,z+d,h]],color);
      this.poly([[x,z,h],[x+w,z,h],[x+w,z+d,h],[x,z+d,h]],top,'#ffffff2a');
    }
    drawWall(){
      const c=this.ctx;
      this.poly([[0,0,0],[16.5,0,0],[16.5,0,3.3],[0,0,3.3]],'#b6beed');
      this.poly([[0,0,0],[0,12,0],[0,12,3.3],[0,0,3.3]],'#d4c9e8');
      for(let x=1;x<16;x+=3){
        this.poly([[x,0,1.1],[x+2.4,0,1.1],[x+2.4,0,2.9],[x,0,2.9]],'#a2cde9','#f1ecff');
        this.poly([[x+.15,0,1.2],[x+2.25,0,1.2],[x+2.25,0,2.8],[x+.15,0,2.8]],'#91c6ea');
        const sp=this.project(x+.5,0,2);const gradient=c.createLinearGradient(sp.x,sp.y,sp.x+70,sp.y+70);gradient.addColorStop(0,'#f9fcff99');gradient.addColorStop(1,'#d9ebff00');c.fillStyle=gradient;
        path(c,[[sp.x,sp.y-8],[sp.x+18,sp.y-18],[sp.x+90,sp.y+100],[sp.x+70,sp.y+110]]);c.fill();
      }
      for(let z=1;z<12;z+=2.8){this.poly([[0,z,1],[0,z+2.2,1],[0,z+2.2,2.8],[0,z,2.8]],'#b7b1e6','#efefff');}
      this.poly([[0,0,0],[16.5,0,0],[16.5,12,0],[0,12,0]],'#d6d0e9','#f8edff');
      for(let x=0;x<16.5;x++){for(let z=0;z<12;z++){
        const shade=(x+z)%3===0?'#f8f4ff33':(x+z)%3===1?'#b8b2dd15':'#fff3e51a';
        this.poly([[x,z,.006],[x+1,z,.006],[x+1,z+1,.006],[x,z+1,.006]],shade);
      }}
      // floor carpet for the conference zone and content desks
      this.poly([[7.1,2.15,.025],[10.45,2.15,.025],[10.45,5,.025],[7.1,5,.025]],'#bd9cff70');
      this.poly([[2.4,6.5,.025],[7.9,6.5,.025],[7.9,10.2,.025],[2.4,10.2,.025]],'#c7e4e070');
      // Small ceiling-style light pools
      for(const [x,z] of [[3,3],[9,5],[12,8]]){const p=this.project(x,z);const grad=c.createRadialGradient(p.x,p.y,3,p.x,p.y,165);grad.addColorStop(0,'#ffffff5b');grad.addColorStop(1,'#ffffff00');c.fillStyle=grad;c.beginPath();c.ellipse(p.x,p.y,165,70,0,0,TAU);c.fill();}
    }
    desk(x,z,w=1.75,d=1.15,screen='#90a6ff'){
      this.shadow(x+w/2,z+d/2,55,23,.11);
      this.prism(x,z,w,d,.53,'#826c91','#efe3db','#a396b6');
      const p=this.project(x+w*.47,z+d*.29,.72);
      const c=this.ctx;
      c.save();c.translate(p.x,p.y);c.rotate(.12);c.fillStyle='#746c9e';rr(c,-19,-30,38,27,4);c.fill();
      const g=c.createLinearGradient(0,-29,20,-4);g.addColorStop(0,'#2f335f');g.addColorStop(1,screen);c.fillStyle=g;rr(c,-16,-27,32,22,3);c.fill();
      c.fillStyle='#fff9';for(let i=0;i<3;i++)c.fillRect(-11+i*8,-10-i*3,5,3+i*3);
      c.fillStyle='#51485d';c.fillRect(-2,-2,4,9);c.fillRect(-11,7,23,3);c.restore();
      const mug=this.project(x+w*.83,z+d*.78,.62);c.fillStyle='#fff2f5';c.beginPath();c.ellipse(mug.x,mug.y,5,6,.25,0,TAU);c.fill();
    }
    table(x,z,w=2.3,d=1.6){
      this.shadow(x+w/2,z+d/2,64,26,.14);
      this.prism(x+.27,z+.2,w-.54,d-.4,.42,'#77689b','#c8b6e8','#a092c7');
      this.prism(x,z,w,d,.55,'#9279a8','#faf2e9','#b8a8c9');
      const c=this.ctx,p=this.project(x+w/2,z+d/2,.6);c.fillStyle='#c8a7fc';c.beginPath();c.ellipse(p.x,p.y,13,6,0,0,TAU);c.fill();
    }
    plant(x,z,s=.8){
      const c=this.ctx;this.shadow(x,z,13,5,.13);
      this.prism(x-.16,z-.15,.34,.34,.34,'#b8948c','#fde2c9','#d6b3a6');
      const p=this.project(x,z,.58);c.save();c.translate(p.x,p.y);
      for(let i=0;i<7;i++){const a=i*TAU/7;const tx=Math.sin(a)*12*s,ty=-9-Math.cos(a)*14*s;
        c.strokeStyle='#3e9d7c';c.lineWidth=2;c.beginPath();c.moveTo(0,7);c.quadraticCurveTo(tx*.8,ty*.65,tx,ty);c.stroke();
        c.fillStyle=i%2?'#4db98a':'#78d9a1';c.beginPath();c.ellipse(tx,ty,5*s,12*s,a,0,TAU);c.fill();}
      c.restore();
    }
    wallSign(x,z,label){
      const c=this.ctx,p=this.project(x,z,2.6);c.save();c.translate(p.x,p.y);c.fillStyle='#434889e6';rr(c,-42,-16,84,29,8);c.fill();c.strokeStyle='#c7b2fc';c.lineWidth=2;c.stroke();c.fillStyle='#fff';c.textAlign='center';c.font='bold 13px system-ui';c.fillText(label,0,3);c.restore();
    }
    drawFurniture(){
      const c=this.ctx;
      // Low glass partitions; objects deliberately spaced for visible footpaths.
      this.prism(.7,.55,3.8,.18,.9,'#b8a7db','#dfe8ff7a','#c9c2ed');
      this.prism(.7,4.0,3.8,.15,.75,'#b8a7db','#e3e3fc55','#bcb2e2');
      this.wallSign(2.1,.1,'CEO AI');
      this.desk(1.5,1.6,2.15,1.1,'#9f88f1');
      this.desk(4.0,4.25,1.8,1.1,'#9bc0f0');
      this.desk(6.2,3.25,1.8,1.1,'#a7acff');
      this.desk(2.3,7.7,2.1,1.05,'#ec94b8');
      this.desk(5.25,8.4,2,1.12,'#f2bd77');
      this.desk(9.7,8.05,1.85,1.1,'#8cbfe8');
      this.desk(12.95,7.55,1.85,1.15,'#d8a1e5');
      this.desk(12.15,4.45,1.8,1.15,'#9be0c0');
      this.desk(9.25,5.25,1.8,1.12,'#e5ad98');
      this.table(8.1,2.6,2.45,1.5);
      // Books, sofa, and planters make the room feel lived-in.
      this.prism(13.1,1.0,2.4,1.08,.33,'#8b86a7','#d3a0b5','#b7a2b5');
      this.prism(13.15,1.0,2.3,.24,.8,'#a58ab5','#eed2e5','#ad97b7');
      for(const [x,z,s] of [[.6,1,.85],[.7,6,.6],[4.6,2.3,.65],[7.2,10.5,.78],[11.6,2,.85],[15,10.7,.8],[14.8,4,.6]])this.plant(x,z,s);
      // Monitors show real-time-looking abstract visuals, not invented results.
      const sign=this.project(12.7,.1,2.9);c.save();c.translate(sign.x,sign.y);c.fillStyle='#f7ffff';c.font='bold 17px system-ui';c.shadowColor='#75a7fe';c.shadowBlur=16;c.fillText('AI MARKETING',0,0);c.restore();
    }
    goto(p,x,z,after='work'){
      p.queue.push({x,z,after});if(!p.target){p.target=p.queue.shift();p.state='walk';}
    }
    startChat(forcedId=null){
      const active=this.staff.filter(p=>p.busy||p.queued);
      const actor=(forcedId&&this.staff.find(p=>p.id===forcedId))||(active.length?active[Math.floor(this.clock)%active.length]:this.staff[Math.floor(this.clock/7)%this.staff.length]);
      const others=this.staff.filter(p=>p!==actor && p.state==='work');
      if(!others.length)return;
      const partner=others[(actor.index+Math.floor(this.clock))%others.length];
      if(actor.state!=='work')return;
      const c={a:actor.id,b:partner.id,phase:'walking',elapsed:0,duration:6.5,real:!!(actor.busy||partner.busy),show:false};
      this.chat=c;
      actor.meeting=true;partner.meeting=true;
      this.goto(actor,7.2,5.25,'meet');this.goto(partner,8.0,5.5,'meet');
    }
    update(dt){
      this.clock+=dt;
      for(const p of this.staff){
        p.phase+=dt*(p.busy?4.7:2.3);
        if(p.state==='walk'&&p.target){
          const dx=p.target.x-p.x,dz=p.target.z-p.z,d=Math.hypot(dx,dz),pace=(p.busy?1.75:1.25)*dt;
          p.direction=dx>=0?1:-1;p.walkPhase+=dt*10;
          if(d<=pace){p.x=p.target.x;p.z=p.target.z;const target=p.target;p.target=p.queue.shift()||null;p.state=p.target?'walk':target.after;
            if(p.state==='meet')p.rest=5.5;}
          else{p.x+=dx/d*pace;p.z+=dz/d*pace;}
        }else if(p.state==='meet'){p.rest-=dt;}
      }
      if(this.chat){
        this.chat.elapsed+=dt;
        const a=this.staff.find(p=>p.id===this.chat.a),b=this.staff.find(p=>p.id===this.chat.b);
        if(a.state==='meet'&&b.state==='meet'){this.chat.show=true;this.chat.phase='talking';}
        if(this.chat.show && this.chat.elapsed>this.chat.duration+5){
          for(const p of [a,b]){p.meeting=false;this.goto(p,p.home.x,p.home.z,'work');}
          this.chat=null;this.nextChat=this.clock+13+Math.random()*9;
        }
        if(this.chat && !this.chat.show && this.chat.elapsed>14){
          for(const p of [a,b]){p.meeting=false;this.goto(p,p.home.x,p.home.z,'work');}
          this.chat=null;this.nextChat=this.clock+18;
        }
      }else if(this.activityEvent && this.staff.some(p=>p.id===this.activityEvent && p.state==='work')){
        this.startChat(this.activityEvent);this.activityEvent=null;
      }else if(this.clock>=this.nextChat){this.startChat();this.nextChat=this.clock+20;}
    }
    character(p){
      const c=this.ctx,s=this.project(p.x,p.z);
      const scale=this.zoom*(p.id==='ceo'?1.16:1.0);
      const walking=p.state==='walk',b=Math.sin(p.walkPhase)*(walking?4.5:0),nod=Math.sin(p.phase)*1.2;
      const px=s.x,py=s.y;
      this.shadow(p.x,p.z,16,5,.23);
      c.save();c.translate(px,py-b);c.scale(scale,scale);
      // Toy-like depth, with animated walking legs and rounded shoes.
      const stride=walking?Math.sin(p.walkPhase)*6:Math.sin(p.phase)*1.1;
      c.strokeStyle='#35314f';c.lineWidth=5.6;c.lineCap='round';
      c.beginPath();c.moveTo(-5,-12);c.lineTo(-5+stride,-2);c.moveTo(5,-12);c.lineTo(5-stride,-2);c.stroke();
      c.fillStyle='#36324a';c.beginPath();c.ellipse(-5+stride,-2,6,3.2,0,0,TAU);c.ellipse(5-stride,-2,6,3.2,0,0,TAU);c.fill();
      const shirt=c.createLinearGradient(-12,-30,12,-11);shirt.addColorStop(0,'#fff9');shirt.addColorStop(.25,p.color);shirt.addColorStop(1,'#333b7499');
      c.fillStyle=shirt;c.beginPath();c.ellipse(0,-22,14,15,0,0,TAU);c.fill();
      const armSwing=walking?Math.sin(p.walkPhase)*9:Math.sin(p.phase)*3.4;
      c.strokeStyle=p.skin;c.lineWidth=7;
      c.beginPath();c.moveTo(-11,-28);c.lineTo(-18,-16+armSwing);c.moveTo(11,-28);c.lineTo(18,-17-armSwing);c.stroke();
      c.fillStyle=p.skin;c.beginPath();c.arc(-18,-16+armSwing,3.2,0,TAU);c.arc(18,-17-armSwing,3.2,0,TAU);c.fill();
      c.fillStyle='#ffffffa6';rr(c,-4,-36,8,8,3);c.fill();
      c.translate(0,nod+(-.8*Math.cos(p.phase)));
      const face=c.createRadialGradient(-7,-47,3,0,-41,17);face.addColorStop(0,'#ffe8c6');face.addColorStop(.68,p.skin);face.addColorStop(1,'#c4896c');
      c.fillStyle=face;c.beginPath();c.ellipse(0,-43,17.2,17.7,0,0,TAU);c.fill();
      c.fillStyle=p.hair;c.beginPath();c.ellipse(0,-53,18,10,0,Math.PI,TAU);c.fill();
      c.beginPath();c.ellipse(-12,-52,6,9,-.4,Math.PI,TAU);c.ellipse(10,-53,6,10,.4,Math.PI,TAU);c.fill();
      c.fillStyle='#252638';c.beginPath();c.arc(-5,-43,1.7,0,TAU);c.arc(5,-43,1.7,0,TAU);c.fill();
      c.fillStyle='#e78591b8';c.beginPath();c.ellipse(-10,-38,3.4,2,0,0,TAU);c.ellipse(10,-38,3.4,2,0,0,TAU);c.fill();
      c.strokeStyle='#945b61';c.lineWidth=1.3;c.beginPath();c.arc(0,-39,3.4,.08,Math.PI-.08);c.stroke();
      if(p.id==='research'||p.id==='analytics'){c.strokeStyle='#4c4a61';c.lineWidth=1.7;c.strokeRect(-9,-47,8,7);c.strokeRect(1,-47,8,7);c.beginPath();c.moveTo(-1,-44);c.lineTo(1,-44);c.stroke();}
      if(p.busy){c.strokeStyle='#5fe7ba';c.lineWidth=1.5;c.beginPath();c.arc(0,-43,21,-.68,.45);c.stroke();}
      c.restore();
      // On-duty label uses live backend state only.
      if(this.hovered===p.id){
        const a=this.data?.agents?.find(x=>x.id===p.id);this.label(s.x,s.y-80*scale,(a?.name||p.short),p.busy?'Đang xử lý nhiệm vụ':p.queued?'Có nhiệm vụ chờ':'Sẵn sàng');
      }
    }
    label(x,y,name,status){
      const c=this.ctx;c.save();c.font='bold 13px system-ui';const w=Math.max(c.measureText(name).width, c.measureText(status).width)+26;
      rr(c,x-w/2,y-10,w,45,10);c.fillStyle='#19294be8';c.fill();c.strokeStyle='#adc4f7b0';c.stroke();
      c.fillStyle='#fff';c.textAlign='center';c.fillText(name,x,y+7);c.font='11px system-ui';c.fillStyle='#aee0e9';c.fillText(status,x,y+23);c.restore();
    }
    bubble(){
      if(!this.chat?.show)return;
      const c=this.ctx,a=this.staff.find(p=>p.id===this.chat.a),b=this.staff.find(p=>p.id===this.chat.b);
      const mid=this.project((a.x+b.x)/2,(a.z+b.z)/2),px=mid.x,py=mid.y-90*this.zoom;
      const msg=this.chat.real?'Trao đổi về nhiệm vụ':'Trao đổi ý tưởng';
      c.save();c.font='bold 13px system-ui';const w=c.measureText(msg).width+28;
      rr(c,px-w/2,py-16,w,32,13);c.fillStyle='#fff8f6';c.fill();c.strokeStyle='#ad9af9';c.lineWidth=1.4;c.stroke();
      c.fillStyle='#645a98';c.textAlign='center';c.fillText(msg,px,py+4);
      path(c,[[px-8,py+16],[px+7,py+16],[px,py+24]]);c.fill();c.restore();
    }
    draw(){
      const c=this.ctx;if(!c)return;
      c.save();c.setTransform(this.canvas.width/W,0,0,this.canvas.height/H,0,0);
      let g=c.createLinearGradient(0,0,0,H);g.addColorStop(0,'#d9eafa');g.addColorStop(.5,'#decff1');g.addColorStop(1,'#c9b9dc');c.fillStyle=g;c.fillRect(0,0,W,H);
      // Ambient bokeh and city outside windows.
      for(let i=0;i<11;i++){const x=50+i*135,h=35+(i*37)%110;c.fillStyle='#b3c9e457';rr(c,x,66-h/2,60,h,4);c.fill();}
      this.drawWall();this.drawFurniture();
      for(const p of [...this.staff].sort((a,b)=>(a.x+a.z)-(b.x+b.z)))this.character(p);
      this.bubble();
      // Service legend lives on the canvas so fullscreen and screenshots retain context.
      c.fillStyle='#27365cbe';rr(c,20,H-55,370,34,12);c.fill();
      c.fillStyle='#f6f4ff';c.font='12px system-ui';c.fillText('● Chuyển động minh họa  ·  ⚡ Trạng thái việc lấy từ backend',35,H-33);
      if(this.paused){c.fillStyle='#252953ab';rr(c,W/2-66,30,132,34,14);c.fill();c.textAlign='center';c.fillStyle='#fff';c.font='bold 14px system-ui';c.fillText('⏸ Đã tạm dừng',W/2,52);}
      c.restore();
    }
    pointerCoords(e){const b=this.canvas.getBoundingClientRect();return {x:(e.clientX-b.left)*W/b.width,y:(e.clientY-b.top)*H/b.height};}
    pick(e){const p=this.pointerCoords(e);let chosen=null,best=29;
      for(const agent of this.staff){const q=this.project(agent.x,agent.z),d=Math.hypot(q.x-p.x,q.y-34*this.zoom-p.y);if(d<best){chosen=agent;best=d;}}
      return chosen;
    }
    pointerDown(e){if(e.button!==0)return;this.drag={id:e.pointerId,x:e.clientX,y:e.clientY,sx:this.offsetX,sy:this.offsetY,moved:false};this.canvas.setPointerCapture?.(e.pointerId);}
    pointerMove(e){const p=this.pick(e);this.hovered=p?.id||null;this.canvas.style.cursor=p?'pointer':this.drag?'grabbing':'grab';
      if(this.drag&&this.drag.id===e.pointerId){const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;
        if(Math.hypot(dx,dy)>5)this.drag.moved=true;
        if(this.drag.moved){const box=this.canvas.getBoundingClientRect();this.offsetX=clamp(this.drag.sx+dx*W/box.width,-260,260);this.offsetY=clamp(this.drag.sy+dy*H/box.height,-195,195);}
      }
    }
    pointerUp(e){if(!this.drag||e.pointerId!==this.drag.id)return;
      const moved=this.drag.moved;this.drag=null;
      if(!moved){const picked=this.pick(e);if(picked&&typeof this.agentClick==='function')this.agentClick(picked.id);}
    }
    zoomAt(mult,e){const old=this.zoom;this.zoom=clamp(this.zoom*mult,.73,1.7);const f=this.zoom/old;if(e){const p=this.pointerCoords(e);this.offsetX=clamp((this.offsetX-(p.x-580))*(f-1)+this.offsetX,-260,260);this.offsetY=clamp((this.offsetY-(p.y-320))*(f-1)+this.offsetY,-195,195);}}
    resetCamera(){this.zoom=1;this.offsetX=0;this.offsetY=0;}
    toggle(){this.paused=!this.paused;return this.paused;}
    setSpeed(){this.speed=this.speed===1?1.75:1;return this.speed;}
    destroy(){this.destroyed=true;cancelAnimationFrame(this.frame);this.resizeObserver?.disconnect();this.canvas.removeEventListener('pointerdown',this.onDown);this.canvas.removeEventListener('pointermove',this.onMove);window.removeEventListener('pointerup',this.onUp);this.canvas.removeEventListener('wheel',this.onWheel);this.canvas.removeEventListener('dblclick',this.onDbl);this.canvas.remove();}
  }
  let current=null;
  window.OfficeLive={
    mount(host,data,onAgentClick){if(current)current.destroy();if(!host)return null;current=new OfficeScene(host,data,onAgentClick);return current;},
    unmount(){if(current){current.destroy();current=null;}},
    update(data){current?.setData(data);},
    toggle(){return current?.toggle();},
    speed(){return current?.setSpeed();},
    reset(){current?.resetCamera();},
    get current(){return current;}
  };
})();
