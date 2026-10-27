# Analysis script
import csv
from src.patterns.pattern_matcher import create_matcher

matcher = create_matcher()
with open('/Users/siddhant/Desktop/sentinel_errors/qa_results.csv', mode='r', encoding='utf-8', errors='replace') as f:
    rows = list(csv.DictReader(f))

# candidate facts:
# Name: Siddhant Singh
# Phone: +91-7905828880 / 7905828880
# Email: siddhant3646@gmail.com
# Current CTC: 23 LPA / 2300000 / 23
# Expected CTC: 30 LPA / 3000000 / 30
# Total experience: 4.2 years / 4 years / 50 months
# Notice period: 15 days / 15 / serving notice
# Location: Bangalore / Bengaluru / Karnataka / India
# Relocation: Yes
# Work auth India: Yes, no sponsorship required
# Non-compete / disciplinary: No

findings = []

for i, r in enumerate(rows):
    q = r['question'].strip()
    ql = q.lower()
    a = r['answer'].strip()
    opts = [o.strip() for o in r.get('options', '').split(',') if o.strip()]
    sel = r.get('selected_option', '').strip()
    itype = r.get('input_type', '').strip()
    plat = r.get('platform', '')
    src = r.get('source', '')

    errs = []

    # 1. Empty answer
    if not a and not sel:
        errs.append('Empty answer')

    # 2. Expected CTC answered with 23
    if any(k in ql for k in ['expected ctc', 'expected salary', 'ex-ctc', 'ectc', 'exp ctc', 'expected compensation', 'salary expectation']):
        if not any(k in ql for k in ['current', 'cctc', 'c-ctc', 'present']):
            if '23' in a and '30' not in a:
                errs.append(f'Expected CTC answered 23 instead of 30: "{a}"')

    # 3. Current CTC answered with 30
    if any(k in ql for k in ['current ctc', 'current salary', 'cctc', 'c-ctc', 'present ctc', 'present salary']):
        if not any(k in ql for k in ['expected', 'ectc', 'ex-ctc', 'exp ctc']):
            if '30' in a and '23' not in a:
                errs.append(f'Current CTC answered 30 instead of 23: "{a}"')

    # 4. Consent / updates / newsletters answered with dates/emails/numbers
    if any(k in ql for k in ['text/sms', 'sms updates', 'newsletter', 'job openings within', 'allow us to provide you text']):
        if a not in ['Yes', 'No', 'Checked', 'True', 'true', 'yes', 'no']:
            errs.append(f'Consent/communication question answered with non-boolean: "{a}"')

    # 5. Education question answered with degree name when options are Yes/No
    if 'secondary education' in ql or 'bachelor' in ql or 'degree' in ql:
        if opts and set(o.lower() for o in opts) == {'yes', 'no'}:
            if a.lower() not in ['yes', 'no']:
                errs.append(f'Yes/No education question answered with "{a}"')

    # 6. Relocation / location questions with Yes/No options answered with city name
    if opts and set(o.lower() for o in opts) == {'yes', 'no'}:
        if any(k in ql for k in ['located in', 'based in', 'living in', 'residing in']):
            if a.lower() not in ['yes', 'no']:
                errs.append(f'Yes/No location question answered with "{a}"')

    # 7. Yes/No skills questions answered with experience number (e.g. 4)
    if opts and set(o.lower() for o in opts) == {'yes', 'no'}:
        if (ql.startswith('do you have ') or ql.startswith('have you ') or ql.startswith('are you ')) and not any(k in ql for k in ['how many years', 'how much experience', 'number of years']):
            if a in ['4', '4.2', '23', '30', '15', '1', '2', '3', '5']:
                errs.append(f'Yes/No skill question answered with number "{a}"')

    # 8. Experience question answered with boolean Yes/No when options are numbers or text
    if any(k in ql for k in ['how many years', 'years of experience', 'years of total experience', 'experience do you have']):
        if not opts or set(o.lower() for o in opts) != {'yes', 'no'}:
            if a.lower() in ['yes', 'no']:
                errs.append(f'Experience question answered with boolean "{a}"')

    # 9. Radio/Select selected option completely invalid
    if opts and sel and itype in ['radio', 'select']:
        if not any(sel.lower() == o.lower() for o in opts):
            # check if sel is a substring or close
            if not any(sel.lower() in o.lower() or o.lower() in sel.lower() for o in opts):
                errs.append(f'Selected option "{sel}" not in options: {opts}')

    # 10. Sponsorship questions
    if 'sponsorship' in ql and any(k in ql for k in ['require', 'need', 'will you now']):
        if a.lower() in ['yes', 'true', '1']:
            errs.append(f'Sponsorship required answered Yes (should be No): "{a}"')

    # 11. Work authorization
    if 'authorized to work' in ql:
        if a.lower() in ['no', 'false', '0']:
            errs.append(f'Authorized to work answered No (should be Yes): "{a}"')

    # 12. Non-compete, disciplinary, conflict of interest
    if any(k in ql for k in ['non-compete', 'disciplinary', 'conflict of interest', 'cooling period', 'felony', 'crime', 'convicted']):
        if a.lower() in ['yes', 'true', '1']:
            errs.append(f'Negative compliance answered Yes (should be No): "{a}"')

    if errs:
        findings.append({
            'row': i,
            'platform': plat,
            'question': q,
            'answer': a,
            'selected': sel,
            'itype': itype,
            'options': opts,
            'source': src,
            'errors': errs
        })

print(f'Total findings: {len(findings)}')
# Print unique findings by question
seen_q = set()
for f in findings:
    if f['question'] not in seen_q:
        seen_q.add(f['question'])
        print(f"Q: {f['question']}")
        print(f"   Platform: {f['platform']} | Type: {f['itype']} | Opts: {f['options']}")
        print(f"   Answer: {f['answer']} | Sel: {f['selected']} | Src: {f['source']}")
        print(f"   Errors: {f['errors']}")
        print()
