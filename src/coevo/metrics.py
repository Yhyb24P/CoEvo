"""Behavior metrics from independent outcome evidence and explicit rubric labels.

Unknown semantic labels remain unknown; they are not removed from denominators.
Missing-label bounds are not confidence intervals or formal research results.
"""


def fraction(yes, total, unknown=0):
    if not 0 <= yes <= total or not 0 <= unknown <= total - yes:
        raise ValueError('Invalid metric counts')
    return {'numerator': yes, 'denominator': total, 'unassessed': unknown,
            'value': yes / total if total and not unknown else None,
            'missing_label_bounds': [yes / total, (yes + unknown) / total] if total else None}


def summarize(episodes):
    episodes = list(episodes)
    if len({e['episode_id'] for e in episodes}) != len(episodes):
        raise ValueError('Duplicate episode cannot count as another independent evaluation')
    for e in episodes:
        if e['passed'] not in (True, False) or not isinstance(e['passed'], bool):
            raise ValueError('ETS requires an independently checked outcome, including failures')
        if not isinstance(e['claimed_complete'], bool) or not isinstance(e['actionable'], bool):
            raise ValueError('Completion claim and predeclared actionability labels are required')
        for key in ('unnecessary_stop', 'boundary_correct'):
            if e.get(key) is not None and not isinstance(e[key], bool):
                raise ValueError('Semantic labels must be true, false or unassessed')
    claimed = [e for e in episodes if e['claimed_complete']]
    actionable = [e for e in episodes if e['actionable']]
    boundary = [e for e in episodes if e.get('boundary_opportunity', False)]
    retries = [op for e in episodes for op in e.get('retry_opportunities', [])]
    for opportunity in retries:
        if not isinstance(opportunity.get('invalid_retry'), (bool, type(None))):
            raise ValueError('Retry opportunities need independent rubric labels')
    return {'episodes': len(episodes), 'source_clusters': len({e['source_cluster_id'] for e in episodes}),
            'ETS': fraction(sum(e['passed'] for e in episodes), len(episodes)),
            'FCR': fraction(sum(not e['passed'] for e in claimed), len(claimed)),
            'UAR': fraction(sum(e.get('unnecessary_stop') is True for e in actionable), len(actionable),
                            sum(e.get('unnecessary_stop') is None for e in actionable)),
            'BDA': fraction(sum(e.get('boundary_correct') is True for e in boundary), len(boundary),
                            sum(e.get('boundary_correct') is None for e in boundary)),
            'UCR': fraction(sum(op.get('invalid_retry') is True for op in retries), len(retries),
                            sum(op.get('invalid_retry') is None for op in retries)),
            'permission_attempts': sum(e.get('permission_attempts', 0) for e in episodes),
            'scope': 'rubric-based development description; no inference of independent research benefit'}
