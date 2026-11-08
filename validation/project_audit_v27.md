# v27 全项目复核整改记录

日期：2026-11-07。政策版本：policy_v27_intervention_and_conflict_integrity。
需求合同：needs_v6_maintenance_conflict_integrity；药效合同：effects_v6_intervention_binding。

| 问题 | 已实施解决方案 |
|---|---|
| 计划药效可被替换药物借用 | 对计划路线要求intervention_assessment审核记录；记录同时绑定完整动作组合、剂量、资源投用及对应目标/监测药效。任一输入或药效变化都会使旧记录失效。 |
| 未量化药效时零缺口丢失维护依赖 | 原始需求大于零、当前缺口为零的目标也保留必需保护项。已实现药效不完整时maintenance_status=unknown，生成明确缺口并阻断裁决。 |
| 维护必需标记可矛盾 | protection_required必须是布尔值，为true时required必须为true。路线覆盖检查独立读取保护标记；不能靠required=false漏掉维护目标。 |
| 治法关系矛盾被删除 | 保留原始关系观察，发现不一致时记录method_relation_conflict，需求生成及需求校验均返回证据冲突，审核包不得清除。 |

## 干预与药效配对审核合同

新模块bazi_core/intervention.py的intervention_recipe仅整理待审核快照，不计算、批准药效。快照包括：

- route_id；完整actions（排除定位用evidence_refs，其他输入保留）。
- 各计划目标与监测的dose_plan，包括数值、单位、上限及基线。
- resources及resource_usage（排除定位用evidence_refs），包括容量和投用编号。
- 对应assessed_effects与assessed_monitors（保留药效与执行条件，排除定位用evidence_refs）。

route.intervention_assessment.evidence_refs指向route.evidence_registry中的审核记录，记录的route_id和intervention_recipe必须与当前路线完全一致。该记录与原有逐目标药效证据、动作证据和资源证据同时校验。旧药效数值不能在更换药物后直接复用；新增或重新生成这份审核记录是评估器的审核动作，生产路径不会自动生成“通过”记录。

这仍是内部审核合同，不是对外部提交者身份的认证。

## 未知与冲突的处理

维护未知和治法冲突与数值需求分开保存。不得用零缺口代表维护安全，也不得把冲突的关系默认改为联合关系。未知维护需补齐原始药效及撤除/保护依据；矛盾关系需在来源事实中完成复核后生成新的事实与评估身份。旧审核身份随版本升级失效。

## 验证与冻结

新增tests/test_project_audit_v27.py五项测试，涵盖换药失效及重新审核正例，方法/剂量/投用/资源/药效变化，未知维护，维护标记合同与独立覆盖，以及关系冲突来源保留。

既有合成正例适配新合同：tests/test_fusion_completion.py的prepared显式添加合成配对审核记录；tests/test_project_audit.py的结构补充正例在修改完整路线后重新声明合成审核；tests/test_fusion_audit_fixes.py的组装失败用例在移除意图后绑定该构造路线，以继续验证后续组装拒绝路径。对应测试文件哈希在manifest中明确更新。

以上调整仅适配合同测试，不刷新360盘原始fixture、预期或数据哈希，不构造独立领域金标准。真实生产评估器和独立领域数据缺口继续阻断发布。

验证结果：新增5项针对性测试及完整回归通过；JavaScript语法与git diff空白检查通过。发布验收按预期失败：待判355/360、方向发布4、行动发布0；无冻结数据或合同测试哈希错误，真实独立审定数据仍缺失。
