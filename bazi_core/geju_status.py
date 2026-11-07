"""格局救应的统一状态词；值保持兼容现有JSON。"""
class State:
    RESCUED = '完全获救'
    BALANCED = '原局自有平衡'
    PARTIAL = '部分解决'
    CORRESPONDING = '原局有对应药'
    NO_DRUG = '原局无药'
    POTENTIAL = '潜在救应、待透'
    PENDING = '待运方案'

SATISFIED = frozenset((State.RESCUED, State.BALANCED))
