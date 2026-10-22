"""Versioned extraction contracts and date-independent reviewed-label projection."""

from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import json
import re
import unicodedata

from jsonschema import Draft202012Validator

from ..review.errors import ReviewError
from ..review.validation import METRICS, load_label_schema, validate_labels as validate_legacy_labels

LEGACY_CONTRACT = 'earnings_eps.v1'
FISCAL_CONTRACT = 'earnings_eps.fiscal.v2'
CONTRACTS = (LEGACY_CONTRACT, FISCAL_CONTRACT)
FISCAL_FIELDS = ('value', 'currency', 'period_type', 'fiscal_year', 'fiscal_quarter')


def require_contract(contract):
    if not isinstance(contract, str) or contract not in CONTRACTS:
        raise ReviewError(f'Unsupported label_contract; expected one of {CONTRACTS}.')
    return contract


def load_schema(contract):
    require_contract(contract)
    if contract == LEGACY_CONTRACT:
        return load_label_schema()
    path = files('finbot_filing_evals.evaluation').joinpath('schemas/earnings_eps_fiscal_v2.schema.json')
    return json.loads(path.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def fiscal_validator():
    schema = load_schema(FISCAL_CONTRACT)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_labels(labels, *, contract=LEGACY_CONTRACT, location='labels'):
    require_contract(contract)
    if contract == LEGACY_CONTRACT:
        validate_legacy_labels(labels, location=location)
        return
    error = next(fiscal_validator().iter_errors(labels), None)
    if error:
        suffix = '.'.join(str(part) for part in error.absolute_path)
        raise ReviewError(f'{location}{"." + suffix if suffix else ""}: {error.message}')
    for metric in METRICS:
        seen = set()
        for index, row in enumerate(labels[metric]):
            if type(row['fiscal_year']) is not int or (row['fiscal_quarter'] is not None and type(row['fiscal_quarter']) is not int):
                raise ReviewError(f'{location}.{metric}[{index}]: fiscal identifiers must be integers.')
            key = (row['currency'], row['period_type'], row['fiscal_year'], row['fiscal_quarter'])
            if key in seen:
                raise ReviewError(f'{location}.{metric}[{index}]: duplicate fiscal-period observation.')
            seen.add(key)


def fiscal_period(description):
    """Recognize explicit reviewed fiscal identifiers; never infer from dates.

    None means an explicitly cumulative/YTD period. Unknown or ambiguous labels
    fail closed so an operator can clarify them through the existing review UI.
    """
    if not isinstance(description, str):
        raise ReviewError('Reviewed period description must be text.')
    text = ' '.join(unicodedata.normalize('NFKC', description).casefold().split())
    text = text.replace('–', '-').replace('—', '-')
    year = r'(?P<year>[1-9][0-9]{3})'
    # Closed grammars prevent silently dropping ambiguous quarter/YTD mixtures.
    cumulative = (
        r'(?:six|nine|6|9) (?:fiscal )?months',
        r'(?:two|three|2|3) (?:fiscal )?quarters',
        r'(?:fiscal )?(?:year[ -]to[ -]date|fy[ -]to[ -]date|ytd)',
        r'q1\s*-\s*q[234]',
    )
    for pattern in cumulative:
        if re.fullmatch(pattern + r'(?:\s+(?:fy\s*)?[1-9][0-9]{3})?', text):
            return None
    quarter_patterns = (
        rf'(?:fiscal\s+)?q(?P<quarter>[1-4])\s+(?:fy\s*)?{year}',
        rf'(?:fy\s*)?{year}\s+(?:fiscal\s+)?q(?P<quarter>[1-4])',
        rf'(?P<ordinal>first|second|third|fourth)\s+(?:fiscal\s+)?quarter\s+(?:of\s+)?(?:fy\s*)?{year}',
    )
    for pattern in quarter_patterns:
        match = re.fullmatch(pattern, text)
        if match:
            quarter = (int(match['quarter']) if 'quarter' in match.groupdict() else
                       ('first', 'second', 'third', 'fourth').index(match['ordinal']) + 1)
            return dict(period_type='quarterly', fiscal_year=int(match['year']), fiscal_quarter=quarter)
    annual = re.fullmatch(rf'(?:fy\s*|fiscal year\s+|annual\s+|year\s+){year}', text)
    if annual:
        return dict(period_type='annual', fiscal_year=int(annual['year']), fiscal_quarter=None)
    raise ReviewError(
        f'Ambiguous or unsupported reviewed period {description!r}. Use an explicit fiscal '
        'label such as FY2026 Q3 or FY2026, or an explicit cumulative/YTD label. Dates are not used to infer it.'
    )


def project_labels(labels, *, location='labels'):
    """Project validated human-reviewed v1 labels into quarterly/annual targets."""
    validate_legacy_labels(labels, location=location)
    projected = {metric: [] for metric in METRICS}
    excluded = []
    for metric in METRICS:
        for index, row in enumerate(labels[metric]):
            try:
                period = fiscal_period(row['period'])
            except ReviewError as error:
                raise ReviewError(f'{location}.{metric}[{index}]: {error}') from error
            if period is None:
                excluded.append(dict(metric=metric, source_index=index, period=row['period'], reason='cumulative/YTD'))
            else:
                projected[metric].append(dict(value=row['value'], currency=row['currency'], **period))
    validate_labels(projected, contract=FISCAL_CONTRACT, location=location)
    return deepcopy(projected), excluded


def period_display(row):
    if 'period_type' not in row:
        return row['period']
    return f"FY{row['fiscal_year']}" + (f" Q{row['fiscal_quarter']}" if row['period_type'] == 'quarterly' else '')
