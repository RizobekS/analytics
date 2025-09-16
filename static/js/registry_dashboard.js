(function(){
const D = window.REG_DATA || {};
// KPI
document.getElementById('kpi-total').textContent = D.kpi?.total ?? '0';
document.getElementById('kpi-issued').textContent = D.kpi?.issued ?? '0';
document.getElementById('kpi-revoked').textContent = D.kpi?.revoked ?? '0';


const exists = (id)=> document.getElementById(id);
const bar = (id, labels, data)=> exists(id) && new ApexCharts(document.querySelector('#'+id), {
chart:{ type:'bar', height:320, toolbar:{show:false} },
series:[{ name:'Количество', data }], xaxis:{ categories: labels }, dataLabels:{enabled:false}
}).render();


const pie = (id, labels, data)=> exists(id) && new ApexCharts(document.querySelector('#'+id), {
chart:{ type:'pie', height:320 }, series:data, labels:labels, legend:{position:'bottom'}
}).render();


const area = (id, labels, data)=> exists(id) && new ApexCharts(document.querySelector('#'+id), {
chart:{ type:'area', height:320, toolbar:{show:false} },
series:[{ name:'Выдано', data }], xaxis:{ categories:labels, type:'category' }, dataLabels:{enabled:false}, stroke:{curve:'smooth'}
}).render();


// Prepare data
const toPairs = (arr, k, v)=> (arr||[]).map(o=> [o[k]||'—', o[v]||0]);
const s = toPairs(D.status, 'status', 'c');
bar('chartStatus', s.map(i=>i[0]), s.map(i=>i[1]));


const r = toPairs(D.region, 'horse__place_of_birth__name', 'c');
bar('chartRegion', r.map(i=>i[0]), r.map(i=>i[1]));


const b = toPairs(D.breed, 'horse__breed__name', 'c');
pie('chartBreed', b.map(i=>i[0]), b.map(i=>i[1]));


const d = (D.daily||[]).map(x=> [x.d, x.c]);
area('chartDaily', d.map(i=>i[0]), d.map(i=>i[1]));
})();
