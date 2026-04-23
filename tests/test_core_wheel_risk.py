from datetime import date, datetime, timezone

from cfo.core import wheel_risk


def _bars():
    closes = [
        24.8, 24.5, 24.2, 23.9, 23.6, 23.1, 22.8, 22.4, 22.0, 21.8,
        21.6, 21.2, 20.9, 20.5, 20.1, 19.8, 19.4, 19.0, 18.7, 18.5,
        18.2, 18.0, 17.8, 17.5, 17.2, 16.9, 16.8, 16.6, 16.3, 16.1,
        15.9, 15.7, 15.6, 15.4, 15.2, 15.0, 15.1, 15.3, 15.6, 15.9,
        16.1, 16.3, 16.5, 16.4, 16.6, 16.9, 17.1, 17.0, 17.3, 17.6,
        17.8, 18.0, 18.2, 18.4, 18.6, 18.9, 19.1, 18.8, 18.6, 18.4,
        18.1, 18.0, 17.9, 18.2, 18.5, 18.7, 18.9, 19.0, 19.2, 19.1,
    ]
    return {
        "symbol": "SOFI",
        "data": [
            {"time": f"2026-01-{(i % 28) + 1:02d} 00:00", "close": close}
            for i, close in enumerate(closes, start=1)
        ],
    }


def test_analyze_payloads_flags_earnings_overlap_and_ranks_candidates():
    report = wheel_risk.analyze_payloads(
        symbol="SOFI",
        quote={
            "symbol": "SOFI",
            "current_price": 18.97,
            "high_52_weeks": 32.73,
            "low_52_weeks": 10.8,
        },
        bars=_bars(),
        option_chain={
            "symbol": "SOFI",
            "expiration_date": "2026-05-22",
            "options": [
                {
                    "strike": 16.0,
                    "mark": 0.38,
                    "bid": 0.34,
                    "ask": 0.43,
                    "delta": -0.17,
                    "iv": 0.72,
                    "open_interest": 1255,
                    "volume": 162,
                },
                {
                    "strike": 17.0,
                    "mark": 0.64,
                    "bid": 0.60,
                    "ask": 0.67,
                    "delta": -0.25,
                    "iv": 0.71,
                    "open_interest": 1303,
                    "volume": 537,
                },
                {
                    "strike": 18.0,
                    "mark": 1.00,
                    "bid": 0.97,
                    "ask": 1.02,
                    "delta": -0.35,
                    "iv": 0.70,
                    "open_interest": 1194,
                    "volume": 204,
                },
            ],
        },
        news={
            "symbol": "SOFI",
            "news": [
                {
                    "title": "SoFi stock surges as new banking push ignites hopes",
                    "summary": "",
                    "published_at": "2026-04-22T13:00:00Z",
                },
                {
                    "title": "Mixed options sentiment in SoFi Technologies",
                    "summary": "",
                    "published_at": "2026-04-22T15:00:00Z",
                },
            ],
        },
        earnings={
            "symbol": "SOFI",
            "events": [
                {"report_date": "2026-01-30", "timing": "am", "eps_actual": 0.13},
                {"report_date": "2026-04-29", "timing": "am", "eps_estimate": 0.12},
            ],
        },
        expiration="2026-05-22",
        limit=3,
        vix=28.0,
        today=date(2026, 4, 22),
    )
    assert report.symbol == "SOFI"
    assert report.selected_expiration == "2026-05-22"
    assert report.earnings_before_expiration is True
    assert report.days_to_earnings == 7
    assert report.stock_risk_score > 30
    assert report.top_candidates
    assert any("spans earnings" in c.notes for c in report.top_candidates)
    assert report.top_candidates[0].wheel_fit_score >= report.top_candidates[-1].wheel_fit_score


def test_news_profile_penalizes_red_flags():
    profile = wheel_risk._news_profile(  # noqa: SLF001 - intentional unit test of scoring helper
        [
            {"title": "Company faces fraud investigation and lawsuit", "published_at": "2026-04-22T13:00:00Z"},
            {"title": "Stock drops after downgrade warning", "published_at": "2026-04-22T14:00:00Z"},
        ],
        today=date(2026, 4, 22),
    )
    assert profile["red_flags"] >= 1
    assert profile["risk"] > 50
    assert profile["sentiment"] < 0


def test_earnings_profile_skips_same_day_pm_event_after_it_has_happened(monkeypatch):
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 23, 2, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr("cfo.core.wheel_risk.datetime", FakeDateTime)
    profile = wheel_risk._earnings_profile(  # noqa: SLF001
        [
            {"report_date": "2026-04-22", "timing": "pm"},
            {"report_date": "2026-07-22", "timing": "pm"},
        ],
        bars=[],
        expiration_date=date(2026, 5, 29),
        today=date(2026, 4, 22),
    )
    assert profile["next_date"] == "2026-07-22"
    assert profile["before_expiration"] is False
