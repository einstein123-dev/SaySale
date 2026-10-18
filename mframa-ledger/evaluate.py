"""Optional real-Gemini evaluation for extraction quality and review routing."""
import json
import os
import statistics
import time
from pathlib import Path

from ai_parser import parse_transaction


AUTO_COMMIT_THRESHOLD = 0.85
REQUIRED_FIELDS = {
    'sale': ('item_name', 'quantity', 'unit_price'),
    'expense': ('amount_for_expense',),
    'restock': ('item_name', 'quantity'),
}


def expected_requires_review(expected):
    kind = expected.get('type')
    if kind not in REQUIRED_FIELDS:
        return True
    return any(expected.get(field) is None for field in REQUIRED_FIELDS[kind] if field in expected)


def meets_basic_confidence_gate(actual, shop_currency, threshold=AUTO_COMMIT_THRESHOLD):
    return bool(
        actual.get('type') in REQUIRED_FIELDS
        and not actual.get('missing_fields')
        and not actual.get('clarification_question')
        and str(actual.get('currency') or '').upper() == shop_currency.upper()
        and actual.get('confidence', 0.0) >= threshold
    )


def _summarize_split(cases):
    successful = [case for case in cases if 'actual' in case]
    field_counts = {}
    for case in cases:
        for field in case['expected']:
            matched = case.get('matches', {}).get(field, False)
            correct, total = field_counts.setdefault(field, [0, 0])
            field_counts[field] = [correct + int(matched), total + 1]

    exact_matches = sum(bool(case.get('exact_match')) for case in cases)
    expected_review = [case for case in successful if case['expected_review']]
    gate_passes = sum(case['basic_confidence_gate_pass'] for case in expected_review)
    gate_eligible = sum(case.get('basic_confidence_gate_pass', False) for case in successful)
    latencies = [case['seconds'] for case in successful]
    return {
        'cases': len(cases),
        'successful_requests': len(successful),
        'exact_case_matches': exact_matches,
        'exact_case_accuracy': round(exact_matches / len(cases), 4) if cases else None,
        'field_accuracy': {
            field: {
                'correct': correct,
                'total': total,
                'accuracy': round(correct / total, 4) if total else None,
            }
            for field, (correct, total) in field_counts.items()
        },
        'median_successful_latency_seconds': round(statistics.median(latencies), 3) if latencies else None,
        'basic_confidence_gate_eligible_cases': gate_eligible,
        'basic_confidence_gate_review_cases': len(successful) - gate_eligible,
        'expected_review_cases': len(expected_review),
        'expected_review_cases_passing_basic_confidence_gate': gate_passes,
        'expected_review_capture_rate': round((len(expected_review) - gate_passes) / len(expected_review), 4) if expected_review else None,
    }


def summarize_results(results):
    splits = sorted({case['split'] for case in results})
    return {
        'total': _summarize_split(results),
        'by_split': {split: _summarize_split([case for case in results if case['split'] == split]) for split in splits},
    }


def run_evaluation(cases, api_key, model):
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            actual = parse_transaction(case['text'], api_key, model, currency=case['currency'])
            elapsed = time.perf_counter() - started
            matches = {field: actual.get(field) == value for field, value in case['expected'].items()}
            expected_review = expected_requires_review(case['expected'])
            basic_gate_pass = meets_basic_confidence_gate(actual, case['currency'])
            results.append({
                **case,
                'actual': actual,
                'matches': matches,
                'exact_match': all(matches.values()),
                'seconds': elapsed,
                'expected_review': expected_review,
                'basic_confidence_gate_pass': basic_gate_pass,
            })
        except Exception as error:
            results.append({**case, 'error_type': type(error).__name__, 'seconds': time.perf_counter() - started})
    return results


def main():
    api_key = os.getenv('GEMINI_API_KEY')
    model = os.getenv('GEMINI_MODEL')
    if not api_key or not model:
        raise SystemExit('Set GEMINI_API_KEY and GEMINI_MODEL in your environment first. No requests made.')

    cases = json.loads(Path('evaluation.json').read_text(encoding='utf-8'))
    results = run_evaluation(cases, api_key, model)
    report = {
        'model': model,
        'confidence_threshold': AUTO_COMMIT_THRESHOLD,
        'metrics': summarize_results(results),
        'limitations': (
            'Small synthetic set; item-name accuracy is not scored. Basic confidence-gate results '
            'do not model product matching, stock availability, role permissions, or actual transaction saves. '
            'They are not an unsafe-save rate or proof of calibrated confidence.'
        ),
        'results': results,
    }
    Path('evaluation-results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'results'}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
