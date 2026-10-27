#!/usr/bin/env python3
"""
Apply pattern fixes and additions for questions found in qa_results.csv.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from patterns.input_type_sanitizer import build_input_type_defaults

PATTERNS_FILE = "config/qa_patterns.json"

def apply_fixes():
    print(f"Loading {PATTERNS_FILE}...")
    with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    patterns = data.setdefault("patterns", {})

    # 1. Fix yes_no_do_you_currently
    if "yes_no_do_you_currently" in patterns:
        negs = patterns["yes_no_do_you_currently"].setdefault("negative_patterns", [])
        for w in ["how many", "years", "ctc", "salary", "compensation", "notice", "experience", "yoe", "months", "lpa", "lwd", "last working", "health care", "healthcare"]:
            if w not in negs:
                negs.append(w)
        print("Updated yes_no_do_you_currently negative_patterns")

    # 2. Update salary_current_fixed_variable
    if "salary_current_fixed_variable" in patterns:
        curr_pats = patterns["salary_current_fixed_variable"].setdefault("patterns", [])
        new_fixed_var = [
            "what is your current ctc? base + variable?",
            "what is your current ctc? base + variable",
            "what is your current ctc (fixed + variable) in lpa (lakhs per annum)?",
            "what is your current ctc (fixed + variable) in lpa",
            "what is your current ctc base + variable",
            "what is your current and expected ctc (fixed + variable, annual?)",
            "what is your current and expected ctc (fixed + variable)"
        ]
        for p in new_fixed_var:
            if p not in curr_pats:
                curr_pats.append(p)
        defaults = patterns["salary_current_fixed_variable"].setdefault("input_type_defaults", {})
        defaults["number"] = "23"
        defaults["text_inr"] = "2300000"
        defaults["text_lpa"] = "23"
        print("Updated salary_current_fixed_variable")

    # 3. New patterns dictionary
    new_patterns = {
        "rating_scale_0_to_5_backend": {
            "patterns": [
                "what would be your self-rating on backend with any web frameworks? rate yourself on a scale of (0-5)",
                "what would be your self-rating on database design? rate yourself on a scale of (0-5)",
                "rate yourself on a scale of (0-5) for backend",
                "rate yourself on a scale of (0-5) for java",
                "self-rating on backend with any web frameworks? rate yourself on a scale of (0-5)",
                "self-rating on database design? rate yourself on a scale of (0-5)",
                "rate yourself on a scale of (0-5) on backend"
            ],
            "category": "skills",
            "default": "4",
            "priority": 18,
            "input_type_defaults": {
                "number": "4",
                "text": "4",
                "radio": "4",
                "select": "4",
                "numeric": "4"
            }
        },
        "rating_scale_0_to_5_ai": {
            "patterns": [
                "what would be your self-rating on understanding of frameworks to build ai agents? rate yourself on a scale of (0-5)",
                "what would be your self-rating on llm-based evals? rate yourself on a scale of (0-5)",
                "self-rating on understanding of frameworks to build ai agents? rate yourself on a scale of (0-5)",
                "self-rating on llm-based evals? rate yourself on a scale of (0-5)",
                "rate yourself on a scale of (0-5) for ai agents",
                "rate yourself on a scale of (0-5) for llm evals"
            ],
            "category": "skills",
            "default": "3",
            "priority": 18,
            "input_type_defaults": {
                "number": "3",
                "text": "3",
                "radio": "3",
                "select": "3",
                "numeric": "3"
            }
        },
        "experience_workday_consultant": {
            "patterns": [
                "how many years of experience do you have in workday technical consultant?",
                "how many years of experience do you have in workday technical consultant",
                "how many years of experience do you have in workday integration consultant?",
                "how many years of experience do you have in workday integration consultant",
                "workday technical consultant",
                "workday integration consultant",
                "years of experience in workday",
                "experience in workday",
                "workday experience"
            ],
            "category": "experience",
            "default": "0 Years",
            "priority": 18,
            "input_type_defaults": {
                "text": "0 Years",
                "textarea": "0 Years",
                "number": "0",
                "radio": "0",
                "select": "0"
            }
        },
        "workday_functional_modules": {
            "patterns": [
                "what are the primary modules in workday functional",
                "primary modules in workday functional",
                "workday functional modules"
            ],
            "category": "technical",
            "default": "None",
            "priority": 18,
            "input_type_defaults": {
                "text": "None",
                "textarea": "None",
                "radio": "N/A",
                "select": "N/A",
                "checkbox": "No",
                "number": "N/A"
            }
        },
        "yes_no_workday_experience": {
            "patterns": [
                "do you have experience in workday",
                "have you worked with workday",
                "do you have experience with workday functional",
                "experience with workday"
            ],
            "category": "yes_no",
            "default": "No",
            "priority": 18,
            "input_type_defaults": {
                "radio": "No",
                "select": "No",
                "text": "No",
                "checkbox": "No"
            }
        },
        "experience_healthcare_domain": {
            "patterns": [
                "how many years of health care experience do you currently have (in years)?",
                "how many years of healthcare experience do you currently have (in years)?",
                "how many years of health care experience do you currently have",
                "how many years of healthcare experience do you currently have",
                "years of health care experience",
                "years of healthcare experience",
                "how many years of healthcare experience",
                "how many years of health care experience"
            ],
            "category": "experience",
            "default": "0 Years",
            "priority": 18,
            "input_type_defaults": {
                "number": "0",
                "text": "0 Years",
                "textarea": "0 Years",
                "radio": "0",
                "select": "0"
            }
        },
        "located_in_ahmedabad_gandhinagar": {
            "patterns": [
                "are you currently located in ahmedabad or gandhinagar?",
                "are you currently located in ahmedabad",
                "are you currently located in gandhinagar",
                "currently located in ahmedabad or gandhinagar"
            ],
            "category": "location",
            "default": "No",
            "priority": 18,
            "input_type_defaults": {
                "radio": "No",
                "select": "No",
                "text": "No",
                "textarea": "No, I am currently based in Bengaluru, Karnataka, but open to relocation."
            }
        },
        "currently_servicing_notice_period": {
            "patterns": [
                "are you currently servicing notice period?",
                "are you currently servicing notice period",
                "currently servicing notice period",
                "are you servicing notice period",
                "are you currently serving notice period"
            ],
            "category": "notice_period",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes",
                "textarea": "Yes, I am currently serving notice period with 15 days remaining."
            }
        },
        "experience_gate_8_plus_years": {
            "patterns": [
                "pl confirm if you have overall 8 + yrs and above experience . incase if you have  less than 8 yrs,  your resume will get rejected. kindly pl confirm .",
                "pl confirm if you have overall 8 + yrs and above experience",
                "pl confirm if you have overall 8 + yrs",
                "confirm if you have overall 8+ yrs"
            ],
            "category": "experience",
            "default": "No",
            "priority": 18,
            "input_type_defaults": {
                "radio": "No",
                "select": "No",
                "text": "No"
            }
        },
        "experience_gate_10_to_15_years": {
            "patterns": [
                "we are looking for candidates with 10–15 years of total experience only. candidates with more than 15 years of experience will not be considered?",
                "we are looking for candidates with 10–15 years of total experience only",
                "we are looking for candidates with 10-15 years of total experience only"
            ],
            "category": "experience",
            "default": "No",
            "priority": 18,
            "input_type_defaults": {
                "radio": "No",
                "select": "No",
                "text": "No"
            }
        },
        "experience_req_4_to_9_years": {
            "patterns": [
                "•\t4-9 years of experience in full stack, frontend, or backend software development.",
                "4-9 years of experience in full stack, frontend, or backend software development.",
                "4-9 years of experience in full stack, frontend, or backend software development",
                "4-9 years of experience in full stack"
            ],
            "category": "experience",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "experience_backend_technologies_bullet": {
            "patterns": [
                "•\texperience with backend technologies such as node.js, java spring boot, python, or golang.",
                "experience with backend technologies such as node.js, java spring boot, python, or golang.",
                "experience with backend technologies such as node.js, java spring boot, python, or golang"
            ],
            "category": "technical",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "git_branching_prs_code_reviews": {
            "patterns": [
                "•\thands-on experience with git, including branching strategies, pull requests, and code reviews.",
                "hands-on experience with git, including branching strategies, pull requests, and code reviews.",
                "hands-on experience with git, including branching strategies, pull requests, and code reviews"
            ],
            "category": "technical",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "ai_assisted_tools_copilot_claude": {
            "patterns": [
                "•\thands-on experience with ai-assisted development tools such as github copilot and claude code to accelerate development, code reviews, and test generation.",
                "hands-on experience with ai-assisted development tools such as github copilot and claude code to accelerate development, code reviews, and test generation.",
                "hands-on experience with ai-assisted development tools such as github copilot and claude code"
            ],
            "category": "technical",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "interested_in_full_time_hybrid_bangalore": {
            "patterns": [
                "this is a full time hybrid role for bangalore location, will you be interested?",
                "this is a full time hybrid role for bangalore location",
                "full time hybrid role for bangalore location, will you be interested?"
            ],
            "category": "preference",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "background_check_and_education_verification_consent": {
            "patterns": [
                "as part of the employment process, all candidates are subject to employment and education verification, as well as a comprehensive background check, in accordance with applicable laws and company policies. i understand that i will be provided with additional information and asked to provide authorization before any such checks are conducted.",
                "subject to employment and education verification",
                "subject to employment and education verification, as well as a comprehensive background check"
            ],
            "category": "compliance",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "deloitte_ex_employee_radio": {
            "patterns": [
                "have you ever worked for deloitte & touche, curach, ingeus, str, intelligent energy, or any other de",
                "have you ever worked for deloitte"
            ],
            "category": "compliance",
            "default": "No",
            "priority": 18,
            "input_type_defaults": {
                "radio": "No",
                "select": "No",
                "text": "No, I am not a current/an ex-employee of Deloitte",
                "textarea": "No, I am not a current/an ex-employee of Deloitte"
            }
        },
        "completed_bachelors_degree_aiml_cse_it": {
            "patterns": [
                "have you completed bachelor's degree in aiml/cse/it??",
                "have you completed bachelor's degree in aiml/cse/it",
                "completed bachelor's degree in aiml/cse/it",
                "completed bachelor's degree in cse/it"
            ],
            "category": "education",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "compensation_based_on_market_standards": {
            "patterns": [
                "are you open to considering compensation based on market standards and your skills, experience, and interview performance? (yes/no)",
                "are you open to considering compensation based on market standards",
                "considering compensation based on market standards"
            ],
            "category": "salary",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "ctc_up_to_45_lpa": {
            "patterns": [
                "is your current/expected ctc up to ₹45 lpa?",
                "is your current/expected ctc up to 45 lpa",
                "is your ctc up to 45 lpa",
                "is your current or expected ctc up to 45 lpa"
            ],
            "category": "salary",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "can_go_to_office_for_interview": {
            "patterns": [
                "only apply if you can go to the office for the interview, bangalore",
                "only apply if you can go to the office for the interview",
                "can go to the office for the interview, bangalore"
            ],
            "category": "availability",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes"
            }
        },
        "relatives_employed_by_company": {
            "patterns": [
                "do you have any relatives employed by ping identity? if yes, provide their name below.",
                "do you have any relatives employed by ping identity",
                "do you have any relatives employed by the company",
                "relatives employed by ping identity"
            ],
            "category": "compliance",
            "default": "No",
            "priority": 18,
            "input_type_defaults": {
                "text": "No",
                "textarea": "No",
                "radio": "No",
                "select": "No"
            }
        },
        "exp_capital_market": {
            "patterns": [
                "exp in capital market ? (personal or professional level)",
                "exp in capital market",
                "experience in capital market",
                "experience in capital markets"
            ],
            "category": "experience",
            "default": "Yes, worked on BFSI settlement reporting systems at Everbridge and Fiserv.",
            "priority": 18,
            "input_type_defaults": {
                "text": "Yes, worked on BFSI settlement reporting systems",
                "textarea": "Yes, worked on BFSI and capital market settlement reporting systems at Everbridge and Fiserv.",
                "radio": "Yes",
                "select": "Yes"
            }
        },
        "build_and_deploy_ml_models": {
            "patterns": [
                "have you build and deploy ml models end to end?",
                "have you build and deploy ml models end to end",
                "build and deploy ml models end to end",
                "build and deploy ml models end-to-end"
            ],
            "category": "technical",
            "default": "Yes, built and deployed ML models and LLM agent pipelines using LangChain, Python, and AWS.",
            "priority": 18,
            "input_type_defaults": {
                "text": "Yes, built and deployed ML models and LLM pipelines",
                "textarea": "Yes, built and deployed ML models and LLM pipelines using LangChain, Python, and AWS.",
                "radio": "Yes",
                "select": "Yes"
            }
        },
        "integration_migration_with_products": {
            "patterns": [
                "have you done intigretion or migration with other products?",
                "have you done intigretion or migration with other products",
                "have you done integration or migration with other products?",
                "have you done integration or migration with other products",
                "intigretion or migration with other products"
            ],
            "category": "technical",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes",
                "textarea": "Yes, led product integrations and legacy API migrations to modern Spring Boot microservices."
            }
        },
        "deploy_ml_models_production_project": {
            "patterns": [
                "have you developed and deployed ml models into production? briefly describe one project?",
                "have you developed and deployed ml models into production? briefly describe one project",
                "developed and deployed ml models into production? briefly describe one project"
            ],
            "category": "technical",
            "default": "Yes, developed and deployed an automated document evaluation and summarization pipeline using Python, LangChain, and AWS ECS with 99.9% uptime.",
            "priority": 18,
            "input_type_defaults": {
                "text": "Yes, deployed document evaluation and summarization pipeline using Python and LangChain.",
                "textarea": "Yes, developed and deployed an automated document evaluation and summarization pipeline using Python, LangChain, and AWS ECS with 99.9% uptime.",
                "radio": "Yes",
                "select": "Yes"
            }
        },
        "model_serving_infrastructure": {
            "patterns": [
                "have you worked on model serving infrastructure such as vllm, triton, torchserve, bentoml, or similar frameworks?",
                "have you worked on model serving infrastructure",
                "model serving infrastructure such as vllm, triton, torchserve, bentoml"
            ],
            "category": "technical",
            "default": "Yes, experience with model serving and containerized deployment using Docker, FastAPI, and AWS ECS/Triton.",
            "priority": 18,
            "input_type_defaults": {
                "text": "Yes, worked with FastAPI and Docker for model serving",
                "textarea": "Yes, experience with model serving and containerized deployment using Docker, FastAPI, and AWS ECS/Triton.",
                "radio": "Yes",
                "select": "Yes"
            }
        },
        "weightage_backend_frontend": {
            "patterns": [
                "what is your weightage between backend-frontend?",
                "what is your weightage between backend-frontend",
                "weightage between backend-frontend",
                "weightage between backend and frontend"
            ],
            "category": "preference",
            "default": "70-30",
            "priority": 18,
            "input_type_defaults": {
                "radio": "70-30",
                "select": "70-30",
                "text": "70-30"
            }
        },
        "wfo_alternate_saturdays_comfortable": {
            "patterns": [
                "this is a complete wfo opportunity with alternate saturdays working. are you comfortable with it?",
                "this is a complete wfo opportunity with alternate saturdays working",
                "complete wfo opportunity with alternate saturdays working"
            ],
            "category": "work_mode",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "commute_5_days_a_week": {
            "patterns": [
                "are you okay to commute 5 days a week to office?",
                "are you okay to commute 5 days a week to office",
                "commute 5 days a week to office",
                "commute 5 days to office"
            ],
            "category": "work_mode",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes"
            }
        },
        "built_supported_high_volume_systems": {
            "patterns": [
                "have you built or supported high-volume systems processing millions of transactions?",
                "have you built or supported high-volume systems processing millions of transactions",
                "built or supported high-volume systems processing millions of transactions"
            ],
            "category": "technical",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes",
                "textarea": "Yes, at Everbridge I designed and supported distributed notification pipelines handling over 10 million events daily with 99.99% uptime."
            }
        },
        "rbac_or_row_level_security": {
            "patterns": [
                "have you built role-based access control or row-level security in a production system?",
                "have you built role-based access control or row-level security in a production system",
                "built role-based access control or row-level security in a production system",
                "role-based access control or row-level security"
            ],
            "category": "technical",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes",
                "textarea": "Yes, implemented RBAC and multi-tenant access control using Spring Security, OAuth2, JWT, and PostgreSQL row-level security."
            }
        },
        "experience_production_grade_enterprise_apps": {
            "patterns": [
                "do you have experience developing and maintaining production-grade enterprise applications, including core product features, internal tools, or infrastructure workflows?",
                "do you have experience developing and maintaining production-grade enterprise applications, including",
                "do you have experience developing and maintaining production-grade enterprise applications",
                "experience developing and maintaining production-grade enterprise applications"
            ],
            "category": "technical",
            "default": "Yes",
            "priority": 18,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "checkbox": "Yes",
                "textarea": "Yes, extensive experience building and maintaining production-grade distributed enterprise applications using Java Spring Boot, Kafka, and AWS at Everbridge."
            }
        }
    }

    for pid, pdata in new_patterns.items():
        pdata["input_type_defaults"] = build_input_type_defaults(pdata, pdata.get("input_type_defaults"))
        patterns[pid] = pdata
        print(f"Added pattern: {pid}")

    print(f"Total patterns in memory: {len(patterns)}")
    print(f"Writing to {PATTERNS_FILE}...")
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Done writing qa_patterns.json!")

if __name__ == "__main__":
    apply_fixes()
