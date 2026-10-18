import evaluate


def test_evaluation_separates_held_out_metrics_and_review_gate():
    results = [
        {
            'split': 'held-out',
            'expected': {'type': None},
            'matches': {'type': False},
            'exact_match': False,
            'actual': {'type': 'expense'},
            'seconds': 0.2,
            'expected_review': True,
            'basic_confidence_gate_pass': True,
        },
        {
            'split': 'development',
            'expected': {'type': 'sale'},
            'matches': {'type': True},
            'exact_match': True,
            'actual': {'type': 'sale'},
            'seconds': 0.1,
            'expected_review': False,
            'basic_confidence_gate_pass': True,
        },
    ]

    summary = evaluate.summarize_results(results)

    assert summary['total']['cases'] == 2
    assert summary['by_split']['held-out']['exact_case_accuracy'] == 0.0
    assert summary['by_split']['held-out']['expected_review_cases_passing_basic_confidence_gate'] == 1
    assert summary['by_split']['held-out']['expected_review_capture_rate'] == 0.0
    assert summary['by_split']['held-out']['field_accuracy']['type']['accuracy'] == 0.0
    assert summary['by_split']['development']['exact_case_accuracy'] == 1.0


def test_basic_confidence_gate_rejects_missing_fields_low_confidence_and_currency_mismatch():
    complete = {
        'type': 'sale', 'missing_fields': [], 'clarification_question': None,
        'currency': 'GHS', 'confidence': 0.85,
    }

    assert evaluate.meets_basic_confidence_gate(complete, 'GHS')
    assert not evaluate.meets_basic_confidence_gate({**complete, 'confidence': 0.84}, 'GHS')
    assert not evaluate.meets_basic_confidence_gate({**complete, 'missing_fields': ['quantity']}, 'GHS')
    assert not evaluate.meets_basic_confidence_gate({**complete, 'currency': 'USD'}, 'GHS')
