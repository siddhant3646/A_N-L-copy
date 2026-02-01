#!/usr/bin/env python3
"""Debug script to check the generated JavaScript"""

import json

# Copy of KNOWN_QA_PATTERNS from agent.py
KNOWN_QA_PATTERNS = {
    'years of experience': '3.8 Years',
    'months of experience': '46',
    'total experience': '3.8 Years',
    'overall experience': '3.8 Years',
    'year of exp': '3.8 Years',
    'current salary': '13.5 LPA',
    'expected salary': '20 LPA',
    'current ctc': '13.5 LPA',
    'expected ctc': '20 LPA',
    'monthly salary': '112500',
    'expected annual ctc': '20 LPA',
    'current annual ctc': '13.5 LPA',
    'phone number': '7905828880',
    'mobile number': '7905828880',
    'email address': 'siddhant3646@gmail.com',
    'current location': 'Noida',
    'current city': 'Noida',
    'preferred location': 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune',
    'current employer': 'Fiserv',
    'current company': 'Fiserv',
    'previous company': 'Fiserv',
    'notice period': '30 days',
    'serving notice': 'Yes',
    'graduation year': '2022',
    'cgpa': '8.51',
    'percentage': '85',
    'degree': 'B.Tech Computer Science',
    'college name': 'VIT Bhopal University',
    'linkedin url': 'https://www.linkedin.com/in/siddhant3646',
    'github url': 'https://github.com/siddhant3646',
    'willing to relocate': 'Yes',
    'work authorization': 'Yes',
    'legally authorized': 'Yes',
    'background check': 'Yes',
    'drug test': 'Yes',
    'remote work': 'Yes',
    'hybrid work': 'Yes',
    'visa sponsorship': 'No',
    'require sponsorship': 'No',
    'programming languages': 'Java, Python, JavaScript',
    'technical skills': 'Java, Spring Boot, React, AWS, Docker',
    'primary competencies': 'Full Stack Development, Cloud Architecture, System Design',
    'top competencies': 'Full Stack Development, Cloud Architecture, System Design',
    'core competencies': 'Full Stack Development, Cloud Architecture, System Design',
    'key skills': 'Java, Spring Boot, React, AWS, Microservices',
    'top 3 primary competencies': 'Full Stack Development, Cloud Architecture, System Design',
    'face to face interview': 'Yes',
    'f2f interview': 'Yes',
    'available for interview': 'Yes',
    'interested for interview': 'Yes',
    'virtual interview': 'Yes',
    'telephonic interview': 'Yes',
    'interested for f2f interview': 'Yes',
    'available on': 'Yes',
    'contract to hire': 'Yes',
    'c2h position': 'Yes',
    'interested in c2h': 'Yes',
    'contract to hire position': 'Yes',
    'date of birth': '17/12/2000',
    'dob': '17/12/2000',
    'tools used': 'Docker, Kubernetes, Jenkins, GitHub Actions, AWS CloudFormation, Terraform, Ansible, PostgreSQL, MongoDB, Bash, Python',
    'configuration tools': 'Ansible, Terraform, AWS CloudFormation',
    'deployment tools': 'Docker, Kubernetes, Jenkins, GitHub Actions',
    'monitoring tools': 'Prometheus, Grafana, CloudWatch, ELK Stack',
    'automation tools': 'Jenkins, GitHub Actions, Ansible, Terraform',
    'tools used on extensive basis': 'Docker, Kubernetes, Jenkins, GitHub Actions, Terraform, Ansible, PostgreSQL, MongoDB, Bash, Python',
}

patterns_json = json.dumps(KNOWN_QA_PATTERNS)

# Simulate the f-string processing
js_code_template = """function() {{
    // 1. INJECTED KNOWLEDGE
    const KNOWN_PATTERNS = {patterns_json};
    const MAX_RETRIES = 3;
    
    // 2. SHARED UTILS
    const isVisible = (elem) => !!(elem && (elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length));

    return 'TEST_OK';
}}"""

js_code = js_code_template.format(patterns_json=patterns_json)

# Write to file for inspection
with open('generated_js_debug.js', 'w') as f:
    f.write(js_code)

print("Generated JavaScript saved to generated_js_debug.js")
print(f"\nFirst 500 characters:\n{js_code[:500]}")
print(f"\nLast 500 characters:\n{js_code[-500:]}")

# Check for line 290
lines = js_code.split('\n')
if len(lines) >= 290:
    print(f"\n\nLine 290 context:")
    for i in range(max(0, 287), min(len(lines), 293)):
        print(f"{i+1}: {lines[i]}")
else:
    print(f"\n\nFile only has {len(lines)} lines")
