import json
from pathlib import Path

P = {}
C = {}

def pat(key, patterns, cat, default, prio=2, exact=False, itd=None):
    d = {"patterns": patterns, "category": cat, "default": default, "priority": prio}
    if itd:
        d["input_type_defaults"] = itd
    else:
        d["input_type_defaults"] = {"radio": default, "select": default, "text": default}
    if exact:
        d["requires_exact_match"] = True
    P[key] = d

def meta(key, desc, fallback, default=None):
    d = {"description": desc, "smart_fallback": fallback}
    if default is not None:
        d["default"] = default
    C[key] = d

# SOFT SKILLS
pat("soft_skills_communication", ["rate your communication skills","how would you rate your communication","communication skills rating","verbal communication proficiency","written communication skills","how good are your communication skills"], "soft_skills", "Excellent")
pat("soft_skills_leadership", ["have you led a team","leadership experience","managed a team","team lead experience","people management experience","have you managed people"], "soft_skills", "Yes")
pat("soft_skills_teamwork", ["how do you work in a team","team collaboration experience","comfortable working in teams","team player","do you prefer team or individual work","cross functional team experience"], "soft_skills", "Yes")
pat("problem_solving_ability", ["how do you approach problem solving","problem solving skills","analytical thinking","approach to debugging","troubleshooting experience","root cause analysis experience"], "soft_skills", "Systematic analytical approach with root cause analysis", itd={"radio":"Yes","select":"Yes","text":"Systematic analytical approach with root cause analysis"})

# SALARY / COMPENSATION
pat("salary_negotiation_willing", ["willing to negotiate salary","open to salary discussion","salary flexible","is your ctc negotiable","can you negotiate your compensation","negotiable salary"], "salary", "Yes")
pat("salary_renegotiation", ["have you renegotiated your salary","salary renegotiation experience","negotiated compensation before","ever negotiated your ctc"], "salary", "No")
pat("expected_salary_range", ["expected salary range","salary range you are looking for","what range of ctc are you expecting","desired compensation range","expected pay range"], "salary", "23-25 LPA")
pat("current_salary_breakup", ["salary breakup","fixed vs variable pay","what is your fixed ctc","what is your variable pay","performance bonus component","retention bonus component"], "salary", "Fixed: 20 LPA, Variable: 3 LPA")
pat("stock_options_equity", ["do you have stock options","esop current","equity compensation","rsu grants","employee stock options","do you receive equity"], "salary", "No")
pat("joining_bonus_expectation", ["expecting joining bonus","joining bonus required","sign on bonus","retention bonus","do you need a joining bonus"], "salary", "No")

# NOTICE / JOINING
pat("notice_period_buyout", ["can you buy out notice period","notice period buyout possible","will you buy out your notice","can you join earlier if buyout","early release with buyout","notice period negotiable with buyout"], "notice_period", "Yes")
pat("immediate_joining", ["can you join immediately","immediate joining possible","can you join within 7 days","join within 15 days","join tomorrow","how soon can you join","earliest joining date"], "notice_period", "Yes")
pat("notice_period_extension", ["can you extend notice period","willing to extend notice","longer notice period acceptable","serve longer notice"], "notice_period", "No")
pat("joining_date_specific", ["what is your exact joining date","specific date you can join","proposed start date","tentative date of joining","date you will be available"], "notice_period", "15 Days")
pat("offer_in_hand", ["do you have any offer in hand","any other offers","holding any offer letter","multiple offers currently","any active offer"], "notice_period", "No")

# INTERVIEW SCHEDULING
pat("interview_scheduling_preference", ["preferred interview time","interview slot preference","when are you available for interview","schedule interview at","best time for interview","interview availability window"], "availability", "Anytime between 10 AM - 6 PM", itd={"radio":"10 AM - 2 PM","select":"10 AM - 2 PM","text":"Anytime between 10 AM - 6 PM"})
pat("interview_time_morning", ["morning slot","morning interview","available in morning","interview before 12 pm"], "availability", "Yes")
pat("interview_slots_weekend", ["weekend interview","interview on saturday","interview on sunday","available on weekend","weekend slot"], "availability", "Yes")
pat("assessment_platform_preference", ["preferred assessment platform","hackerrank","hackerearth","codility","mettl","do you prefer any assessment tool"], "availability", "Any")

# COMPLIANCE / LEGAL
pat("background_check_consent", ["consent to background verification","background check consent","agree to bgv","authorize background check","permit background verification","bgv consent"], "compliance", "Yes")
pat("criminal_record_disclosure", ["any criminal record","criminal history","convicted of any crime","criminal charges","court cases pending"], "compliance", "No")
pat("drug_test_consent", ["willing to take drug test","drug screening consent","pre employment drug test","substance abuse test"], "compliance", "Yes")
pat("service_agreement_consent", ["agree to service agreement","service bond consent","service agreement acceptance","bond undertaking","training agreement consent"], "compliance", "Yes")
pat("data_privacy_consent", ["consent to data processing","gdpr consent","privacy policy acceptance","data sharing consent","personal data usage consent"], "compliance", "Yes")
pat("reference_check_consent", ["consent to reference check","reference verification consent","can we contact your references","reference check authorization"], "compliance", "Yes")

# LINKEDIN / NAUKRI RESUME FIELDS
pat("github_portfolio", ["github profile","github url","portfolio link","code repository link","gitlab profile","personal website"], "skills", "https://github.com/johndoe", itd={"text":"https://github.com/johndoe"})
pat("professional_certifications", ["professional certifications","certifications held","certified in","technical certifications","industry certifications"], "skills", "AWS Certified Solutions Architect, Oracle Certified Professional", itd={"text":"AWS Certified Solutions Architect, Oracle Certified Professional"})
pat("language_proficiency_english", ["english proficiency","english fluency","english speaking level","how well do you speak english"], "skills", "Fluent")
pat("language_proficiency_hindi", ["hindi proficiency","hindi fluency","do you speak hindi","hindi speaking level"], "skills", "Native")
pat("travel_willingness", ["willing to travel","travel percentage","how much travel","business travel ok","comfortable with travel"], "work_mode", "Yes")
pat("onsite_willingness", ["willing to work onsite","onsite work ok","open to onsite","can work from office","comfortable with onsite work"], "work_mode", "Yes")
pat("relocation_package", ["relocation assistance","relocation reimbursement","relocation package","will you need relocation support"], "location", "Yes")
pat("bond_period_duration", ["bond period","service agreement duration","minimum tenure commitment","lock in period","commitment period"], "employment", "1 Year")
pat("non_compete_duration", ["non compete period","non compete agreement duration","restriction period after exit","cooling off period"], "employment", "6 Months")

# NAUKRI PERSONAL
pat("aadhaar_number", ["aadhaar number","aadhaar id","uidai number","aadhar card"], "personal_info", "123456789012", exact=True, itd={"text":"123456789012"})
pat("emergency_contact_name", ["emergency contact name","person to contact in emergency","emergency contact person"], "personal_info", "Emergency Contact", exact=True, itd={"text":"Emergency Contact"})
pat("emergency_contact_phone", ["emergency contact number","emergency contact phone","emergency phone","emergency mobile"], "personal_info", "9876543210", exact=True, itd={"text":"9876543210"})
pat("passport_number", ["passport number","passport id","passport no"], "personal_info", "A1234567", exact=True, itd={"text":"A1234567"})
pat("marital_status", ["marital status","married or single","relationship status"], "personal_info", "Single")
pat("dependents_count", ["number of dependents","dependents","family members","children count"], "personal_info", "0")

# OTHERS
pat("gap_year_explanation", ["career gap","gap in employment","explain gap","break in career","sabbatical","gap year reason"], "employment", "Personal development and upskilling during break", itd={"radio":"Yes","select":"Yes","text":"Personal development and upskilling during break"})
pat("company_blacklist", ["not interested in companies","exclude companies","do not want to apply to","company restriction"], "preference", "None")
pat("diversity_inclusion", ["diversity and inclusion","belong to minority","underrepresented group","diversity candidate"], "self_identification", "Prefer not to say")
pat("pronouns", ["pronouns","preferred pronouns","he she they","gender pronouns"], "self_identification", "He/Him")
pat("work_permit_status", ["work permit","work authorization status","eligible to work","work visa"], "work_authorization", "Yes")
pat("visa_type", ["visa type","current visa","h1b","l1 visa","business visa","travel visa"], "work_authorization", "Not applicable")

# CATEGORIES METADATA
meta("soft_skills", "Soft skills and behavioral traits", True)
meta("compliance", "Legal and compliance consent questions", False)
meta("work_mode", "Work mode preferences and onsite requirements", True, default="Yes")
meta("work_authorization", "Work authorization and visa status", False)
meta("compensation", "Compensation and benefits beyond base salary", True)

# WRITE PAYLOAD
with open("new_patterns_payload.json", "w", encoding="utf-8") as f:
    json.dump({"patterns": P, "categories": C}, f, ensure_ascii=False, indent=2)
print(f"Wrote {len(P)} new patterns and {len(C)} new categories to new_patterns_payload.json")


