// 八字喜用 · 前端逻辑
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);

  const WX_CLASS = { "木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water" };

  function chip(wx, extra) {
    const cls = WX_CLASS[wx] || "neutral";
    return '<span class="chip ' + cls + (extra ? " " + extra : "") + '">' + wx + "</span>";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  function render(out) {
    const box = $("result");
    if (!out.ok) {
      box.classList.remove("hidden");
      box.innerHTML = '<p class="warn">分析失败：' + esc(out.error) + "（阶段：" + esc(out.stage) + "）</p>";
      return;
    }

    const meta = out.paipan_meta || {};
    const ws = out.wangshuai || {};
    const xy = out.xiyong_wangshuai || {};
    const rd = ws.root_detail || {};

    let html = "";
    if (meta.八字) {
      html += '<div class="bazi-line">' + esc(meta.八字) + "</div>";
      html += '<div class="meta">日主：' + esc(meta.日主) + "（" + esc(out.day_wuxing) + "）";
      if (meta.公历) html += " ｜ 公历 " + esc(meta.公历);
      if (meta.农历) html += " ｜ 农历 " + esc(meta.农历);
      if (meta.生肖) html += " ｜ " + esc(meta.生肖);
      html += "</div>";
      if (meta.真太阳时校正分钟 != null) {
        html += '<div class="meta">真太阳时校正：' + esc(meta.真太阳时校正分钟) +
                " 分钟" + (meta.夏令时回拨 ? "（含夏令时回拨）" : "") + "</div>";
      }
    } else {
      html += '<div class="bazi-line">' + esc((out.input.year.gan + out.input.year.zhi) + " " +
              (out.input.month.gan + out.input.month.zhi) + " " +
              (out.input.day.gan + out.input.day.zhi) + " " +
              (out.input.hour.gan + out.input.hour.zhi)) + "</div>";
    }

    html += '<div style="margin-top:12px">' +
            '<span class="pill tag">旺衰：' + esc(out.tag) + "</span>" +
            '<span class="pill conf">规则置信系数 ' + esc(out.confidence) + "</span></div>";

    // F / K 能量条
    const F = ws.F || 0, K = ws.K || 0;
    const tot = (F + K) || 1;
    const fp = (F / tot * 100).toFixed(1), kp = (K / tot * 100).toFixed(1);
    html += '<div class="block"><div class="label">生扶 F / 克泄耗 K 能量分布</div>' +
            '<div class="bar"><div class="f" style="width:' + fp + '%"></div>' +
            '<div class="k" style="width:' + kp + '%"></div></div>' +
            '<legend>生扶 F=' + esc(F) + "（" + fp + "%） ｜ 克泄耗 K=" + esc(K) + "（" + kp + "%）" +
            (ws.ratio != null ? " ｜ F:K=" + esc(ws.ratio) : "") + "</legend></div>";

    // 当前有效根为主展示，结构根记录保留在可展开明细中。
    const state = ws.root_state || {};
    html += '<div class="block"><div class="label">当前根状态</div>';
    if (state.effective_count != null) {
      html += '<div>剩余有效根 ' + esc(state.effective_count) + ' 处 ｜ 有效根能量 ' + esc(state.effective_energy) + '</div>';
      if ((state.damaged_root_branches || []).length) html += '<div>受损根位置：' + state.damaged_root_branches.map(i => esc(["年支", "月支", "日支", "时支"][i])).join('、') + '</div>';
    }
    if ((state.pulled_branches || []).length) html += '<div>已拔根位置：' + state.pulled_branches.map(i => esc(["年支", "月支", "日支", "时支"][i])).join('、') + '</div>';
    html += '<details><summary>结构根记录</summary><div>' + esc(ws.root_status || "—") + ' ｜ 结构根能量 ' + esc(ws.root_energy) + '</div></details>';
    // 被冲支折扣（V1.2：多根遇冲整支折力）
    const bd = (ws.debug && ws.debug.branch_detail) || [];
    const chonged = bd.filter((b) => b.chong_factor != null && b.chong_factor < 1);
    if (chonged.length) {
      html += '<div style="margin-top:6px">遇冲折力：' +
              chonged.map((b) => esc(b.zhi) + "（×" + esc(b.chong_factor) + "）").join("、") +
              "</div>";
    }
    // 日主辨根档（从格专项：0 无根 / 1 微根·余气 / 2 强根 / 3 中气）
    const rlv = ws.effective_root_level != null ? ws.effective_root_level : ws.debug && ws.debug.root_level;
    if (rlv != null) {
      const names = ["无根", "微根·余气", "强根（本气/长生）", "中气"];
      html += '<div style="margin-top:6px">日主有效根档：' + esc(names[rlv] || rlv) + "</div>";
    }
    const marks = ws.phase_marks || [];
    if (marks.length) html += '<div>禄刃／帝旺标记：' + marks.map(m => esc(["年支", "月支", "日支", "时支"][m.branch_index] + m.zhi + '·' + m.label + (m.active ? '' : '（' + m.inactive_reason + '）'))).join('、') + '</div>';
    html += "</div>";
    if ((ws.boundary_hints || []).length) html += '<div class="note">接近判定边界：' + ws.boundary_hints.map(h => esc(h.current_tag + ' ↔ ' + h.adjacent_tag)).join('；') + '。仅作复核提示，不自动改判或切换喜用。</div>';

    // 喜用维度
    if (xy.conditional || xy.requires_review) html += '<div class="note">本盘喜用为条件候选，需结合以下残余根证据复核。</div>';
    html += '<div class="block"><div class="label">旺衰维度喜用（' + esc(xy.category || "—") + "）</div>" +
            '<div class="chips">' + (xy.favored || []).map((w) => chip(w)).join("") + "</div>" +
            '<div class="label" style="margin-top:10px">忌神</div>' +
            '<div class="chips">' + (xy.disliked || []).map((w) => chip(w)).join("") + "</div>";
    if (xy.neutral && xy.neutral.length) {
      html += '<div class="label" style="margin-top:10px">中性 / 慎用</div>' +
              '<div class="chips">' + xy.neutral.map((w) => chip(w, "neutral")).join("") + "</div>";
    }
    html += "</div>";

    html += '<div class="block"><div class="label">取用原则</div><div>' + esc(xy.principle || "") + "</div></div>";
    if (xy.note) html += '<div class="note">' + esc(xy.note) + "</div>";

    // 合局 / 开库 备注
    if (ws.warning && ws.warning.length) {
      html += '<div class="warn">备注：' + esc(ws.warning.join("；")) + "</div>";
    }

    // 克泄耗干虚透标记（只标记、不折力）
    const kd = (ws.debug && ws.debug.k_dry_unrooted) || [];
    if (kd.length) {
      html += '<div class="note">虚透克泄耗天干（满力计算，仅标记）：' +
              esc(kd.map((k) => k.gan).join("、")) + "</div>";
    }

    // 根明细
    const rl = (ws.debug && ws.debug.root_list) || [];
    if (rl.length) {
      html += '<div class="block"><div class="label">根明细</div><div class="roots">' +
              rl.map((r) => '<span class="r' + (r.is_broken ? " broken" : "") + '">' +
              esc(r.zhi) + "·" + esc(r.root_type) + "·" + esc(r.eff_energy) + "</span>").join("") +
              "</div></div>";
    }

    // 节气 / 司令信息（排盘模式自动推算）
    const sti = out.solar_term_info;
    if (sti && sti.jie_name) {
      html += '<div class="meta">节气：' + esc(sti.jie_name) + " " + esc(sti.jie_time) +
              " 后第 " + esc(sti.day) + " 天（" + esc(sti.exact_days) + " 天，来源：" +
              esc(out.solar_term_source) + "）</div>";
    } else if (sti) {
      html += '<div class="meta">节气：手工指定第 ' + esc(sti.day) + " 天</div>";
    }

    // 子平格局（独立维度，旺衰不参与定格）
    const gj = out.geju;
    if (gj) {
      const clsMap = { "成格": "ok", "成中有败": "warn2", "败中有救": "save", "真破格": "bad" };
      const statusCls = clsMap[gj.ge_status] || "";
      const list = (arr) => (arr && arr.length) ? arr.map((x) => esc(x)).join("、") : "不显";
      html += '<div class="block ge">' +
              '<div class="label">子平格局（纯月令取格 · 独立维度）</div>' +
              '<div class="ge-head"><span class="ge-name">' + esc(gj.main_ge_name) + "</span>" +
              (gj.an_ge_flag ? '<span class="pill conf">暗格</span>' : "") +
              '<span class="pill ge-status ' + statusCls + '">' + esc(gj.ge_status) + "</span>" +
              '<span class="pill conf">清浊：' + esc(gj.clean_level) + "</span></div>" +
              '<div class="ge-rows">' +
              "<div><b>格神</b> " + esc(gj.ge_shen) + "</div>" +
              "<div><b>相神</b> " + list(gj.xiang_shen_list) + "</div>" +
              "<div><b>忌神</b> " + list(gj.ji_shen_list) + "</div>" +
              "<div><b>司令（仅供参考，不参与取格）</b> " + esc(gj.siling_gan) +
                " ｜ 旺衰（附加）" + esc(gj.wangshuai_tag) + " / " +
                esc(gj.wangshuai_confidence) + "</div>" +
              "</div>";
      if (gj.an_ge_flag) html += '<div class="note">暗格依据：' +
        esc(gj.quge_basis) + "。</div>";
      if (gj.bijiao_tou && gj.bijiao_tou.length)
        html += '<div class="note">月令透出比劫 ' + esc(gj.bijiao_tou.join("、")) +
          "：该字不取格神。</div>";
      if (gj.lu_ren_flag) html += '<div class="note">禄刃月令，非八格；透干只作相神，不升格。</div>';
      if (gj.special_ge) html += '<div class="note">外格优先：' + esc(gj.special_ge) + "</div>";
      html += '<div class="ge-note">' + esc(gj.note) + "</div>";

      if (gj.rescue_summary?.weak_risks?.length) html += '<div class="note"><b>仍有弱忌／隐患：</b>' + gj.rescue_summary.weak_risks.map(esc).join('、') + '</div>';
      // Step8 格局维度喜用（李师傅笔记口径：有病治病为先 / 无病顺逆取用）
      const xyj = gj.xiyong_geju;
      if (xyj) {
        const listBr = (arr) => (arr && arr.length)
          ? arr.map((x) => esc(x)).join("<br>") : "不显";
        html += '<div class="block xy">' +
                '<div class="label">格局维度喜用（李师傅笔记：有病治病为先 / 无病顺逆取用）</div>' +
                '<div class="ge-head"><span class="pill ge-status ' +
                  (xyj.has_bing ? "bad" : "ok") + '">' + esc(xyj.mode) + "</span>" +
                '<span class="pill conf">' + (xyj.has_bing ? "有病" : "无病") + "</span>" +
                (xyj.has_unresolved_bing === false ? '<span class="pill conf">无未解决之病</span>' : "") +
                (xyj.has_unresolved_bing === true ? '<span class="pill conf">仍有未解决之病</span>' : "") +
                (xyj.used_original_drug ? '<span class="pill conf">实际使用原局药</span>' : "") +
                (xyj.self_balanced ? '<span class="pill conf">原局自有平衡，无需用药</span>' : "") +
                "</div>";
        if (xyj.bing_list && xyj.bing_list.length) {
          html += '<div class="xy-bing">' + xyj.bing_list.map((b) =>
            '<div class="xy-bing-row"><b>' + esc(b.name) + "</b> " +
            '<span class="pill ge-status ' +
              (b.severity === "坏格" ? "bad" : "warn2") + '">' + esc(b.severity) + "</span>" +
            "<div>病神：" + listBr(b.bing_shen) + "</div>" +
            "<div>原局救应：" + ((b.rescue_evidence || []).filter(e => e.power > 0 && e.drug_id).map(e => {
              const parts = e.drug_id.split(":");
              return esc(["年", "月", "日", "时"][Number(parts[0])] + "干" + parts[2] + "｜" + e.method + "｜分配力量" + e.power);
            }).join("<br>") || "尚无有效分配") + "</div></div>").join("") + "</div>";
        }
        html += '<div class="ge-rows">' +
                "<div><b>用神</b> " + listBr(xyj.yong_shen_list) + "</div>" +
                "<div><b>辅佐</b> " + listBr(xyj.xi_shen_list) + "</div>" +
                "</div>" +
                '<div class="ge-note">' + esc(xyj.principle) + "</div>";
        html += '<div class="ge-note"><b>格局喜用忌神：</b>' + listBr(xyj.ji_shen_list) + '</div>';
        if (xyj.conditional_ji_shen?.length) html += '<div class="note"><b>条件忌：</b>' + xyj.conditional_ji_shen.map(x => esc(x.wuxing + '：' + x.condition + (x.status ? '（' + x.status + '）' : ''))).join('<br>') + '</div>';
        if (xyj.third_element_roles?.length) html += '<div class="note"><b>第三行作用：</b>' + xyj.third_element_roles.map(x => esc(x.wuxing + '·' + x.role + '：' + x.condition)).join('<br>') + '</div>';
        if (xyj.potential_yong_shen?.length) html += '<div class="note"><b>潜在救应、待透：</b>' + listBr(xyj.potential_yong_shen) + '</div>';
        if (xyj.alternative_yong_shen?.length) html += '<div class="note"><b>替代方案（不可直接并用）：</b>' + listBr(xyj.alternative_yong_shen) + '</div>';
        if (xyj.conditional_yong_shen?.length) html += '<div class="note"><b>条件取用：</b>' + xyj.conditional_yong_shen.map(x => esc(x.shen + '：' + x.reason)).join('<br>') + '</div>';
        if (xyj.pending_yong_shen?.length) html += '<div class="note"><b>待运建议：</b>' + listBr(xyj.pending_yong_shen) + '</div>';
        if (xyj.treatment_status?.length) html += '<div class="note"><b>逐病治疗状态：</b>' + xyj.treatment_status.map(x => esc(x.name + '：' + x.status)).join('<br>') + '</div>';
        if (xyj.unresolved_bing?.length) html += '<div class="note"><b>尚待处理：</b>' + listBr(xyj.unresolved_bing) + '</div>';
        if (xyj.combination_validation?.length) html += '<div class="note">' + listBr(xyj.combination_validation) + '</div>';
        if (xyj.fuyi_hint) html += '<div class="note">' + esc(xyj.fuyi_hint) + "</div>";
        if (xyj.tiaohou_pending) {
          html += '<div class="meta" style="margin-top:8px">※ 调候维度已独立上线（见「调候维度」区块），但本层格局喜用尚未把「调候之病」并入病清单；笔记以调候之病最优先</div>';
        }
        html += "</div>";
      }

      if (gj.trace_log && gj.trace_log.length) {
        html += '<details class="trace"><summary>判定链路（' + gj.trace_log.length + " 步）</summary><ol>" +
                gj.trace_log.map((t) => "<li>" + esc(t) + "</li>").join("") +
                "</ol></details>";
      }
      html += "</div>";
    }

    // 调候维度（《穷通宝鉴》逐月取用，独立维度，不覆盖旺衰/格局）
    const th = out.tiaohou;
    if (th && th.ok) {
      const ganChips = (arr) => (arr && arr.length)
        ? arr.map((g) => '<span class="chip neutral">' + esc(g) + "</span>").join("") : "—";
      const cList = (arr) => (arr && arr.length) ? arr.map((x) => esc(x)).join("、") : "不显";
      html += '<div class="block th"><div class="label">调候维度（《穷通宝鉴》逐月取用 · 独立维度）</div>';
      html += '<div class="ge-head"><span class="pill tag">' + esc(th.day_gan) + " 日 " +
              esc(th.month_zhi) + " 月</span>" +
              '<span class="pill conf">' +
              (th.no_order ? "原书并用／无定序" : "首用 " + esc(th.zhuyong || "—")) + "</span>";
      if (th.segment && th.segment.applied)
        html += '<span class="pill conf">分段：' + esc(th.segment.applied) + "</span>";
      html += "</div>";

      const pres = th.presence || {};
      const presTxt = Object.keys(pres).map((g) => {
        const p = pres[g];
        return esc(g) + "：" + esc(p.state) +
               (p.tou_at && p.tou_at.length ? "（" + esc(p.tou_at.join("、")) + "）" : "") +
               (p.cang_at && p.cang_at.length ? "［藏 " + esc(p.cang_at.join("、")) + "］" : "");
      }).join(" ｜ ");
      const xy = th.xiyong || {};
      html += '<div class="ge-rows">' +
              "<div><b>调候用神</b> <span class=\"chips\">" + ganChips(th.yongshen) + "</span></div>" +
              "<div><b>原局透藏</b> " + (presTxt || "—") + "</div>";
      if (xy.missing && xy.missing.length)
        html += "<div><b>原局缺</b> " + cList(xy.missing) + "</div>";
      if (xy.favored_wuxing && xy.favored_wuxing.length)
        html += "<div><b>对应五行</b> " + xy.favored_wuxing.map((w) => chip(w)).join("") + "</div>";
      if (th.ji && th.ji.gans && th.ji.gans.length)
        html += "<div><b>忌／不可用</b> " + ganChips(th.ji.gans) + "（原文抽取，需复核）</div>";
      html += "</div>";

      if (th.conditions && th.conditions.length) {
        html += '<div class="label" style="margin-top:10px">条件用（带触发条件，非通用次用）</div><div class="ge-rows">';
        th.conditions.forEach((c) => {
          const mark = c.auto_triggered === true ? "✔ 已触发"
                     : (c.auto_triggered === false ? "✘ 未触发" : "? 待判");
          html += "<div><b>" + esc(c.expr || "—") + '</b> <span class="pill conf">' +
                  mark + "</span> " + esc(c.cond || "") + "</div>";
        });
        html += "</div>";
      }
      if (th.alt_read && th.alt_read.length) {
        th.alt_read.forEach((a) => {
          html += '<div class="note">另读备查（非默认）：' + cList(a.gans) + " — " +
                  esc(a.basis) + "</div>";
        });
      }
      if (th.segment && th.segment.undetermined)
        html += '<div class="warn">节气分段未定，当前取代表值；请填「调候节气分段」或「节气后第几天」以锁定乙·酉／乙·午／癸·辰等分段格。</div>';
      html += '<details class="trace"><summary>原书定序原句与备注</summary>' +
              '<div class="ge-note">' + esc(th.quote) + "</div>" +
              '<div class="ge-note">' + esc(th.note) + "</div></details>";
      html += '<div class="note">※ ' + esc(th.caveat) + "</div></div>";
    }

    const mods = out.modules || {};
    html += '<div class="meta" style="margin-top:14px">三维框架：旺衰=' + esc(mods.wangshuai) +
            "，格局=" + esc(mods.geju) + "，调候=" + esc(mods.tiaohou) +
            "（V1 不加权合并）。旺衰有效权重 effective_ws = 25 × " +
            esc(out.confidence) + " = " + esc(out.score_wangshuai && out.score_wangshuai.effective_ws) + "</div>";

    box.innerHTML = html;
    box.classList.remove("hidden");
  }

  function analyze() {
    const err = $("err");
    err.textContent = "";
    const chart = $("chart").value.trim();
    let payload = {};
    const std = $("solarTermDay").value.trim();
    if (std !== "") payload.solar_term_day = parseInt(std, 10);
    const thSeg = $("tiaohouSegment").value.trim();
    if (thSeg) payload.tiaohou_segment = thSeg;
    if (chart) {
      payload.chart = chart;
    } else {
      payload = Object.assign(payload, {
        birth: $("birth").value.trim(),
        sex: $("sex").value,
        lon: $("lon").value ? parseFloat($("lon").value) : null,
        truesun: $("truesun").checked,
      });
      if (!payload.birth) {
        err.textContent = "请填写生辰，或展开填写四柱。";
        return;
      }
    }

    const btn = $("go");
    btn.disabled = true; btn.textContent = "分析中…";
    fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json())
      .then((out) => render(out))
      .catch((e) => {
        $("result").classList.remove("hidden");
        $("result").innerHTML = '<p class="warn">请求失败：' + esc(e.message) + "</p>";
      })
      .finally(() => { btn.disabled = false; btn.textContent = "开始分析"; });
  }

  $("go").addEventListener("click", analyze);
})();
