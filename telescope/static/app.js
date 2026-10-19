'use strict';
const $=id=>document.getElementById(id);
const el=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;};
const display=(v,suffix='')=>v===null||v===undefined||v===''?'待核':`${v}${typeof v==='number'?suffix:''}`;
const money=v=>v===null||v===undefined?'暂无参考':`¥${Number(v).toLocaleString('zh-CN',{maximumFractionDigits:2})}`;
const isEd=m=>{const v=m.parameters.ed;return typeof v==='string'&&!/待核|未知|未列|非ED|普通玻璃/.test(v)&&/ED|低色散/i.test(v);};
const isFlat=m=>{const v=m.parameters.flat_field;return typeof v==='string'&&!/待核|未知|未列/.test(v)&&/平场/.test(v);};
let catalog,filtered=[],page=1,selectedModel=null,previewUrl=null;
const pageSize=20;

function fillSelect(id,values,suffix=''){
  for(const value of values){const option=el('option','',`${value}${suffix}`);option.value=String(value);$(id).append(option);}
}
function applyFilters(){
  const query=$('search').value.toLocaleLowerCase().trim(),brand=$('brand-filter').value,mag=$('mag-filter').value,objective=$('objective-filter').value,price=$('price-filter').value,ed=$('ed-filter').value;
  filtered=catalog.models.filter(m=>(!query||JSON.stringify([m.name,m.spec,m.brand,m.parameters]).toLocaleLowerCase().includes(query))&&(!brand||m.brand===brand)&&(!mag||String(m.parameters.magnification)===mag)&&(!objective||String(m.parameters.objective_mm)===objective)&&(!price||(m.reference_price!==null&&(price==='known'||m.reference_price<=Number(price))))&&(!ed||(ed==='ed'?isEd(m):!isEd(m))));
  const numeric=(v,fallback)=>typeof v==='number'?v:fallback;
  const sort=$('sort').value;
  filtered.sort((a,b)=>sort==='price'?numeric(a.reference_price,Infinity)-numeric(b.reference_price,Infinity):sort==='weight'?numeric(a.parameters.weight_g,Infinity)-numeric(b.parameters.weight_g,Infinity):sort==='field'?numeric(b.parameters.field_deg,-Infinity)-numeric(a.parameters.field_deg,-Infinity):a.brand.localeCompare(b.brand,'zh-CN')||a.name.localeCompare(b.name,'zh-CN'));
  page=1;renderRows();
}
function renderRows(){
  $('model-rows').replaceChildren();
  const pages=Math.max(1,Math.ceil(filtered.length/pageSize));
  $('result-count').textContent=`找到 ${filtered.length} 条型号规格`;
  $('page-label').textContent=`第 ${page} / ${pages} 页`;
  $('previous').disabled=page===1;$('next').disabled=page===pages;
  if(!filtered.length){const tr=el('tr'),td=el('td','muted','没有符合条件的型号，请调整筛选。');td.colSpan=8;tr.append(td);$('model-rows').append(tr);return;}
  for(const m of filtered.slice((page-1)*pageSize,page*pageSize)){
    const tr=el('tr'),nameCell=el('td'),button=el('button','model-name',m.name);
    nameCell.append(el('span','model-meta',m.brand),button);button.addEventListener('click',()=>openDetail(m));tr.append(nameCell);
    const values=[m.spec,money(m.reference_price),display(m.parameters.field_deg,'°'),display(m.parameters.eye_relief_mm,'mm'),display(m.parameters.weight_g,'g')];
    values.forEach((value,i)=>tr.append(el('td',i===1?'price'+(m.reference_price===null?' unknown':''):'',value)));
    const tags=el('td');if(isEd(m))tags.append(el('span','tag','ED'));if(isFlat(m))tags.append(el('span','tag','平场'));if(!tags.children.length)tags.append(el('span','unknown','待核'));tr.append(tags);
    const end=el('td'),arrow=el('button','row-arrow','↗');arrow.setAttribute('aria-label',`查看${m.name}`);arrow.addEventListener('click',()=>openDetail(m));end.append(arrow);tr.append(end);$('model-rows').append(tr);
  }
}
function safeLink(url,label){const a=el('a','',label||url);const parsed=new URL(url,location.origin);if(!['http:','https:'].includes(parsed.protocol))return el('span','',label||url);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;}
function photoCard(p){
  const model=catalog.models.find(m=>m.id===p.model_id),card=el('article','photo-card'),link=el('a');link.href=p.image_url;link.target='_blank';link.rel='noopener noreferrer';
  const image=el('img');image.src=p.image_url;image.alt=`${model?.name||p.model_id}，${p.credit}的实拍`;image.loading='lazy';link.append(image);card.append(link);
  const info=el('div');info.append(el('h3','',model?.name||p.model_id),el('p','',`拍摄：${p.credit}`),el('p','',p.equipment),el('p','',p.conditions));if(p.note)info.append(el('p','',p.note));card.append(info);return card;
}
function renderGallery(){
  const photos=catalog.contributions.filter(p=>p.kind==='photo');$('photo-count').textContent=photos.length;$('photo-gallery').replaceChildren();
  if(!photos.length){const empty=el('div','empty-photos');empty.append(el('strong','','还没有经过审核的实拍图片'),el('span','','留下第一份真实记录，让纸面参数多一个参考。'));$('photo-gallery').append(empty);}
  else for(const p of photos)$('photo-gallery').append(photoCard(p));
}
function openDetail(model){
  selectedModel=model;$('detail-brand').textContent=`${model.brand} / ${model.id}`;$('detail-title').textContent=model.name;
  const content=$('detail-content');content.replaceChildren();
  const price=el('div','detail-price');price.append(el('strong','',money(model.reference_price)),el('span','',`参考入手价格${model.price_asof?' · '+model.price_asof:''}。${catalog.price_note}`));content.append(price);
  content.append(el('p','muted',`规格：${model.spec}。代际/版本：${model.version||'待核'}。`));
  for(const group of [...new Set(catalog.fields.map(f=>f.group))]){
    const section=el('section','parameter-group'),grid=el('div','parameter-grid');section.append(el('h3','',group));
    for(const f of catalog.fields.filter(f=>f.group===group)){
      const row=el('div','parameter-item'),value=el('span','',display(model.parameters[f.key])),status=model.verification[f.key];
      if(status==='unverified')value.append(el('small','parameter-status','待核或存在来源冲突'));
      if(status==='community')value.append(el('small','parameter-status','用户补充，已审核'));
      if(status==='derived')value.append(el('small','parameter-status','按已审核规格重新计算'));
      row.append(el('span','',f.label),value);grid.append(row);
    }section.append(grid);content.append(section);
  }
  const note=el('div','detail-note');note.append(el('p','',model.verification_note||'核验状态待补充'),el('p','',model.experience_note||'暂无独立实际体验证据'));content.append(note);
  const sources=el('section','parameter-group');sources.append(el('h3','','资料来源'));const list=el('ul','source-list');
  for(const url of model.sources){const li=el('li');li.append(safeLink(url));list.append(li);}if(!list.children.length)list.append(el('li','','原记录来源尚未补全，欢迎提交可核对资料。'));sources.append(list);content.append(sources);
  const contributions=catalog.contributions.filter(p=>p.model_id===model.id);
  if(contributions.length){const group=el('section','parameter-group');group.append(el('h3','','用户补充（已审核）'));
    for(const p of contributions){if(p.kind==='photo'){group.append(photoCard(p));continue;}const item=el('div','detail-note');item.append(el('strong','',p.credit));if(p.kind==='parameter')item.append(el('p','',`${catalog.fields.find(f=>f.key===p.field)?.label||'参考入手价'}：${display(p.value)}`));if(p.note)item.append(el('p','',p.note));if(p.source_url)item.append(safeLink(p.source_url,'查看投稿来源'));group.append(item);}content.append(group);
  }
  $('detail-dialog').showModal();$('detail-dialog').scrollTop=0;
}
function updateForm(){
  const kind=$('submit-kind').value;$('photo-fields').classList.toggle('hidden',kind!=='photo');$('parameter-fields').classList.toggle('hidden',kind!=='parameter');
  $('photo-file').required=kind==='photo';$('submit-value').required=kind==='parameter';
  document.querySelector('[name="equipment"]').required=kind==='photo';document.querySelector('[name="conditions"]').required=kind==='photo';
  const numeric=$('submit-field').value==='reference_price'||catalog?.fields.find(f=>f.key===$('submit-field').value)?.numeric;
  $('submit-value').type=numeric?'number':'text';if(numeric){$('submit-value').step='any';$('submit-value').min='0.00001';}else{$('submit-value').removeAttribute('step');$('submit-value').removeAttribute('min');}
}
function openSubmit(model=null,kind='photo'){
  if(!catalog)return;
  if($('detail-dialog').open)$('detail-dialog').close();
  $('submission-form').reset();$('submit-kind').value=kind;if(model)$('submit-model').value=model.id;
  $('submit-message').textContent='';$('image-preview').classList.add('hidden');if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null;}
  updateForm();$('submission-dialog').showModal();
}
function readBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('图片读取失败'));reader.readAsDataURL(file);});}
async function submit(event){
  event.preventDefault();const button=$('submit-button');button.disabled=true;$('submit-message').textContent='正在提交…';
  try{
    const form=new FormData(event.target),payload=Object.fromEntries(form.entries());payload.consent=form.get('consent')==='on';
    if(payload.kind==='photo'){const file=$('photo-file').files[0];if(!file||file.size>5*1024*1024)throw new Error('请选择不超过5MiB的图片');payload.image_data=await readBase64(file);}
    if(payload.kind==='parameter'&&($('submit-field').value==='reference_price'||catalog.fields.find(f=>f.key===payload.field)?.numeric))payload.value=Number(payload.value);
    const session=await fetch('/api/session',{cache:'no-store'});if(!session.ok)throw new Error('无法取得投稿令牌，请刷新重试');
    const {token}=await session.json();const response=await fetch('/api/submissions',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(payload)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'提交失败');
    $('submit-message').textContent=`已收到，人工审核后展示。投稿编号：${result.id}`;
    $('submission-form').reset();updateForm();$('image-preview').classList.add('hidden');
  }catch(error){$('submit-message').textContent=error.message;}finally{button.disabled=false;}
}
for(const id of ['search','brand-filter','mag-filter','objective-filter','price-filter','ed-filter','sort'])$(id).addEventListener(id==='search'?'input':'change',()=>{if(catalog)applyFilters();});
$('previous').addEventListener('click',()=>{page--;renderRows();});$('next').addEventListener('click',()=>{page++;renderRows();});
for(const button of document.querySelectorAll('[data-close]'))button.addEventListener('click',()=>$(button.dataset.close).close());
for(const id of ['contribute-top','contribute-bottom','contribute-photo'])$(id).addEventListener('click',()=>openSubmit());
$('detail-submit').addEventListener('click',()=>openSubmit(selectedModel));$('submit-kind').addEventListener('change',updateForm);$('submit-field').addEventListener('change',updateForm);$('submission-form').addEventListener('submit',submit);
$('photo-file').addEventListener('change',()=>{if(previewUrl)URL.revokeObjectURL(previewUrl);const file=$('photo-file').files[0];if(file&&file.size<=5*1024*1024){previewUrl=URL.createObjectURL(file);$('image-preview').src=previewUrl;$('image-preview').classList.remove('hidden');}else{$('image-preview').classList.add('hidden');$('submit-message').textContent='请选择不超过5MiB的JPEG、PNG或WebP图片';}});
fetch('/api/catalog',{cache:'no-store'}).then(async response=>{if(!response.ok)throw new Error('读取目录失败');return response.json();}).then(data=>{
  catalog=data;$('model-count').textContent=data.models.length;$('price-count').textContent=data.models.filter(m=>m.reference_price!==null).length;
  fillSelect('brand-filter',[...new Set(data.models.map(m=>m.brand))].sort((a,b)=>a.localeCompare(b,'zh-CN')));
  fillSelect('mag-filter',[...new Set(data.models.map(m=>m.parameters.magnification).filter(v=>typeof v==='number'))].sort((a,b)=>a-b),'×');
  fillSelect('objective-filter',[...new Set(data.models.map(m=>m.parameters.objective_mm).filter(v=>typeof v==='number'))].sort((a,b)=>a-b),'mm');
  for(const model of [...data.models].sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'))){const option=el('option','',model.name);option.value=model.id;$('submit-model').append(option);}
  for(const f of [...data.fields.filter(f=>!['field_m','exit_pupil_mm'].includes(f.key)),{key:'reference_price',label:'参考入手价格(元)'}]){const option=el('option','',f.label);option.value=f.key;$('submit-field').append(option);}
  applyFilters();renderGallery();
}).catch(error=>{$('load-error').textContent=`${error.message}，请稍后刷新页面。`;$('load-error').classList.remove('hidden');$('result-count').textContent='目录暂不可用';});
