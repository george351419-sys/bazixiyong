// Exercise the actual click -> fetch -> render flow with engine output from stdin.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const path = require('path');
const outputs = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  for (const output of outputs) {
    const nodes = {};
    const document = {getElementById(id) {
      return nodes[id] ||= {value: id === 'chart' ? 'test chart' : '', innerHTML: '',
        classList: {remove() {}}, addEventListener(event, fn) {this.listener = fn;}};
    }};
    const context = {document, fetch: () => Promise.resolve({json: () => Promise.resolve(output)})};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8'), context);
    nodes.go.listener();
    await new Promise(resolve => setImmediate(resolve));
    const html = nodes.result.innerHTML;
    if (output.final_xiyong.primary_status === 'tied') {
      assert(html.includes('方向并列首选：' + output.final_xiyong.primary_gans.join('≈')), html);
      assert(!html.includes('方向首用：'), html);
    }
    if ((output.final_xiyong.cutoff_tied_gans || []).length) {
      assert(html.includes('同分未展示字：' + output.final_xiyong.cutoff_tied_gans.join('、') + '</div>'), html);
    }
    assert(html.includes('当前根状态'), html);
    assert(html.includes('当前取用方向'), html);
    assert(html.includes(output.final_xiyong.effective_source), html);
    assert(html.includes(output.final_xiyong.principle.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')), html);
    for (const position of output.final_xiyong.positions || []) {
      if (position.dose_plan) {
        assert(html.includes('投用：' + position.dose_plan.amount + ' ' + position.dose_plan.unit), html);
        assert(html.includes('上限：' + position.dose_plan.max_amount), html);
        assert(html.includes(position.application_id), html);
      }
    }
    assert(html.includes('原始旺衰维度取用原则'), html);
    assert(html.includes('剩余有效根 ' + output.wangshuai.root_state.effective_count));
    assert(html.includes('<details><summary>结构根记录</summary>'));
    assert(html.indexOf('剩余有效根') < html.indexOf('<summary>结构根记录'));
    if (output.xiyong_wangshuai.conditional) {
      assert(html.includes('条件候选'));
      assert(html.includes('本盘证据：'));
    }
    if (output.wangshuai.phase_marks.length) assert(html.includes('禄刃／帝旺标记'));
    if (output.wangshuai.boundary_hints.length) {
      assert(html.includes('接近判定边界'));
      for (const hint of output.wangshuai.boundary_hints) assert(html.includes(hint.adjacent_tag));
    }
    if (output.tag === '假从强') assert(html.includes('时支金'));
  }
  process.stdout.write('render checks passed\n');
})().catch(error => {console.error(error); process.exitCode = 1;});
