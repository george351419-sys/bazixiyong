# v28 审查问题与实施记录

日期：2026-11-07。政策：policy_v28_applicability_monitoring_dose；药效合同：effects_v7_prediction_monitoring_states。

| 问题 | 对应方案与实施 |
|---|---|
| 假前提路线混作未知，阻塞合格候选 | 路线验证先评估当前执行前提。明确为假时result=rejected、applicability=not_applicable，跳过药效和资源核账，不制造级联缺口；未知和非法条件仍按证据缺口阻断。延期条件不被误当成立即执行前提。 |
| 预测监测需要虚构处方动作 | monitor_results中的计划监测使用application_ids关联已核验的实际投用；不要求监测目标有动作，反而禁止为其附加动作或dose_plan。资源只对实际投用扣减，监测不重复扣账。 |
| 保护路线可发布非法剂量 | 非计划效果不得携带dose_plan。组装阶段再次按执行状态筛选；保护和等待不输出新增剂量或预测剂量。已有药效比例仅保留为observed_relief_ratio，不作为执行剂量。 |

## 状态与覆盖

已知不适用的路线保留在诊断结果中，failed_rules给出假条件；missing_evidence为空、evaluation_skipped=true，不参与可行候选选择。只有真实缺证据才进入unknown。未参与当前路线的goal_results附加记录不作为执行前提，条件检查针对当前目标、监测与实际动作。

## 监测合同

计划监测仍须有同基线的逐目标药效证据，initial_demand=0，relief_feasible=0；projected_aggravation与projected_remaining按数值恒等式核验。监测状态为satisfied或aggravated，后者仍需要既有政策授权，不自动允许副作用。

application_ids必须为非空、去重的投用编号列表，每个编号均能在该路线的已核验资源分配中找到。完整干预/药效审核快照覆盖该关联。监测在评估输出中标记is_monitor=true，最终positions只由实际动作生成。含新计划干预的路线不能用历史已实现观察替代预测监测。

## 剂量合同

仅计划干预允许dose_plan，仍核验数量、上限、单位和基线。非计划效果中残留的计划字段返回unexpected_dose_plan，防止把历史作用当作新投用。保护剂量若未来需要单独发布，应另有经审定的维护剂量合同；本轮不会从已有药力或覆盖率推断。

## 测试与冻结

新增tests/test_project_audit_v28.py四项反例：假前提候选不阻塞合格路线；未知仍阻断且延期不误排除；真实投用关联监测及无效关联拒绝；保护路线无计划剂量、非法残留剂量拒绝。

旧合同测试的必要适配：v23假条件改为检查rejected的failed_rules；v26保护正例清除转换状态前的计划剂量；fusion_audit_fixes中已实现效果正例同样清除旧计划字段，继续验证错误增加动作的拒绝。上述文件哈希明确登记更新，360盘fixture、原始预期与数据哈希不刷新。

真实独立审定数据与生产评估器依据仍待补齐；合同回归通过不代表已具备生产发布条件。

本轮验证结果：新增4项针对性测试和完整回归通过；JavaScript语法与git diff空白检查通过。发布验收按预期失败，待判355/360，方向发布4，行动发布0，独立审定数据仍缺失。冻结数据及合同测试哈希无错误。
