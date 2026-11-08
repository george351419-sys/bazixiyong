# -*- coding: utf-8 -*-
"""八字喜用判断 · 本地 Web 服务（标准库 http.server，零依赖）。

提供：
  GET  /              返回前端页面 index.html
  GET  /<静态资源>     返回 web/ 下的 css/js 等
  POST /api/analyze   八字旺衰 + 旺衰维度喜用 + 子平格局 + 格局维度喜用 + 调候维度

payload 可选字段：
  solar_term_day      节气后第几天（司令参考/调候近似分段，不参与取格）
  enable_special_ge   是否启用外格前置筛查（默认 true）
  input_kind          real_chart（默认）或显式rule_case（规则构造案例）
  tiaohou_segment     调候节气分段（段A/段B/上半月/下半月/清明后/谷雨后），不传自动推断

启动：
  python web/server.py [--port 8000] [--host 127.0.0.1]

说明：生产部署可替换为 gunicorn/uvicorn；当前用标准库以满足环境零依赖约束。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
sys.path.insert(0, PROJECT_ROOT)

from bazi_core.paipan import analyze_birth  # noqa: E402
from bazi_core.engine import analyze  # noqa: E402
from bazi_core.input_contracts import normalize_chart, integer, boolean, finite_number


def _parse_chart(s):
    parts = s.split()
    if len(parts) != 4:
        raise ValueError("chart 需四柱干支，空格分隔")
    order = ["year", "month", "day", "hour"]
    chart = {}
    for i, p in enumerate(parts):
        if len(p) != 2:
            raise ValueError("干支应为 2 字：%s" % p)
        chart[order[i]] = {"gan": p[0], "zhi": p[1]}
    return chart


def do_analyze(payload):
    """根据 payload 调引擎，返回结果 dict。"""
    try:
        if not isinstance(payload,dict): raise ValueError('请求需为JSON对象')
        for key in ('enable_special_ge','truesun','lunar','leap','eot'):
            if key in payload: boolean(payload[key],key)
        if payload.get('lon') is not None: finite_number(payload['lon'],'lon',-180,180)
        if 'chart' in payload and payload['chart'] not in (None,'') and not isinstance(payload['chart'],(str,dict)):
            raise ValueError('chart需为字符串或四柱对象')
        return _do_analyze(payload)
    except (ValueError,TypeError,KeyError) as exc:
        return dict(ok=False,error=str(exc),stage='input')


def _do_analyze(payload):
    config = None
    if "enable_special_ge" in payload:
        config = {"enable_special_ge": payload["enable_special_ge"]}
    raw_day = payload.get("solar_term_day")
    try:
        std = integer(raw_day,'solar_term_day',0,40) if raw_day not in (None, "") else None
    except (TypeError, ValueError):
        return {"ok": False, "error": "solar_term_day 需为整数", "stage": "input"}

    chart = payload.get("chart")
    if chart:
        try:
            c = _parse_chart(chart) if isinstance(chart,str) else dict(chart)
            c['input_kind']=payload.get('input_kind','real_chart')
            c,_=normalize_chart(c,default_kind='real_chart')
        except ValueError as e:
            return {"ok": False, "error": str(e), "stage": "input"}
        if std is not None:
            c["solar_term_day"] = std
        out = analyze(c, config=config, tiaohou_segment=payload.get("tiaohou_segment"))
        out["input"] = c
        return out

    # 走排盘（自然语言 / 公历 / 农历 / 真太阳时）
    out = analyze_birth(
        birth=payload.get("birth"),
        y=payload.get("y"), m=payload.get("m"), d=payload.get("d"),
        h=payload.get("h"), minute=payload.get("minute", 0), second=payload.get("second",0),
        sex=payload.get("sex", "male"),
        lon=payload.get("lon"), truesun=payload.get("truesun", False),
        lunar=payload.get("lunar", False),
        leap=payload.get("leap", False),calendar=payload.get('calendar'),
        sect=payload.get('sect'),eot=payload.get('eot',False),
        config=config, solar_term_day=std,
        tiaohou_segment=payload.get("tiaohou_segment"),
    )
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html; charset=utf-8")
        # 静态资源
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(ROOT, rel))
        if os.path.commonpath([ROOT,full])!=ROOT or not os.path.isfile(full):
            return self._send(404, {"ok": False, "error": "not found"})
        ctype = "text/javascript; charset=utf-8" if full.endswith(".js") else \
                ("text/css; charset=utf-8" if full.endswith(".css") else
                 "application/octet-stream")
        return self._serve_file(rel, ctype)

    def _serve_file(self, rel, ctype):
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            return self._send(404, {"ok": False, "error": "not found"})
        with open(full, "rb") as f:
            data = f.read()
        self._send(200, data, ctype)

    def do_POST(self):
        if urlparse(self.path).path != "/api/analyze":
            return self._send(404, {"ok": False, "error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            return self._send(400, {"ok": False, "error": "JSON 解析失败：%s" % e})
        try:
            out = do_analyze(payload)
        except Exception as e:
            return self._send(500, {"ok": False, "error": "分析异常：%s" % e})
        return self._send(200 if out.get('ok') else 400, out)


def main():
    ap = argparse.ArgumentParser(description="八字喜用 Web 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("八字喜用 Web 服务已启动： http://%s:%d/" % (args.host, args.port))
    print("按 Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
