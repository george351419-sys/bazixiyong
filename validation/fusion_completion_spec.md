# 喜用融合整改规格与完成对照（policy_v21）

本文件保留v21验收记录。当前v22的全项目整改、规则变化及未完成的生产依据见[project_audit_v22.md](project_audit_v22.md)。默认生辰后端、完整条件判定、结构需求补充和逐动作资源核账以v22为准。

本文件对应最后一轮完整审计清单。整改按清单验收；程序合同通过不等于命理正确性已有独立证明。

## 一、六项代码缺陷的处理

| 审计问题 | 当前规则 | 验收位置 |
|---|---|---|
| 天干、五行可以矛盾 | contracts.action_identity 是唯一精度与五行合同。干级五行由天干推导，冲突输入阻断 | test_gan_and_wuxing_must_agree |
| 正缺口可被 required=false 跳过 | 正缺口必须 required=true。路线需覆盖或按政策延期；替代方法使用 choice_group 选一项 | test_positive_need_cannot_be_optional / test_method_alternatives_require_one_choice |
| 已实现药效被继续建议加强 | increase 只接受 planned，当前缓解为0、预计缓解单列，剂量计划必须有数量、单位、上限与基线绑定 | test_realized_effect_cannot_be_recommended_as_an_increase / test_planned_effect_has_no_realized_dose |
| 组装失败混入旧缺口 | 已完成覆盖时不再恢复自动候选的旧缺口；final_assembly=blocked、reason=action_assembly_failed。行动无效候选先排除再排序 | test_assembly_failure_does_not_restore_old_missing_items / test_invalid_action_cannot_block_valid_competitor |
| 畸形输入导致类型异常 | 证据包、路线容器、引用、ID、精度与方法选择先检查结构，返回待判错误 | test_malformed_bundle_fields_return_errors |
| 不相关政策虚增覆盖率 | 扶抑冲突匹配POL-06，格局冲突匹配POL-02至05，双冲突两侧都匹配；另报成功裁决与证据待判数 | test_unrelated_policy_does_not_cover_conflict |

## 二、固定时间口径

1. 原局需求已经扣除原局已实现药效。缺口与药效完整性分别记录，不能由缺口反推药力。
2. 原局／已实现作用使用 execution_status=realized；可用于说明已满足或有保护依赖，不据此生成加强建议。
3. 候选计划使用 execution_status=planned：relief_realized=0、remaining=当前缺口；relief_feasible / projected_remaining / projected_aggravation 描述执行后投影。
4. planned 的 dose=null，projected_dose 才是预计剂量比。dose_plan 必须给 amount、max_amount、unit、baseline_ref 并绑定相同证据。
5. 条件未满足使用 not_executed + deferred，必须有条件表达式与政策授权。条件已满足也必须重验，不能直接把预计药效当原局事实。
6. 路线比较使用 comparison_relief 和投影后 remaining；公开结果保留 current_remaining 与 projected_remaining，避免混淆。

## 三、资源、方法与反事实

- 同一目标的不同处理方法不是多个可以相加的需求。build_needs 为同目标同组合的不同方法建立 choice_group，路线必须明确 method_choices。
- planned 路线必须有 resources / resource_usage。一次 application_id 可同时作用多个维度，但容量只扣一次；重复申请、遗漏作用目标、剂量不一致或超容量均阻断。
- 保护要求移除后缺口增大的证据或有效结构依赖；限制要求同基线的反事实证据；不能从忌神标签直接推导。
- scenario_evaluation.climate_intervention 与 climate_removal 复用同一已审核气候模型，保留缓解和加剧两面。它们只计算气候能量干预，不冒充八字重新排盘或全局结构反事实。完整结构和承受能力仍须评估器重验。

## 四、统一入口、特殊结构与输出

原局事实身份 → 需求评估身份 → 路线评估身份，单向依赖。改变候选不能反向改写需求基线。

从格、化气、专旺、两气成象统一经过 special_structure_verdict 和最终发布校验。分类验真依据来自已有格局筛查与旺衰逐根事实，不复制判格阈值。化气不再由引擎提前覆盖。特殊结构只发布方向，不能视为行动已验证。

假从普通方向暂定，顺从路线带具体残根／印比／克泄耗障碍。无法机器确认的逐根改变保留人工核查；最终标签重验表达式不冒充去病措施。当前上游没有独立“假化”事实生产器，不能由格名字符串猜造假化路线。

普通路线支持两种接入：

- 静态 fusion_evidence：绑定事实、需求身份、各维度覆盖和政策证据，再经过完整路线检查。
- analyze(..., fusion_provider=provider)：内部评估器在同一次真实分析中接收 prepare_fusion_context，复用同一份旺衰输出；不能与静态证据包同时使用。

review_status=approved 是内部审核合同，不是外部认证。证据登记只能证明可追溯、一致，不能替代实际药效与承受评估。

release_scope=direction_conclusion 和 integrated_recommendation 分别表示方向与路线范围。release_ready 和 action_release_ready 分开；只有证据、身份、条件、剂量与资源等检查通过后才发布行动。

## 五、验收与冻结

- python3 tools/run_regression.py：完整行为回归和审计反例。
- python3 tools/audit_fusion_release.py --enforce --output validation/fusion_release_latest.json：发布门槛；失败返回非零。
- manifest 冻结360盘的原fixture、原config、逐盘external开关与哈希，另冻结构造合同测试文件哈希。不得把外格全开结果与原分母混报。
- 待判率≤10%，已知冲突政策覆盖率≥95%，冲突类型未知时阻断。规则匹配率不等于成功裁决率。
- 基线按implementation_snapshot标注；构造用例不是命理金标准。历史600盘只有汇总数字，没有逐盘数据，未伪造纳入。
- test_real_chart_to_final_output_without_mocking、test_single_pass_provider_receives_real_context 使用真实引擎、真实四柱及合成模型证据验证消费闭环；后者不重算旺衰。它们不证明合成模型符合命理实战。

## 六、能力完成状态与生产阻断

| 能力 | 程序状态 | 生产依据状态 |
|---|---|---|
| 气候需求与干预投影 | 已支持审核模型，未复制能量打分 | 缺默认模型的独立审定映射与阈值 |
| 扶抑与承受能力 | 评估器上下文、绑定、证据覆盖与政策消费已接通 | 缺默认数值评估器及审核边界 |
| 修复与替代路线 | 自动意图、气候投影、选路和行动组装已接通 | 完整跨维度药效、剂量上限仍由审核评估器提供 |
| 共享资源、互斥方法 | 已实现并有反例测试 | 资源容量数值需要来源 |
| 保护与限制 | 反事实合同与校验、气候局部重算已实现 | 全局结构与承受反事实尚需模型 |
| 特殊结构 | 四类统一出口已实现，假从保留独立条件路线 | 假化上游数据未定义；罕见结构仍需独立构造与人工案例 |
| 发布验收 | 分母、哈希、分项指标、阻断命令已实现 | 独立人工审定案例不足，默认生产待判率仍高 |

上述生产阻断不能用构造证据、任意阈值、补一个approved标记或降低门槛替代。当前交付完成可依据代码修复的清单与评估接入，尚未达到默认生产可发布。
