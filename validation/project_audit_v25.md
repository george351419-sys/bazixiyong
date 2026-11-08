# v25 项目方法与逻辑整改

日期：2026-11-07。政策：policy_v25_scope_and_input_contracts。

| 复核问题 | 已完成的解决方案 |
|---|---|
| 明确不安全的保护路线仍发布 | 有动作的路线只要核验为bearing_safe=false就拒绝。增加、保护、限制动作均要求有证据绑定的bearing_safe=true，未知则待判。 |
| 区间漏检节后天数分段 | 比较两端四柱、当前节气、节后整数天数及夏令时。任一不同或节气信息无法取得均要求补充钟点；返回候选四柱及candidate_solar_term_info。 |
| 辰时覆盖具体钟点 | 先从剔除时辰词的文本解析具体钟点，再校验其属于所述时辰范围；明确钟点不使用中点。矛盾、多种时辰标记拒绝。 |
| 非法时间串部分匹配 | 含冒号的时间字段完整匹配时:分或时:分:秒，拒绝三位小时/分钟/秒、小数秒、尾部冒号等非法格式。 |
| 历法参数互相矛盾 | lunar=true与calendar=solar在进入任何后端之前拒绝；数字入口、文本入口与显式外部适配器使用共同底线。 |
| 方向回退的独立案例冒充行动验证 | 案例增加direction或integrated_action范围。行动案例必须覆盖仲裁状态/模式、发布标志、最终来源、发布范围、行动开关、条件核查及完整positions。发布门要求有实际比较通过的融合行动正例。 |

区间天数检查采用保守规则：即使某次跨天未改变具体司令，也不把两种节后天数压成一个值。这保留了下游规则继续调整时的输入不确定性。

## 独立审定范围合同

沿用v24文件哈希、审定来源和逐字段比较。数据集或单个case可声明scope；省略时只视为direction，便于兼容旧方向案例。

发布工具固定以required_scope=integrated_action执行验证。方向案例可保留在混合案例集中，但至少需要一个融合行动正例；缺失时阻断。融合行动案例也可记录负例，仍须提供全部行动状态字段并精确比较。

融合行动正例必须预期：arbitration.decision_status=decided、mode=integrated、release_ready=true、action_release_ready=true；final_xiyong.effective_source=arbitration_integrated、release_scope=integrated_recommendation、release_ready/action_release_ready/actionable=true、conditional_review_status=complete及非空positions。positions整体与独立预期比较，包含动作、剂量和条件等原始发布字段。

预期必须由领域审定者提供，当前未提供真实独立审定数据；构造测试只验证合同，不充当命理金标准。

## 验证与限制

新增tests/test_project_audit_v25.py的7项反例，覆盖安全底线、区间天数、钟点优先级、完整时间字段、历法冲突、方向/行动范围隔离和实际行动字段比较。纳入统一回归及独立冻结测试哈希清单；360盘原fixture和原哈希不变。

生产评估器、气候模型依据与真实独立审定案例的既有缺口仍需补齐。此次整改不会自动把待判变成可发布。

本轮验证结果：新增7项反例、现有全部回归及JavaScript语法检查通过，git diff空白检查通过。发布验收按预期失败：355/360待判、方向发布4、行动发布0，独立融合行动审定数据缺失。
