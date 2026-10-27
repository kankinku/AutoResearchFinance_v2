/* D8 — fixed original G124 retrospective 2026 QQQ, never sealed OOS. */
(() => {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const format = (value) => Number(value).toLocaleString("ko-KR", {
    minimumFractionDigits: 1, maximumFractionDigits: 1,
  });
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  let charts = null;
  let evidence = null;

  function note(text, invalid = false) {
    const element = byId("oos-date-note");
    element.textContent = text;
    element.className = invalid ? "muted trace-range-note range-error" :
      "muted trace-range-note";
  }

  function validateWindow(from, to) {
    if (!evidence || !/^\d{4}-\d{2}-\d{2}$/.test(from) ||
        !/^\d{4}-\d{2}-\d{2}$/.test(to) ||
        from > to || from < evidence.period_start || to > evidence.period_end) {
      throw new Error("2026년 시장 데이터 안에서 시작일과 종료일을 선택하세요.");
    }
    const selected = evidence.candles.filter((bar) =>
      bar.time >= from && bar.time <= to);
    if (!selected.length) {
      throw new Error("지정한 날짜에는 QQQ 거래일이 없습니다.");
    }
    return selected;
  }

  function setWindow() {
    if (!charts) return;
    const from = byId("oos-start").value;
    const to = byId("oos-end").value;
    try {
      const selection = validateWindow(from, to);
      if (selection.length === 1) {
        const index = evidence.candles.findIndex((b) => b.time === selection[0].time);
        const logical = {from: index - .5, to: index + .5};
        charts.price.timeScale().setVisibleLogicalRange(logical);
        charts.equity.timeScale().setVisibleLogicalRange(logical);
      } else {
        const actual = {from: selection[0].time, to: selection[selection.length - 1].time};
        charts.price.timeScale().setVisibleRange(actual);
        charts.equity.timeScale().setVisibleRange(actual);
      }
      note("확대 중: " + from + " ~ " + to + " · " +
        selection.length.toLocaleString("ko-KR") + "거래일 · 성과는 2026년 전체 기준");
    } catch (error) {
      note(error.message, true);
    }
  }

  function resetWindow() {
    if (!charts || !evidence) return;
    charts.price.timeScale().fitContent();
    charts.equity.timeScale().fitContent();
    byId("oos-start").value = evidence.period_start;
    byId("oos-end").value = evidence.period_end;
    note("전체 2026년 검증 구간 · " + evidence.candles.length + "거래일");
  }

  async function init() {
    try {
      const response = await fetch("api/oos/2026-g124", {
        cache: "no-store", headers: {Accept: "application/json"},
      });
      if (!response.ok) throw new Error("검증 결과 API: HTTP " + response.status);
      const data = await response.json();
      if (data.status !== "VERIFIED_RETROSPECTIVE_NON_PIT_NOT_SEALED" ||
          data.generation !== 124 || data.orders_enabled !== false ||
          data.candles?.length !== data.equity?.length ||
          data.metrics.fill_count !== data.fills?.length ||
          data.candles.length < 150) {
        throw new Error("2026년 검증 증거를 확인할 수 없습니다.");
      }
      evidence = data;
      byId("oos-status").textContent = "사후 OOS 재현 완료";
      const metrics = [
        ["G124 · 2026 수익률", format(data.metrics.strategy_return_pct) + "%",
          "2026년 첫 거래일 1만 달러로 시작한 별도 백테스트"],
        ["QQQ 단순 보유", format(data.metrics.qqq_return_pct) + "%",
          "2026년 QQQ 첫 거래일 시가 매수 후 마지막 종가 평가 · 배당 제외"],
        ["G124 최대 하락폭", format(data.metrics.strategy_max_drawdown_pct) + "%",
          "2026년 중 평가금액의 이전 최고점 대비 최대 하락"],
        ["QQQ 대비 차이", format(data.metrics.qqq_excess_pp) + "%p",
          "G124 수익률에서 동기간 QQQ 단순 보유 수익률을 뺀 값"],
      ];
      byId("oos-kpis").innerHTML = metrics.map(([label, value, help]) =>
        "<div><span class='label'>" + escapeHtml(label) + "</span><strong>" +
        escapeHtml(value) + "</strong><small>" + escapeHtml(help) + "</small></div>"
      ).join("");
      const rows = data.fills.map((item) =>
        "<tr><td>" + escapeHtml(item.time) + "</td><td>" +
        (item.side === "buy" ? "매수" : "매도") + "</td><td>" +
        format(item.price) + "</td><td>" + format(item.cost) + "</td></tr>"
      );
      byId("oos-orders").innerHTML = rows.join("");
      byId("oos-summary").textContent = data.period_start + " ~ " +
        data.period_end + " · " + data.candles.length.toLocaleString("ko-KR") +
        "거래일 · 체결 " + data.fills.length.toLocaleString("ko-KR") +
        "건 · 거래비용 " + format(data.metrics.cost_usd) +
        "달러 · 최종 평가금액 " + format(data.metrics.end_equity_usd) + "달러";
      byId("oos-warnings").replaceChildren();
      for (const warning of data.warnings) {
        const note = document.createElement("p");
        note.textContent = warning;
        byId("oos-warnings").append(note);
      }
      const lib = window.LightweightCharts;
      if (!lib?.createChart || !lib?.CandlestickSeries ||
          !lib?.LineSeries || !lib?.createSeriesMarkers) {
        throw new Error("차트 라이브러리를 사용할 수 없습니다.");
      }
      const chartOpts = {
        autoSize: true,
        layout: {background: {type:"solid",color:"#fff"},textColor:"#475467"},
        grid: {vertLines:{color:"#edf1f5"},horzLines:{color:"#edf1f5"}},
        timeScale: {timeVisible:false,secondsVisible:false},
        localization: {locale:"ko-KR"},
      };
      const price = lib.createChart(byId("oos-price"), chartOpts);
      const candle = price.addSeries(lib.CandlestickSeries, {
        upColor:"#12986d",downColor:"#d44949",borderVisible:false,
        wickUpColor:"#12986d",wickDownColor:"#d44949",
      });
      candle.setData(data.candles.map((item) => ({
        time:item.time,open:item.open,high:item.high,low:item.low,close:item.close,
      })));
      const marks = data.fills.map((item) => ({
        time:item.time,
        position:item.side === "buy" ? "belowBar" : "aboveBar",
        shape:item.side === "buy" ? "arrowUp" : "arrowDown",
        color:item.side === "buy" ? "#087443" : "#b42318",
        text:item.side === "buy" ? "매수" : "매도",
      }));
      lib.createSeriesMarkers(candle, marks.sort((a,b) =>
        a.time.localeCompare(b.time)));
      const equity = lib.createChart(byId("oos-equity"), chartOpts);
      const line = equity.addSeries(lib.LineSeries, {
        color:"#2563eb",lineWidth:2,priceLineVisible:false,
      });
      line.setData(data.equity);
      charts = {price,equity};
      byId("oos-start").min = data.period_start;
      byId("oos-start").max = data.period_end;
      byId("oos-end").min = data.period_start;
      byId("oos-end").max = data.period_end;
      for (const id of ["oos-start","oos-end","oos-zoom","oos-reset"]) {
        byId(id).disabled = false;
      }
      byId("oos-zoom").addEventListener("click", setWindow);
      byId("oos-reset").addEventListener("click", resetWindow);
      resetWindow();
    } catch (error) {
      byId("oos-status").textContent = "검증 자료 확인 실패";
      byId("oos-summary").textContent = error.message;
      note("검증 가능한 2026년 데이터가 없어 차트를 표시하지 않습니다.", true);
    }
  }
  // Hidden panels cannot initialize Lightweight Charts at zero width.
  // Standalone /oos keeps the previous eager behavior for older bookmarks.
  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("quant-panel-oos")) {
      window.addEventListener("quant:activate-oos", () => {
        if (evidence || charts) return;
        void init();
      }, {once: true});
    } else {
      void init();
    }
  });
})();
