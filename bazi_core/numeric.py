"""不会因超大整数溢出的共同有限数值检查。"""
import math

def finite(value):
    if type(value) not in (int,float): return False
    try: return math.isfinite(value)
    except (OverflowError,ValueError,TypeError): return False
