import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root=path.dirname(fileURLToPath(import.meta.url));
const analysisBytes=await fs.readFile(path.join(root,'analysis.json'));
const a=JSON.parse(analysisBytes.toString('utf8'));
const final=process.argv.includes('--final');
const q=JSON.parse(await fs.readFile(path.join(root,'quantity.json'),'utf8'));
const sourceHash=crypto.createHash('sha256').update(analysisBytes).digest('hex');
if(final && q.source_analysis_sha256!==sourceHash)throw new Error('Quantity model was not regenerated from this analysis.');
if(final && a.partial_data) throw new Error('Final workbook requires the full evaluable cohort.');
const outDir=final?path.resolve(root,'../../outputs/magpie-v2'):path.join(root,'workbook-preview');
await fs.mkdir(outDir,{recursive:true});
const wb=Workbook.create();
const sheets=['对比汇总','工程题记录','上下文和工具','任务占比','调用记录','用量与中断','同额度推算'].map(n=>wb.worksheets.add(n));
const [summary,core,context,mix,raw,usage,budget]=sheets;
const FONT='Arial';
const BLUE='#2563EB',ORANGE='#D97706',INK='#172033',GRAY='#64748B',DARK='#334155';
const num=v=>typeof v==='number'&&Number.isFinite(v)?v:null;
const na=v=>num(v)??'n.a.';
const byP=(rows,p)=>rows?.find(r=>r.provider===p)??{};
const pnames={go:'OpenCode Go',goat:'Command GOAT'};

function base(sheet,last='P100'){
  sheet.showGridLines=false;
  sheet.getRange(`A1:${last}`).format.font={name:FONT,size:10,color:INK};
  sheet.getRange(`A1:${last}`).format.verticalAlignment='center';
}
function title(sheet,text){sheet.getRange('A2').values=[[text]];sheet.getRange('A2').format.font={name:FONT,size:15,bold:true,color:INK};sheet.getRange('A2').format.rowHeight=27;}
function header(sheet,range){(typeof range==='string'?sheet.getRange(range):range).format={fill:DARK,font:{name:FONT,size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',rowHeight:24};}
function table(sheet,startRow,headers,rows,name,widths=[]){
  const n=Math.max(1,rows.length),cols=headers.length;
  sheet.getRangeByIndexes(startRow-1,0,1,cols).values=[headers];
  if(rows.length)sheet.getRangeByIndexes(startRow,0,rows.length,cols).values=rows;
  const range=sheet.getRangeByIndexes(startRow-1,0,n+1,cols);
  range.format.font={name:FONT,size:10,color:INK};range.format.rowHeight=21;
  const t=sheet.tables.add(range,true,name);t.showFilterButton=true;
  header(sheet,sheet.getRangeByIndexes(startRow-1,0,1,cols));
  widths.forEach((w,i)=>{sheet.getRangeByIndexes(0,i,startRow+n+1,1).format.columnWidth=w;});
  sheet.freezePanes.freezeRows(startRow);return t;
}
function fmtColumns(sheet,firstRow,lastRow,columns,format){
  for(const col of columns)sheet.getRangeByIndexes(firstRow-1,col,lastRow-firstRow+1,1).setNumberFormat(format);
}

base(summary,'P65');title(summary,'DeepSeek V4.1 Flash 套餐实测');summary.tabColor=DARK;
summary.getRange('A3').values=[[`2026-11-05 至 11-06  本机 Magpie  同题配对  ${a.partial_data?'采集中，仅预览':'完整可评估样本'}`]];summary.getRange('A3').format.font={name:FONT,size:10,color:GRAY,italic:true};
const g=byP(a.core?.summary,'go'),c=byP(a.core?.summary,'goat'),lg=byP(a.low_core?.summary,'go'),lc=byP(a.low_core?.summary,'goat');
const serialP=p=>a.baseline?.summary?.find(r=>r.provider===p&&r.phase==='serial')??{};
const sg=serialP('go'),sc=serialP('goat');
const requestsP=p=>byP(a.requests?.provider_totals,p);
const tr=a.tables?.tool_trials??[],ct=a.tables?.context_trials??[];
const avg=(rows,k)=>rows.length?rows.reduce((s,r)=>s+(Number(r[k])||0),0)/rows.length:null;
const metricRows=[
 ['high 首轮严格通过率',g.first_pass_macro,c.first_pass_macro,'比率'],
 ['high 首轮去框通过率',g.first_after_extraction_macro,c.first_after_extraction_macro,'比率'],
 ['high 反馈后严格通过率',g.solved_macro,c.solved_macro,'比率'],
 ['high 反馈后去框通过率',g.solved_after_extraction_macro,c.solved_after_extraction_macro,'比率'],
 ['high 每题实际请求等待均值',g.workflow_mean_seconds_macro,c.workflow_mean_seconds_macro,'秒'],
 ['low 首轮严格通过率',lg.first_pass_macro,lc.first_pass_macro,'比率'],
 ['low 首轮去框通过率',lg.first_after_extraction_macro,lc.first_after_extraction_macro,'比率'],
 ['low 反馈后去框通过率',lg.solved_after_extraction_macro,lc.solved_after_extraction_macro,'比率'],
 ['low 每题实际请求等待均值',lg.workflow_mean_seconds_macro,lc.workflow_mean_seconds_macro,'秒'],
 ['串行完整返回 p50',sg.total_seconds_p50,sc.total_seconds_p50,'秒'],
 ['串行完整返回 p90',sg.total_seconds_p90,sc.total_seconds_p90,'秒'],
 ['串行首个可见输出 p50',sg.first_visible_seconds_p50,sc.first_visible_seconds_p50,'秒'],
 ['长上下文完整 JSON 通过率',avg(ct.filter(r=>r.provider==='go'),'full_json_pass'),avg(ct.filter(r=>r.provider==='goat'),'full_json_pass'),'比率'],
 ['工具流程完成率',avg(tr.filter(r=>r.provider==='go'),'episode_success'),avg(tr.filter(r=>r.provider==='goat'),'episode_success'),'比率'],
 ['工具最终代码通过率',avg(tr.filter(r=>r.provider==='go'),'source_pass'),avg(tr.filter(r=>r.provider==='goat'),'source_pass'),'比率'],
 ['已记录终端请求',requestsP('go').n_terminal_requests,requestsP('goat').n_terminal_requests,'次'],
 ['有明确终止且有效载荷的请求',requestsP('go').complete_n,requestsP('goat').complete_n,'次'],
 ['未知 usage（含缺失终端）',requestsP('go').unknown_usage_including_missing_client_n,requestsP('goat').unknown_usage_including_missing_client_n,'次'],
];
summary.getRange('A5:D5').values=[['指标','OpenCode Go','Command GOAT','单位']];header(summary,'A5:D5');
summary.getRange(`A6:D${metricRows.length+5}`).values=metricRows.map(([label,x,y,unit])=>[label,na(x),na(y),unit]);
summary.getRange(`A6:D${metricRows.length+5}`).format.rowHeight=23;
metricRows.forEach((r,i)=>summary.getRange(`B${i+6}:C${i+6}`).setNumberFormat(r[3]==='比率'?'0.0%':r[3]==='次'?'#,##0':'0.0'));
summary.getRange('A1:A65').format.columnWidth=34;summary.getRange('B1:C65').format.columnWidth=17;summary.getRange('D1:D65').format.columnWidth=11;summary.getRange('E1:E65').format.columnWidth=3;summary.getRange('F1:P65').format.columnWidth=10;
summary.getRange('A26').values=[['去框分数仅去除完整的单个 Python 代码框；这是事后补充诊断。']];
summary.getRange('A27').values=[['严格分数、思考档位、并发档位和时段分别统计。']];
summary.getRange('A28').values=[['等待为模型请求耗时之和；原始失败、修复和采集器中断均另列。']];
summary.getRange('A29').values=[['用户报告另一台电脑可能同时运行 OpenCode；本机日志无法量化该跨设备共享负载。']];
summary.getRange('B6:C23').format.horizontalAlignment='center';summary.getRange('D6:D23').format.horizontalAlignment='center';
summary.getRange('A26:A29').format.font={name:FONT,size:10,color:GRAY};
const configs=[['Go high',g],['GOAT high',c],['Go low',lg],['GOAT low',lc]];
summary.getRange('A32:C36').values=[['配置','严格首轮通过率','去框首轮通过率'],...configs.map(([name,d])=>[name,num(d.first_pass_macro),num(d.first_after_extraction_macro)])];
summary.getRange('B33:C36').setNumberFormat('0.0%');header(summary,'A32:C32');
const qchart=summary.charts.add('bar',summary.getRange('A32:C36'));qchart.title='工程题首轮通过率';qchart.titleTextStyle.fontSize=12;qchart.titleTextStyle.typeface=FONT;qchart.setPosition('F5','P19');qchart.legend={position:'bottom',textStyle:{typeface:FONT,fontSize:10}};qchart.yAxis={numberFormatCode:'0%',numberFormatSourceLinked:false,textStyle:{typeface:FONT,fontSize:10}};
qchart.series.items[0].fill=BLUE;qchart.series.items[1].fill=ORANGE;
summary.getRange('A39:B43').values=[['配置','首轮请求平均耗时（秒）'],...configs.map(([name,d])=>[name,num(d.first_mean_seconds_macro)])];header(summary,'A39:B39');summary.getRange('B40:B43').setNumberFormat('0.0');
const tchart=summary.charts.add('bar',summary.getRange('A39:B43'));tchart.title='工程题首轮等待时间';tchart.titleTextStyle.fontSize=12;tchart.titleTextStyle.typeface=FONT;tchart.hasLegend=false;tchart.setPosition('F21','P35');tchart.yAxis={numberFormatCode:'0"s"',numberFormatSourceLinked:false,textStyle:{typeface:FONT,fontSize:10}};tchart.series.items[0].fill='#64748B';

const codeRows=[...(a.tables.core_trials??[]).map(r=>({...r,effort:'high'})),...(a.tables.low_core_trials??[]).map(r=>({...r,effort:'low'}))].sort((x,y)=>`${x.task_id}|${x.effort}|${x.repetition}|${x.provider}`.localeCompare(`${y.task_id}|${y.effort}|${y.repetition}|${y.provider}`));
base(core,`R${Math.max(20,codeRows.length+8)}`);title(core,'工程题逐次结果');core.getRange('A3').values=[['每行是一题一次试验；589 条验收断言不作为独立样本。']];
table(core,5,['题目','套餐','思考档','重复','首轮严格通过','首轮去框通过','反馈后严格通过','反馈后去框通过','首轮秒','修复秒','实际等待秒','修复次数','首轮失败类型','首轮思考 token','全部输出 token'],codeRows.map(r=>[r.task_id,pnames[r.provider],r.effort,r.repetition,r.first_pass,r.first_after_conservative_extraction_pass,r.solved,r.workflow_after_conservative_extraction_solved,r.first_seconds,r.repair_seconds,r.workflow_seconds,r.repair_attempted?1:0,r.first_failure_normalized??'',r.first_reasoning_tokens,r.workflow_output_tokens]),'EngineeringTrials',[26,20,10,8,16,16,18,18,12,12,14,10,22,18,18]);
fmtColumns(core,6,Math.max(6,codeRows.length+5),[8,9,10],'0.0');fmtColumns(core,6,Math.max(6,codeRows.length+5),[13,14],'#,##0');core.freezePanes.freezeColumns(2);

const contexts=[...(a.tables.context_summaries??[])].sort((x,y)=>parseInt(x.size_label,10)-parseInt(y.size_label,10)||x.provider.localeCompare(y.provider));
const tools=a.tables.tool_summaries??[];
base(context,'P65');title(context,'长上下文与工具流程');context.getRange('A3').values=[['上下文按预设长度分组，同时列出接口报告的实际输入 token。']];
table(context,5,['目标长度','套餐','数据集数','完整 JSON 通过率','字段通过率','实际输入均值','完整返回 p50秒','完整返回 p90秒','已完成响应数'],contexts.map(r=>[r.size_label,pnames[r.provider],r.n_datasets,r.full_json_pass_rate,r.complete_field_pass_rate,r.actual_input_tokens_mean,r.total_seconds_p50,r.total_seconds_p90,r.complete_n]),'ContextSummary',[14,20,12,21,16,20,22,22,18]);
fmtColumns(context,6,Math.max(6,contexts.length+5),[3,4],'0.0%');fmtColumns(context,6,Math.max(6,contexts.length+5),[5],'#,##0');fmtColumns(context,6,Math.max(6,contexts.length+5),[6,7],'0.0');
const toolStart=19;context.getRange('A17').values=[['工具题使用可读写的合成仓库；测试文件不可修改，最多 12 次模型响应。']];
table(context,toolStart,['仓库','套餐','流程数','最终代码通过率','有效完成率','平均模型轮数','平均工具调用数','工具错误数','流程等待 p50秒','达到轮数上限'],tools.map(r=>[r.repository_id,pnames[r.provider],r.n_episodes,r.source_pass_rate,r.episode_success_rate,r.turns_mean,r.n_episodes?r.tool_calls_sum/r.n_episodes:null,r.tool_errors_sum,r.total_seconds_p50,r.censored_n]),'ToolSummary',[27,20,12,20,17,20,20,16,23,20]);
fmtColumns(context,toolStart+1,Math.max(toolStart+1,toolStart+tools.length),[3,4],'0.0%');fmtColumns(context,toolStart+1,Math.max(toolStart+1,toolStart+tools.length),[5,6,8],'0.0');context.freezePanes.unfreeze();

base(mix,'N65');title(mix,'任务次数占比与有效完成效率');mix.getRange('A3').values=[['占比指任务次数；表内为严格格式工作流，实际失败和重试计时。']];
mix.getRange('A5:D5').values=[['类型','套餐','通过率','平均等待秒']];header(mix,'A5:D5');
const strata=a.tables.mix_strata??[];
const strataOrder=['code','context','tools'].flatMap(s=>['go','goat'].map(p=>strata.find(r=>r.stratum===s&&r.provider===p)??{stratum:s,provider:p,pass_rate:null,mean_seconds:null}));
mix.getRange('A6:D11').values=strataOrder.map(r=>[r.stratum,pnames[r.provider],num(r.pass_rate),num(r.mean_seconds)]);mix.getRange('C6:C11').setNumberFormat('0.0%');mix.getRange('D6:D11').setNumberFormat('0.0');
const grid=a.tables.mix_grid??[];const start=15;
mix.getRange('A14').values=[['有效完成数/分钟 = 加权通过率 ÷ 加权平均秒数 × 60。GOAT/Go >1 代表 GOAT 更高。']];
table(mix,start,['代码占比','上下文占比','工具占比','Go 加权通过率','Go 平均秒','Go 合格数/分','GOAT 加权通过率','GOAT 平均秒','GOAT 合格数/分','GOAT / Go'],grid.map(r=>[r.code_weight_pct/100,r.context_weight_pct/100,r.tools_weight_pct/100,null,null,null,null,null,null,null]),'WorkloadMixtures',[14,16,14,20,17,20,23,20,23,18]);
for(let i=0;i<grid.length;i++){
 const row=start+i+1;
 const available=strataOrder.every(r=>typeof r.pass_rate==='number'&&typeof r.mean_seconds==='number');
 if(!available)continue;
 mix.getRange(`D${row}:J${row}`).formulas=[[
  `=A${row}*$C$6+B${row}*$C$8+C${row}*$C$10`,
  `=A${row}*$D$6+B${row}*$D$8+C${row}*$D$10`,
  `=IF(E${row}=0,"n.a.",D${row}/E${row}*60)`,
  `=A${row}*$C$7+B${row}*$C$9+C${row}*$C$11`,
  `=A${row}*$D$7+B${row}*$D$9+C${row}*$D$11`,
  `=IF(H${row}=0,"n.a.",G${row}/H${row}*60)`,
  `=IF(F${row}=0,"n.a.",I${row}/F${row})`,
 ]];
}
fmtColumns(mix,start+1,start+Math.max(grid.length,1),[0,1,2,3,6],'0.0%');fmtColumns(mix,start+1,start+Math.max(grid.length,1),[4,7],'0.0');fmtColumns(mix,start+1,start+Math.max(grid.length,1),[5,8,9],'0.000');
mix.getRange('A33').values=[['各类正确率与等待都是本轮实测；任务组合仅为情景计算，不是未来承诺。']];mix.freezePanes.unfreeze();

const rawRows=a.tables.request_records??[];base(raw,`W${Math.max(20,rawRows.length+8)}`);title(raw,'全部被测请求记录');raw.getRange('A3').values=[['每行一条有客户端终端记录的调用；行政中断的缺失终端另见报告与 JSON。']];
table(raw,5,['开始时间（北京时间）','套餐','阶段','试验编号','思考档','标称并发/套餐','HTTP','完整响应','失败类型','首个可见秒','完整返回秒','输入 token','缓存 token','输出 token','思考 token','缓存命中率','usage 已知','等值估价 USD','价格时段','请求 ID','行政排除','排除原因'],rawRows.map(r=>[r.started?new Date(Date.parse(r.started)+8*3600*1000):null,pnames[r.provider],r.phase,r.trial_id,r.effort,r.concurrency_per_provider,r.status,r.complete,r.failure_class_normalized??'',r.first_visible_seconds,r.total_seconds,r.input_tokens,r.cached_tokens,r.output_tokens,r.reasoning_tokens,r.cache_fraction,r.usage_known,r.estimated_list_equivalent_usd,r.pricing_period,r.attempt_id,r.administratively_invalidated,r.administrative_reason??'']),'RequestRecords',[23,20,20,35,10,20,9,14,22,17,18,18,18,18,18,18,14,22,17,42,14,60]);
fmtColumns(raw,6,rawRows.length+5,[0],'mm-dd hh:mm:ss');raw.getRange(`A6:A${rawRows.length+5}`).format.horizontalAlignment='center';fmtColumns(raw,6,rawRows.length+5,[9,10],'0.00');fmtColumns(raw,6,rawRows.length+5,[11,12,13,14],'#,##0');fmtColumns(raw,6,rawRows.length+5,[15],'0.0%');fmtColumns(raw,6,rawRows.length+5,[17],'$0.000000');raw.freezePanes.freezeColumns(2);

base(usage,'K60');title(usage,'所有调用用量与采集中断');
usage.getRange('A3').values=[['用量覆盖已记录的原始调用，包括失败和行政排除；未知值不按零计算。']];
const usageMetrics=[
 ['已记录终端请求', 'n_terminal_requests','次'],
 ['有效完整响应','complete_n','次'],
 ['未知 usage（含缺失终端）','unknown_usage_including_missing_client_n','次'],
 ['行政中断后缺失客户端终端','administratively_resolved_missing_client_terminal_n','次'],
 ['行政排除的已返回请求','administratively_invalidated_client_terminal_n','次'],
 ['已知输入 token','input_tokens_known_sum','token'],
 ['已知缓存 token（已含于输入）','cached_tokens_known_sum','token'],
 ['已知输出 token（已含思考）','output_tokens_known_sum','token'],
 ['已知思考 token','reasoning_tokens_known_sum','token'],
 ['已知部分按公开价格等值估算','estimated_list_equivalent_usd_known_sum','USD'],
];
usage.getRange('A5:D5').values=[['指标','OpenCode Go','Command GOAT','单位']];header(usage,'A5:D5');
usage.getRange('A6:D15').values=usageMetrics.map(([label,key,unit])=>[label,na(requestsP('go')[key]),na(requestsP('goat')[key]),unit]);
usage.getRange('B6:C15').format.horizontalAlignment='center';usage.getRange('B6:C14').setNumberFormat('#,##0');usage.getRange('B15:C15').setNumberFormat('$0.000000');
usage.getRange('A17').values=[['金额是按用量与公布单价的估算，不是账单、实际扣费或剩余额度。']];
usage.getRange('A18').values=[['缺失客户端终端的两条请求：网关 499 与网关耗时仅供恢复核对。']];
const admin=a.tables.administratively_resolved_missing_client_attempts??[];
const adminHeaders=['套餐','阶段','试验编号','客户端 usage','客户端耗时','网关 HTTP','网关耗时秒','请求 ID'];
// Gateway data stays explicitly separate from absent client observations.
table(usage,21,adminHeaders,admin.map(r=>[pnames[r.provider],r.phase,r.trial_id,'未知','未知',r.gateway_status??null,r.gateway_elapsed_seconds??null,r.attempt_id]),'AdministrativeMissing',[38,20,36,16,16,16,23,44]);
usage.getRange('A27').values=[['所有原始记录保留；受本地采集器中断影响的整个试验对重新执行。']];
usage.getRange('A28').values=[['原 Go 首轮限制违规也保留，并另做删除整个替代试验对的敏感性分析。']];
usage.getRange('A30').values=[['公开额度与单价核验：2026-11-05；下月规则可能变化。']];
usage.getRange('A31').values=[['OpenCode Go: https://opencode.ai/v2/docs/console/go/']];
usage.getRange('A32').values=[['GOAT: https://commandcode.ai/docs/plans/goat']];
usage.getRange('A33').values=[['价格: https://commandcode.ai/docs/resources/pricing-limits']];
usage.getRange('A34').values=[['外部负载：用户报告另一台电脑可能同时运行 OpenCode；本机日志不能量化。']];
usage.getRange('A30:A34').format.font={name:FONT,size:9,color:GRAY};
usage.freezePanes.unfreeze();

base(budget,'L65');title(budget,'相同等值额度可完成的任务量（模型推算）');
budget.getRange('A3').values=[['依赖相同题目分布、token、缓存和修复行为；不是实际账单或保证任务数。']];
budget.getRange('A4:B4').values=[['等值额度 USD',q.allowance_usd]];budget.getRange('B4').setNumberFormat('$#,##0');budget.getRange('B4').format={fill:'#DBEAFE',font:{name:FONT,size:11,bold:true,color:BLUE}};
const endpoints={actual_strict:'实际严格流程',actual_conservative_extracted:'去框；全部实际修复成本',counterfactual_conservative:'自动去框假设（反事实）'};
const qr=q.tables.quantity_summaries.filter(r=>r.pricing==='uniform_off_peak');
table(budget,6,['套餐','思考档','口径','已知成本题次','观察题次','纳入题目数','每题等值成本 USD','同群体通过率','合格任务数/额度','95% 下界','95% 上界'],qr.map(r=>[pnames[r.provider],r.effort,endpoints[r.endpoint],r.eligible_workflows,r.observed_workflows,r.eligible_tasks,num(r.task_macro_cost_per_workflow),num(r.task_macro_success_rate),null,num(r.ci_low),num(r.ci_high)]),'QuantityModels',[20,10,35,18,14,14,23,20,23,20,20]);
for(let i=0;i<qr.length;i++)if(typeof qr[i].task_macro_cost_per_workflow==='number'&&qr[i].task_macro_cost_per_workflow>0){
 const row=7+i;budget.getRange(`I${row}`).formulas=[[`=$B$4*H${row}/G${row}`]];
}
fmtColumns(budget,7,6+qr.length,[6],'$0.000000');fmtColumns(budget,7,6+qr.length,[7],'0.0%');fmtColumns(budget,7,6+qr.length,[8,9,10],'#,##0');
budget.getRange('A21').values=[['统一按低峰价格重计已知 token；相同消耗按高峰价计算时任务量减半。']];
budget.getRange('A22').values=[['实际流程要求全成本已知；反事实按选中请求计价，纳入样本可能不同。']];
budget.getRange('A23').values=[['蓝色额度可调整；95% 区间固定对应原始 $100 额度，来自合同成组重采样。']];
const qp=q.tables.paired_quantity_ratios.filter(r=>r.pricing==='uniform_off_peak');
table(budget,26,['思考档','配对题目数','口径','配对题次','GOAT/Go 任务量比','95% 下界','95% 上界'],qp.map(r=>[r.effort,r.n_paired_tasks,endpoints[r.endpoint],r.n_paired_workflows,num(r.ratio_goat_over_go),num(r.ci_low),num(r.ci_high)]),'QuantityPairs',[20,10,35,18,23,14,23]);
fmtColumns(budget,27,26+qp.length,[4,5,6],'0.000');budget.freezePanes.unfreeze();

wb.recalculate();
const formulaChecks=[];
for(let i=0;i<qr.length;i++){
 if(qr[i].modeled_correct_workflows_per_allowance===null)continue;
 const actual=budget.getRange(`I${7+i}`).values[0][0],expected=qr[i].modeled_correct_workflows_per_allowance;
 if(typeof actual!=='number'||!Number.isFinite(actual)||Math.abs(actual-expected)>1e-7)throw new Error('Quantity formula mismatch '+i);
 formulaChecks.push({quantity_row:7+i,actual,expected});
}
if(strataOrder.every(r=>typeof r.pass_rate==='number'&&typeof r.mean_seconds==='number')){
 for(let i=0;i<grid.length;i++){
  const row=start+i+1,w=[grid[i].code_weight_pct/100,grid[i].context_weight_pct/100,grid[i].tools_weight_pct/100];
  const expected=[];
  for(const offset of [0,1]){
   const rate=w.reduce((s,x,j)=>s+x*strataOrder[j*2+offset].pass_rate,0);
   const seconds=w.reduce((s,x,j)=>s+x*strataOrder[j*2+offset].mean_seconds,0);
   expected.push(rate,seconds,rate/seconds*60);
  }
  expected.push(expected[2]>0?expected[5]/expected[2]:'n.a.');
  const actual=mix.getRange(`D${row}:J${row}`).values[0];
  if(actual.some((v,j)=>typeof expected[j]==='number'?(typeof v!=='number'||!Number.isFinite(v)||Math.abs(v-expected[j])>1e-9):v!==expected[j]))throw new Error('Mixture formula mismatch row '+row+': '+JSON.stringify({actual,expected}));
  formulaChecks.push({row,actual,expected});
 }
 // The final grid row is 100% code. Doubling only its Go wait must halve its correct/minute formula.
 const row=start+grid.length,old=mix.getRange('D6').values[0][0],before=mix.getRange(`F${row}`).values[0][0];
 mix.getRange('D6').values=[[old*2]];wb.recalculate();
 const after=mix.getRange(`F${row}`).values[0][0];
 if(typeof after!=='number'||!Number.isFinite(after)||Math.abs(after-before/2)>1e-9)throw new Error('Mixture recalculation sensitivity failed');
 mix.getRange('D6').values=[[old]];wb.recalculate();
 const restored=mix.getRange(`F${row}`).values[0][0];
 if(typeof restored!=='number'||!Number.isFinite(restored)||Math.abs(restored-before)>1e-9)throw new Error('Mixture restore failed');
 formulaChecks.push({sensitivity:'Go code wait doubled',before,after,restored:mix.getRange(`F${row}`).values[0][0]});
}
await fs.writeFile(path.join(root,'workbook-formula-checks.json'),JSON.stringify(formulaChecks,null,2));
const inspect=await wb.inspect({kind:'table',range:'对比汇总!A5:D23',include:'values,formulas',tableMaxRows:20,tableMaxCols:4,maxChars:5000});
await fs.writeFile(path.join(root,'workbook-inspect.txt'),inspect.ndjson);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'final formula error scan',maxChars:4000});
await fs.writeFile(path.join(root,'workbook-errors.txt'),errors.ndjson);
const previewDir=path.join(root,'workbook-previews');await fs.mkdir(previewDir,{recursive:true});
for(const [sheet,range] of [[summary,'A1:P44'],[core,'A1:O18'],[context,'A1:J27'],[mix,'A1:J33'],[raw,'A1:L16'],[usage,'A1:H34'],[budget,'A1:K35']]){
 const image=await wb.render({sheetName:sheet.name,range,scale:1.5,format:'png'});
 await fs.writeFile(path.join(previewDir,`${sheet.name}.png`),new Uint8Array(await image.arrayBuffer()));
}
if(final){const blob=await SpreadsheetFile.exportXlsx(wb);await blob.save(path.join(outDir,'DeepSeek套餐扩展实测.xlsx'));}
console.log(JSON.stringify({final,partial:a.partial_data,worksheets:sheets.map(s=>s.name),raw_requests:rawRows.length,core_trials:codeRows.length,output_dir:outDir}));
