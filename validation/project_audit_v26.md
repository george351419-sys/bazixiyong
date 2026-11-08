# v26 项目审查整改

日期：2026-11-07。政策：policy_v26_maintenance_and_provenance。

| 问题 | 已完成方案 |
|---|---|
| 保护动作借用他药效果 | 每个数值保护动作要求action_id、source_action_id、protection_ref。保护证据绑定药物身份、方法、目标、基线和原始作用记录，source_record必须存在于当前事实的treatment_allocations，原始药物、目标及有效药力须相符。结构保护另核对所保护record的药物身份。 |
| 零缺口丢失维护依赖 | 需求账保留保护依赖与原始治疗状态；零缺口但有已实现药效/保护依据的目标标记protection_required、required、handling=maintenance。不能走no_new_advice，须提供保护反事实。 |
| 不同方法自动互斥 | 不同治法默认均需覆盖。method_relation显式声明alternative、joint或conflict；alternative才建立choice_group，需同一需求来源及审核证据。joint保持共同覆盖，conflict同时进入路线时阻断。融合审核包内的关系证据须绑定事实和评估身份。 |
| 手工天数覆盖真实节气 | 实际solar_term_info始终保留；手工天数只覆盖chart.solar_term_day的司令参考。solar_term_override记录请求值、实际值和冲突，JSON与网页提示。调候仍使用实际节气。 |
| 独立审定漏掉排盘入口 | 支持birth_input案例，调用真实analyze_birth，固定truesun和sect，并核对原始/校正/节气参考时间、四柱、时间约定和当前节气，以及后续各层结果。发布验收要求至少有成功比较的出生入口正例，仍要求融合行动正例。 |
| 异常审定文件崩溃 | 读取后先验证顶层对象、案例及配置结构；非法顶层返回结构化失败，路径、JSON和预期字段错误均纳入报告。 |

## 保护证据合同

action.protection_ref须属于该目标protection_dependency.evidence_refs。对应registry记录包含route_id、target_id、remaining_without、action_id、source_action_id、gan/wuxing/precision、method、baseline_ref和source_record。source_record是当前事实原始治疗分配的完整记录，不能仅写一个自定义来源名。

## 治法关系合同

method_relation包含kind、group_id、非空evidence_refs。替代组内需求仍须同类型、同场景、同原始目标和同来源组合；方法必须不同。仅凭同一目标出现多种方法不再推断替代关系。审核包registry中的关系证据包含完整relation及facts_snapshot_id、assessment_snapshot_id。

## 出生信息独立案例

case使用birth_input或chart二选一。birth_input使用analyze_birth参数，必须显式提供truesun和sect；config放在case.config。成功出生案例除原有分层预期外，必须提供paipan_meta.八字、原始公历、公历、节气参考公历、time_convention和solar_term_info.current_jieqi_name。失败出生案例可使用expected.ok=false及stage等预期验证拒绝路径。案例仍须有独立来源及固定预期，不能使用本轮构造测试冒充金标准。

## 回归与冻结

新增tests/test_project_audit_v26.py六项测试，覆盖保护绑定正例及额外药物拒绝、维护需求、显式治法替代、手工天数与真实节气、异常文件、出生信息全链路比较。

旧tests/test_fusion_audit_fixes.py中“治法替代须选择一个”的正例已补明确method_relation及来源引用，以适配新的证据要求；仅更新该合同测试的登记哈希。冻结360盘及其原始预期和哈希不刷新。

真实独立审定数据尚未提供；生产评估依据的既有缺口继续阻断发布。

本轮验证结果：新增六项反例及完整回归通过，JavaScript语法和git diff空白检查通过。发布验收按预期返回失败：待判355/360、方向发布4、行动发布0；独立审定文件尚缺，出生入口及融合行动独立正例均为0。无冻结哈希或合同测试哈希错误。
