# v29 项目整改与审核合同

日期：2026-11-07。政策版本：policy_v29_counterfactual_maintenance_resolution；需求合同：needs_v7_reviewed_maintenance_resolution。

| 检查问题 | 解决方案与完成范围 |
|---|---|
| 气候干预基线失效仍返回已评估 | climate_intervention、climate_removal、prepare_fusion_context统一检查结构、快照及能量来源。失效即返回unknown，不输出可信药效。结果绑定完整模型哈希、assessment_snapshot_id、规范化delta及scenario_id，移除另有removal_id。 |
| 内部总量与明细舍入不一致 | 旺衰新增climate_energy_raw，使用math.fsum从原始energy_records合计；build_facts及快照合同使用raw。climate_energy继续作为六位小数展示。干预使用fsum，负值仅在8个机器浮点间距容差内归零并记录numerical_adjustments，真实负值拒绝。 |
| 未知维护需求无补证通道 | 新增maintenance_assessments，绑定原需求、完整原始账、基线和独立审核的撤除反事实。核验后仅更新维护派生结论，不改已测数值；精确解除对应maintenance_assessment缺口。其他缺口不清除。 |

## 情景身份与精度

情景保持climate_energy_only范围，不等于重排命盘或验证全局结构。派生的element_energy_after单独记录，facts_snapshot_id始终表示已核验的原始事实。scenario_id依赖当前政策/合同、完整模型和干预，不仅依赖模型名称。model_version相同而内容不同，也会产生不同评估身份。

原始账采用浮点的未舍入值与fsum，不宣称任意精度。浮点负值归零仅限可解释的机器误差，原值和界限同时记录；不会以宽泛容差掩盖实际超额移除。旧输入没有raw字段时保留既有climate_energy兼容入口，新增生产计算均提供raw字段。

## 维护补证合同

审核包fusion_evidence.maintenance_assessments为按需求ID索引的对象，仅处理当前maintenance_status=unknown的既有零缺口需求。prepare_fusion_context.unresolved_maintenance_targets给出待评估需求。

每项包含：

- original_need：完整原需求快照，必须原样绑定；baseline_ref保持一致。
- source_ledger_row：当前事实中同目标、方法、场景和来源组合的完整原始账。
- outcome：protect_required或no_dependency。
- withdrawal：scope=original_target、method=reviewed_withdrawal、remaining_with、remaining_without，均为有限非负数。
- evidence_refs：非空审核证据引用；每个registry记录绑定target_id、facts_snapshot_id、assessment_snapshot_id及完整maintenance_assessment（除定位引用本身）。

remaining_with须等于原始测得的当前缺口。protect_required要求remaining_without大于remaining_with；no_dependency要求两者相等。相反或不一致的结论拒绝。

通过后保留maintenance_source、original_demand、initial_demand和全部原始账；新增maintenance_resolution及verified状态。需要保护时仍为必需目标，路线必须另通过保护来源、药物、承受能力及跨维度验证，并与审核撤除反事实的数值一致。无依赖时才解除保护标记。补证本身不自动批准动作。

任何错配、旧身份、缺证据或擅改测量值都不解除未知；未知以外的数值/治法冲突仍阻断。维护判断是审核评估器的结论，本模块只执行合同，不编造撤除效果。

## 测试与冻结

新增tests/test_project_audit_v29.py六项测试：三个情景入口的失效快照拒绝；小数配置下全部/部分移除与真实负值拒绝；模型内容及干预身份；两种维护结论的完整仲裁正例；保护动作与审核撤除值不一致拒绝；旧身份、错账、改数值、矛盾结论和缺证据拒绝。

测试中的审核结论为构造合同样本，不作为独立领域金标准。冻结360盘数据、配置与原始预期不刷新。

本轮验证结果：新增6项针对性测试及完整回归通过。发布验收按预期失败：待判355/360，方向发布4，行动发布0；真实独立审定数据仍缺失。冻结数据及合同测试哈希均无错误。
