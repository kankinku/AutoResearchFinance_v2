"""One-off read-only academic research ledger freeze + quality diagnostic.

Example:
python -m scripts.audit_academic_campaign --checkpoint-dir /path/to/checkpoints \
 --destination /path/to/ignored/audits/phase1-freeze \
 --origin-session <old-id> --active-session <new-id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.academic_campaign_audit import audit_campaign, snapshot_ledger


def _markdown(result: dict[str, object]) -> str:
    active = result["active_s7"]
    origin = result["origin_s7"]
    champion = result["latest_selected_parent"]
    coverage = result["active_s7_portfolio_risk_coverage"]
    assert isinstance(active, dict) and isinstance(origin, dict)
    assert isinstance(coverage, dict)
    champion = champion if isinstance(champion, dict) else {}
    total = result["generation_count"]
    previous = result["origin_completed"]
    current = result["active_completed"]
    origin_counts = f"{origin['better']} / {origin['worse']} / {origin['same']}"
    active_counts = f"{active['better']} / {active['worse']} / {active['same']}"
    champion_return = float(champion.get("total_return") or 0)
    champion_mdd = float(champion.get("mdd") or 0)
    champion_exposure = float(champion.get("exposure") or 0)
    available_risk = coverage["replayed_full_period_risk_coverage"]
    total_experiments = active["experiments"]
    return "\n".join(
        [
            "# Quant 학술 연구 원장 품질 감사 (1단계)",
            "",
            "> 조회·스냅샷 전용. 주문·독립 OOS·인과성 승인 아님.",
            f"- 연구 세대: **{total}** (이전 {previous} + 현재 {current})",
            f"- 개발 데이터 해시: `{result['dataset_hash']}`",
            f"- 이전 세션 S7 수익 개선·악화·동일: {origin_counts}",
            f"- 현재 세션 S7 수익 개선·악화·동일: **{active_counts}**",
            f"- 예측 방향 일치하였으나 수익 악화: **{active['matched_but_worse']}건**",
            f"- 동일 부모·자식 체결 흔적: **{active['unchanged_execution']}건**",
            f"- 자식 전략 해시 중복: **{active['duplicate_child_hashes']}건**",
            f"- 결과 일치 서명 쌍: {active['same_result_signature_pairs']}쌍 "
            "(동일 체결 증거는 아님)",
            f"- 개발 최우수 부모 수익률: **{champion_return:.2%}**, "
            f"MDD: **{champion_mdd:.2%}**, 노출률: **{champion_exposure:.2%}**",
            f"- S7 자식 전체기간 위험·노출 지표 재검증 가능: "
            f"**{available_risk}/{total_experiments}건**",
            "",
            "## 해석 경계",
            "",
            "- 비용 합계는 서로 다른 반복 백테스트의 합이며 포트폴리오 손익이 아님.",
            "- 원장 데이터는 개발 QQQ 기간을 반복 재사용하므로 과적합·다중검정 위험이 높음.",
            "- 부모 전략 단순 보유 QQQ 비교는 독립 OOS도 동일 위험의 전방검증 비교도 아님.",
            "- 각 세대 S7 자식 전체기간 MDD·노출률 일부는 제공되지 않아 임의로 계산하지 않음.",
            "- 파일 SHA256은 스냅샷 보존만 검증. 운영 증거 해시의 원본 재생검증은 별도 필요.",
            "- GPT/무작위 탐색의 예산 통제 비교는 아직 수행되지 않음.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--origin-session", required=True)
    parser.add_argument("--active-session", required=True)
    opts = parser.parse_args()
    snapshot_ledger(opts.checkpoint_dir, opts.destination)
    report = audit_campaign(
        opts.destination, origin_session=opts.origin_session, active_session=opts.active_session
    )
    (opts.destination / "quality-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (opts.destination / "quality-report.md").write_text(_markdown(report), encoding="utf-8")
    print(_markdown(report))


if __name__ == "__main__":
    main()
