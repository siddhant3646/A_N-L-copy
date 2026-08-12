"""Fix linkedin_microsoft_employment_type pattern for better substring matching."""
import json

with open('config/qa_patterns.json', 'r') as f:
    d = json.load(f)

# Update the employment_type pattern with stronger, more specific patterns
d['patterns']['linkedin_microsoft_employment_type']['patterns'] = [
    "if you currently or previously worked at linkedin or microsoft please select the company and employment type",
    "select the company and employment type",
    "linkedin or microsoft company and employment type",
    "linkedin or microsoft employment type",
    "linkedin microsoft employment type",
    "employment type at linkedin or microsoft",
    "employment type at linkedin",
    "employment type at microsoft",
    "which role did you hold at linkedin or microsoft",
    "which role did you hold at linkedin",
    "which role did you hold at microsoft",
    "type of employment at linkedin or microsoft",
    "type of employment at linkedin",
    "type of employment at microsoft",
    "linkedin employee type",
    "microsoft employee type",
    "linkedin contingent worker",
    "microsoft full time employee",
    "microsoft fixed term contractor",
    "microsoft agency temp",
    "microsoft business guest",
    "microsoft vendor contractor outsourced",
    "microsoft intern",
    "microsoft joint venture",
    "linkedin intern employment",
    "linkedin fixed term contract employee",
    "linkedin employee",
    "company and employment type linkedin or microsoft",
    "company and employment type linkedin microsoft",
]

with open('config/qa_patterns.json', 'w') as f:
    json.dump(d, f, indent=2)

print("Updated linkedin_microsoft_employment_type patterns.")
print("New pattern count:", len(d['patterns']['linkedin_microsoft_employment_type']['patterns']))
