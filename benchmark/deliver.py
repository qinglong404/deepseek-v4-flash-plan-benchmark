"""Publish locally measured data; never calls a model or reads API credentials."""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAMES = {'go': 'OpenCode Go', 'goat': 'Command GOAT'}


def f(x, digits=1):
    return '未知/不适用' if x is None else f'{x:,.{digits}f}'


def pct(x):
    return '未知/不适用' if x is None else f'{100*x:.1f}%'


def yes(x):
    return '未知' if x is None else ('通过' if x else '未通过')


def table(headers, rows):
    def cell(x):
        return str(x).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(map(cell, headers)) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(map(cell, r)) + ' |' for r in rows])


def ci(m, rate=False):
    fmt = pct if rate else lambda x: f(x, 3)
    if m.get('estimate') is None:
        return '不可估计；' + str(m.get('estimate_state', '数据不足'))
    if m.get('ci_low') is None:
        return fmt(m['estimate']) + '；没有可用的无条件 95% 区间'
    return f"{fmt(m['estimate'])} [{fmt(m['ci_low'])}, {fmt(m['ci_high'])}]"


def demote_headings(markdown):
    return '\n'.join(
        ('#' + line) if line.startswith('#') else line
        for line in markdown.splitlines()
    )


def make_report(a, q, decision, trajectory=None):
    T = a['tables']
    calls = T['request_records']
    totals = {r['provider']: r for r in a['requests']['provider_totals']}
    start = min(r['started'] for r in calls)
    end = max(r['ended'] for r in calls)
    raw_n = len(calls) + len(a['requests'].get('raw_unreturned_attempts', []))
    parts = ['# DeepSeek V4.1 Flash：两套餐复杂实测与决策数据',
             f"测试窗口：{start} 至 {end}（北京时间）。本轮共 {raw_n} 次启动记录、{len(calls)} 条客户端终端记录。",
             '**范围：这台机器现有网络、现有 Magpie、标准 Flash 路由。结果是当前端到端使用体验，不是底模能力排行榜。**',
             demote_headings(decision),
             '## 样本与判断口径',
             table(['层次', '每套餐样本', '要回答的问题'], [
                 ['复杂代码 high', '12 合同 × 3 次 = 36 题次', '边界行为正确性、格式遵循、一次反馈后的恢复'],
                 ['复杂代码 low（后加对照）', '同 12 合同 × 2 次 = 24 题次', '减少思考时是否更实用；与 high 分开分析'],
                 ['长上下文', '4 个预设长度 × 3 个数据种子 = 12 组', '覆盖、冲突、删除记录后的跨记录推理与精确 JSON'],
                 ['多文件工具', '2 个合成仓库 × 3 次 = 6 个流程', '读文件、修复、运行测试和结束整个流程'],
                 ['短任务与并发', '12 次串行 + 并发 1/2/4 各 2 批共 14 次', '响应分布、首个可见输出、并行批次吞吐']]),
             'high 是预先冻结主实验。low 和去代码框诊断是观察到早期结果后增加的补充分析，均单列。重复题次用于看稳定性；589 条代码断言和 102 条仓库断言不当作独立样本。',
             '严格通过要求原始回答直接满足输出与执行合同。去框通过只允许删除覆盖整条回答的单个 Python/py/无语言代码框，再用同一隔离验收器检查；它不允许修改算法、选择多个代码块或删除解释文字。执行限制仍适用，因而它不是无限制的算法质量分数。实际修复、时间和用量都保留。',
             '## 四种配置：正确率、等待和思考量',
             table(['配置', '题次/合同', '首轮严格', '首轮去框', '反馈后严格', '反馈后去框', '首轮均秒', '实际流程均秒', '首轮思考 token 均值'], [
                 [NAMES[r['provider']]+' '+r['effort'], f"{r['n_first_trials']}/{r['n_tasks']}",
                  pct(r['strict_first_pass_macro']), pct(r['after_extraction_first_pass_macro']),
                  pct(r['strict_solved_macro']), pct(r['after_extraction_solved_macro']),
                  f(r['first_seconds_mean']), f(r['workflow_seconds_mean']), f(r['first_reasoning_tokens_mean'], 0)]
                 for r in T['code_configurations']]),
             '均值先在同一合同内平均，再让 12 个合同等权。实际流程等待是模型请求耗时之和，包含失败与必要的一次反馈修复；不包括本地验收器运行时间，也不是人工从打开任务到验收的总工时。',
             '![四配置正确率与等待](07-effort-strata.png)',
             '## high 的配对不确定性与单题敏感性']
    metric_names = {
        'first_pass_difference_goat_minus_go': ('首轮严格通过率差，GOAT−Go', True),
        'solved_difference_goat_minus_go': ('反馈后严格通过率差，GOAT−Go', True),
        'first_correct_latency_ratio_goat_over_go': ('首轮均正确时耗时比 GOAT/Go', False),
        'workflow_correct_latency_ratio_goat_over_go': ('流程均完成时耗时比 GOAT/Go', False),
        'useful_throughput_ratio_goat_over_go': ('严格有效完成效率比 GOAT/Go', False),
    }
    parts.append(table(['指标', '估计 [探索性 95% 区间]', '合同数/配对题次'], [
        [label, ci(a['core']['metrics'][key], rate),
         str(a['core']['metrics'][key].get('n_clusters'))+'/'+str(a['core']['metrics'][key].get('n_pairs'))]
        for key, (label, rate) in metric_names.items()]))
    secondary_names = {
        'first_after_extraction_difference_goat_minus_go': ('首轮去框检查通过率差，GOAT−Go', True),
        'solved_after_extraction_difference_goat_minus_go': ('修复后去框检查通过率差，GOAT−Go', True),
        'first_source_correct_latency_ratio_goat_over_go': ('首轮去框均通过时耗时比 GOAT/Go', False),
        'auto_strip_useful_throughput_ratio_goat_over_go': ('假设自动去框的完成效率比 GOAT/Go', False),
    }
    parts.append(table(['事后补充指标', '估计 [探索性 95% 区间]', '合同数/配对题次'], [
        [label, ci(a['core']['secondary_metrics'][key], rate),
         str(a['core']['secondary_metrics'][key].get('n_clusters'))+'/'+str(a['core']['secondary_metrics'][key].get('n_pairs'))]
        for key, (label, rate) in secondary_names.items() if key in a['core']['secondary_metrics']]))
    loo = T['core_leave_one_task_out']
    parts.append(table(['逐一删除合同', '严格完成效率比 GOAT/Go'], [[r['excluded_task'],f(r['ratio_goat_over_go'],3)] for r in loo]))
    sensitivity = a['administrative_recovery'].get('sensitivity_drop_recovered_pair', {})
    sm = sensitivity.get('metrics', {}).get('useful_throughput_ratio_goat_over_go', {})
    parts += [f"删除受采集器中断影响后重做的整个试验对：配对数 {sensitivity.get('paired_workflows')}，严格完成效率比 {ci(sm)}。原中断前 Go 的限制违规结果仍在原始记录与单独表中。",
              f"区间使用固定种子、{a['bootstrap_draws']:,} 次整个合同的成组重采样。通过率差大于 0 偏向 GOAT；耗时比大于 1 偏向 Go；有效完成效率比大于 1 偏向 GOAT。三种方向不能混用。",
              '这些区间只反映本题库内重复与合同差异。12 个合成合同不足以代表所有代码工作；全对时经验区间可能退化为零宽，不证明未来零错误或两者等价。只比较均正确任务的速度也会筛掉困难失败题，应与完成率、失败时间一起读。',
              '![逐题通过率](01-code-quality.png)',
              '![正确任务的配对耗时](03-paired-correct-latency.png)',
              '## 每道复杂代码题的重复结果']
    for effort, tab in [('high','core_tasks'),('low','low_core_tasks')]:
        parts.append('### '+effort)
        parts.append(table(['合同', '套餐', '题次', '首轮严格', '首轮去框', '反馈后去框', '流程均秒', '修复次数'], [
            [r['task_id'], NAMES[r['provider']], r['n_first_graded'], pct(r['first_pass_rate']),
             pct(r['first_after_extraction_pass_rate']), pct(r['solved_after_extraction_rate']),
             f(r['workflow_seconds_mean']), r['repair_attempts']] for r in T[tab]]))
    failures = collections.Counter()
    for effort, tab in [('high','core_failures'),('low','low_core_failures')]:
        for r in T[tab]:
            failures[(effort,NAMES[r['provider']],r['stage'],r['normalized'])] += r['count']
    parts += ['## 失败类型：不把格式和运行限制说成算法错误',
              table(['思考档','套餐','阶段','归类','次数'], [list(k)+[v] for k,v in sorted(failures.items())]),
              'format 表示完整代码框等输出合同问题；restriction 表示导入、名称或属性等运行限制；semantic 才是验收行为不符合预期。限制拒绝并未证明内部算法错误。提示已说明 Python 3.12、导入白名单、禁用 IO 和资源边界，但没有逐条说明 AST 对双下划线属性的禁用，属于题库执行合同的局限。',
              '原始失败标签、规范化标签、每次反馈和去框后检查均在数据与证据包中。HTTP 200 本身不等于完成；完整流需要有效载荷、有效终止原因和 [DONE]。',
              '## 长上下文：实际输入长度、正确性与等待',
              table(['预设组','套餐','实际输入 token 均值','组数','完整 JSON 通过','字段检查通过','p50 秒','p90 秒'], [
                  [r['size_label'],NAMES[r['provider']],f(r['actual_input_tokens_mean'],0),r['n_datasets'],
                   f"{r['full_json_passed']}/{r['n_datasets']}",pct(r['complete_field_pass_rate']),f(r['total_seconds_p50']),f(r['total_seconds_p90'])]
                  for r in sorted(T['context_summaries'],key=lambda r:(int(r['size_label'][:-1]),r['provider']))]),
              '每组有 9 个精确字段，包含版本覆盖、删除、干扰 ID 和跨记录计算。全部字段同时正确才算该组通过。字段相关，不能把 108 个字段当作 108 个独立样本。预设组保持原标签，实际 token 由接口报告；没有测试 1M 上下文边界。']
    context_bad=[r for r in T['context_fields'] if not r['complete_field_pass']]
    parts.append(table(['未通过字段所在组','套餐','字段','响应完整'],[[r['trial_id'],NAMES[r['provider']],r['field'],yes(r['response_complete'])] for r in context_bad]) if context_bad else '本轮所有上下文字段均通过。')
    parts += ['![上下文长度与表现](04-context-scaling.png)',
              '## 多文件工具流程',
              table(['仓库','套餐','流程数','最终代码通过','完整流程成功','平均响应轮数','平均工具调用','工具错误','p50 秒','轮数到顶'], [
                  [r['repository_id'],NAMES[r['provider']],r['n_episodes'],pct(r['source_pass_rate']),pct(r['episode_success_rate']),
                   f(r['turns_mean']),f(r['tool_calls_sum']/r['n_episodes']),r['tool_errors_sum'],f(r['total_seconds_p50']),r['censored_n']]
                  for r in T['tool_summaries']]),
              '仓库一覆盖库存事务、幂等和状态回滚；仓库二覆盖配置叠加、来源跟踪和缺陷修复。模型能列目录、读文件、写指定源文件和跑固定测试；不能改测试或任意执行 shell。每流程最多 12 次模型响应，达到上限仍保留最终代码检查；“代码通过”和“模型正常结束整个流程”分别统计。仅两个仓库，不能推出大型真实项目的普遍成功率。',
              '## 简单任务、首个可见输出与并发',
              table(['阶段','每套餐并发','套餐','请求数','夹具通过','首个可见 p50 秒','完整 p50 秒','完整 p90 秒'], [
                  [r['phase'],r['concurrency_per_provider'],NAMES[r['provider']],r['n_requests'],
                   f"{r['fixture_passed']}/{r['n_requests']}",f(r['first_visible_seconds_p50']),f(r['total_seconds_p50']),f(r['total_seconds_p90'])]
                  for r in T['baseline_summaries']]),
              table(['串行配对指标 GOAT/Go','估计 [95% 区间]','Go 更快/GOAT 更快'],[
                  [key,ci(r),str(r['go_wins'])+'/'+str(r['goat_wins'])] for key,r in a['baseline']['serial_metrics'].items() if key.endswith('all_terminal')]),
              '首个可见输出排除思考正文与 keepalive，只计最终正文或工具调用的首个非空增量；首事件可能只是思考，另存原始数据。串行指每套餐一个流，一对套餐共享本机网络；并发 4 则最多每套餐 4 流，共享链路最多 8 条被测流。并发只有每档两批，作描述性测量，不宣称测出了持续容量上限。',
              '![并发批次](05-matched-concurrency.png)',
              '![延迟分布](02-latency-distributions.png)',
              '## 工具轨迹补充：测试通过后还在等待什么',
              table(['仓库题次','套餐','写文件数','测试通过/失败次数','首次工具测试通过累计秒','首次通过后模型等待秒','最终代码'],[
                  [r['trial_id'],NAMES[r['provider']],r['write_file_calls_n'],str(r['run_tests_passed_n'])+'/'+str(r['run_tests_failed_n']),
                   f(r['response_wait_until_first_passed_test_seconds']),f(r['response_wait_after_first_passed_test_seconds']),yes(r['source_pass'])]
                  for r in (trajectory or {}).get('episodes',[]) if r['record_state']=='recorded_terminal']),
              '这是事后轨迹诊断。累计时间按发出对应工具调用的那次完整模型响应计入；不是精确工具调用首字时刻，也不含工具执行。配置仓库的全部 run_tests 调用均通过，首次通过后仍有模型响应和进一步工具操作；不能把这些额外等待描述为失败测试后的修复，也不直接断言它们毫无作用。',
              '## 量：公开额度相同，完成同一工作实际消耗可能不同',
              '2026-11-05 核验：基础月费均为 $10，GOAT 另列支付手续费；只使用标准 DeepSeek V4.1 Flash，两边月度等值额度均为 $100，5 小时/周窗口均对应 $20/$50。[OpenCode Go](https://opencode.ai/v2/docs/console/go/)、[GOAT 套餐](https://commandcode.ai/docs/plans/goat)、[GOAT 窗口说明](https://commandcode.ai/docs/resources/usage-limits)。这是模型使用价值，不是现金返还。混用模型按各模型占用比例共享池，下月应以续费时规则为准。',
              '标准版每百万 token 的新输入/缓存输入/输出：低峰 $0.15/$0.003/$0.60，高峰 $0.30/$0.006/$1.20。高峰是北京时间工作日 09–12、14–18；输出已包含思考，不能另加一次思考费用。缓存是输入的子集，不能同时按全额新输入重复计算。[OpenCode 价格表](https://opencode.ai/v2/docs/console/go/)、[Command 价格表](https://commandcode.ai/docs/resources/pricing-limits)。',
              table(['已知部分；含失败与行政排除','OpenCode Go','Command GOAT'],[
                  [label, f(totals['go'].get(key),digits), f(totals['goat'].get(key),digits)] for label,key,digits in [
                      ('客户端终端请求数','n_terminal_requests',0),('完整响应数','complete_n',0),
                      ('未知 usage，含缺失终端','unknown_usage_including_missing_client_n',0),
                      ('输入 token','input_tokens_known_sum',0),('其中缓存 token','cached_tokens_known_sum',0),
                      ('输出 token，含思考','output_tokens_known_sum',0),('其中思考 token','reasoning_tokens_known_sum',0),
                      ('按公开价格的等值估算 USD','estimated_list_equivalent_usd_known_sum',6)]]),
              '本轮没有刻意耗尽套餐，也没有观测满月可用量或精确扣费。缺失 usage 的请求费用未知，上表不是完整账单。具体配置的 $100 合格任务数推算见 quantity.json 与预算表；它依赖相同任务分布、公开单价及缓存模式，不是承诺。']
    if q:
        endpoints={'actual_strict':'实际严格流程','actual_conservative_extracted':'去框后通过；保留全部实际修复成本','counterfactual_conservative':'假设客户端自动去框；反事实'}
        qr=[r for r in q['tables']['quantity_summaries'] if r['pricing']=='uniform_off_peak']
        parts.append(table(['配置','计算口径','已知成本题次/观察题次','纳入合同','每题等值成本 USD','每 $100 合格任务估算 [95% 区间]'],[
            [NAMES[r['provider']]+' '+r['effort'],endpoints[r['endpoint']],
             str(r['eligible_workflows'])+'/'+str(r['observed_workflows']),r['eligible_tasks'],
             f(r['task_macro_cost_per_workflow'],6),
             f(r['modeled_correct_workflows_per_allowance'],0)+' ['+f(r['ci_low'],0)+', '+f(r['ci_high'],0)+']'] for r in qr]))
        parts.append('上表统一按低峰单价重计已知 token 与缓存；如果 token、命中和修复模式相同，改按高峰价格时可用任务数减半。只纳入整个流程成本均已知的题次，两套餐可纳入的子集可能不同。公平的跨套餐比值另用两边都已知成本的相同题次配对，见下面。')
        parts.append(table(['思考档','计算口径','配对合同/题次','同额预算的 GOAT/Go 合格任务数比 [95% 区间]'],[
            [r['effort'],endpoints[r['endpoint']],str(r['n_paired_tasks'])+'/'+str(r['n_paired_workflows']),
             f(r['ratio_goat_over_go'],3)+' ['+f(r['ci_low'],3)+', '+f(r['ci_high'],3)+']']
            for r in q['tables']['paired_quantity_ratios'] if r['pricing']=='uniform_off_peak']))
        parts.append('预算推算的分母、未知工作流数量、统一高低峰重计价与假设自动去框结果都独立保存，不能把未知成本当零或把推算当实际额外跑出的任务。')
    parts += ['## 一个便于决策的指标：每分钟有效完成数',
              '**有效完成数/分钟 = 60 × 成功任务数 ÷ 实际模型请求等待秒数之和。** 失败等待和必要修复都占分母；相对于 Go 的指数为该效率比 ×100。代码主指标用严格工作流；去框后假设能提前结束的结果只作单独的反事实分析。',
              '下面组合权重是“任务次数占比”，不是时间占比、token 占比或账单占比。每类先计算各自通过率与均时，再按任务占比组合：60×Σ(占比×通过率)/Σ(占比×均秒)。Excel 保留可重算公式。',
              table(['代码/上下文/工具 次数占比','Go 合格数/分','GOAT 合格数/分','GOAT 指数，Go=100'], [
                  [f"{r['code_weight_pct']}/{r['context_weight_pct']}/{r['tools_weight_pct']}",
                   f(r['go_correct_tasks_per_minute'],3),f(r['goat_correct_tasks_per_minute'],3),
                   f(None if r['throughput_ratio_goat_over_go'] is None else 100*r['throughput_ratio_goat_over_go'],1)] for r in T['mix_grid']]),
              '这是情景计算，没有声称对所有用户存在唯一加权总冠军；也没有把不同任务的断言数当权重。去框反事实组合另在 CSV/JSON 中，方便看格式问题对实际客户端流程的影响。',
              '![任务组合敏感性](06-workload-mix-sensitivity.png)',
              '## 采集中断、环境与结果边界',
              '本地原 high 采集器在 18:45:36 收到 SIGTERM，退出码 143，发起者未知。两条请求缺失客户端终端记录，网关对应 499；不能把它们算成套餐故障，也不能把网关零 token 字段当成已测零用量。整个受影响试验对按相同题目与参数重做。另一个原已返回 Go 首轮因双下划线属性限制未通过，原评分与用量保留；主配对排除这三个明确 attempt ID，并报告删除替代整对的敏感性。',
              table(['套餐','阶段','题次','客户端用量/耗时','网关状态/耗时（独立证据）'],[
                  [NAMES[r['provider']],r['phase'],r['trial_id'],'未知',str(r['gateway_status'])+'/'+f(r['gateway_elapsed_seconds'],3)+' 秒']
                  for r in T['administratively_resolved_missing_client_attempts']]),
              '因此完整指计划可评估队列在注明配对替换后完成；并不表示每个原始请求都获得最终答案。原始启动、终端、排除清单和配对重做记录全部保留。',
              '模型路由固定为 `opencode-go/deepseek-v4.1-flash` 与 `commandcode-plan/deepseek/deepseek-v4.1-flash`；没有 Fast 变体或自动跨套餐回退。温度 0、输出上限 65,536。相同 high/low 请求标签不保证上游内部思考预算完全相同。',
              '同题在同一批次近同时请求，代码每套餐最多两条被测流。测试保留本机原有后台使用，不停止其他应用；background-load.json 只聚合可见的已落盘同模型后台记录，不能据此建立速度变化的因果关系。',
              '用户在采集中途补充：另一台电脑可能同时运行其他 OpenCode 任务，因此 OpenCode 可能承受跨设备、共享账号的并发与额度竞争。本机 Magpie 日志看不到另一台机器的请求数、token、重叠时长或剩余滚动额度，不能把这些负载伪造成精确观测；它作为外部负载敏感性保留。若 OpenCode 在此背景下仍保持同等或更高质量调整吞吐，其优势方向更可信；若只是 GOAT 速度领先，则对速度归因应更保守。',
              '本轮主要观察低峰时段。前轮高峰只有 6 个短任务配对，这轮有 12 个；二者常规速度方向不同，说明不能用一个时段代表全月，但也不能将方向变化直接归因于高低峰、排队或网络中的某一个因素。前轮 50 调用没有混入这轮置信区间或指数，严格评分口径也不同。',
              '模型生成的代码在 bwrap 新文件系统、网络与 PID 命名空间运行，不可访问用户目录、配置或凭据；15 秒 CPU、20 秒验收墙钟、768 MiB 内存，Python 3.12.3。独立审查复验全部参考实现、故意错误实现及 400 个额外随机 oracle 案例，仍不能证明题库覆盖所有真实缺陷。',
              '单次响应应用门限为 600 秒，建立响应后可关闭套接字；异常的响应头前持续零碎传输可能超过该门限，已通过本地网络试验记录为采集器边界。因此不把这个门限描述成所有路径上的严格绝对硬截止。',
              'low 在 high 之后测试，思考强度、顺序、负载与缓存可能混杂；它是实用配置对照，不能当成随机化因果实验。没有修改套餐、支付、网络代理或真实项目，也没有自动取消任何订阅。',
              '## 文件与复核',
              '- `DeepSeek套餐扩展实测.xlsx`：汇总、逐题、上下文/工具、任务组合公式、调用记录、用量与中断、同额度推算。',
              '- `analysis.json`、`quantity.json`：完整统计定义和结果；`tables/` 是可筛选 CSV，每个表保持字段原名。',
              '- `magpie-v2-evidence.zip`：冻结题库、脚本、原始最终答案、工具轨迹、每次评分、提示哈希、负对照、审查及恢复证据；没有 API 密钥和思考正文。',
              '- `SHA256SUMS.json`：交付文件哈希。复算分析不发网络请求；重新执行采集脚本会消耗现有套餐用量。',
              f"分析生成时间：{a['generated_at']}。本报告由本轮数据生成，决策评述另经人工逐项核对。"]
    return '\n\n'.join(parts)+'\n'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    analysis_bytes=(ROOT/'analysis.json').read_bytes()
    a=json.loads(analysis_bytes)
    if a['partial_data'] and not args.preview:
        raise SystemExit('Refusing final publication while planned evaluable data are incomplete.')
    q=json.loads((ROOT/'quantity.json').read_text()) if (ROOT/'quantity.json').exists() else None
    if not args.preview and (not q or q['source_analysis_sha256']!=hashlib.sha256(analysis_bytes).hexdigest()):
        raise SystemExit('Final requires quantity model from the same analysis snapshot.')
    trajectory=json.loads((ROOT/'tool-trajectory.json').read_text()) if (ROOT/'tool-trajectory.json').exists() else None
    if not args.preview and (not trajectory or trajectory['source_sha256']!=hashlib.sha256((ROOT/'tool-results.jsonl').read_bytes()).hexdigest()):
        raise SystemExit('Final requires trajectory from current tool records.')
    decision_path=ROOT/'decision.md'
    if not args.preview and not decision_path.exists():
        raise SystemExit('Final requires manually reviewed decision.md.')
    decision=decision_path.read_text() if decision_path.exists() else '> 数据采集中，决策评述待完整结果后写入。'
    out=ROOT/'report-preview' if args.preview else ROOT.parent.parent/'outputs/magpie-v2'
    out.mkdir(parents=True,exist_ok=True)
    (out/'DeepSeek套餐扩展实测报告.md').write_text(make_report(a,q,decision,trajectory))
    for name in ['analysis.json','analysis-summary.txt','quantity.json','QUANTITY_README.md','ANALYSIS_README.md','background-load.json','historical-hour-profile.json','external-load-observation.json','tool-trajectory.json']:
        if (ROOT/name).exists():shutil.copy2(ROOT/name,out/name)
    csv_dir=out/'tables';csv_dir.mkdir(exist_ok=True)
    for name,rows in list(a['tables'].items())+([('quantity_'+k,v) for k,v in q['tables'].items()] if q else [])+([('tool_trajectory_episodes',trajectory['episodes']),('tool_trajectory_summaries',trajectory['summaries'])] if trajectory else []):
        keys=list(dict.fromkeys(key for row in rows for key in row))
        if not keys:continue
        with (csv_dir/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as file:
            writer=csv.DictWriter(file,fieldnames=keys);writer.writeheader();writer.writerows(rows)
    print(json.dumps({'preview':args.preview,'out':str(out),'terminal_requests':len(a['tables']['request_records'])},ensure_ascii=False))


if __name__=='__main__':main()
