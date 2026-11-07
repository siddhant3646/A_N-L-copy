"""
Apply pattern fixes for questions identified from qa_results.csv audit.
"""

import json
import os
import shutil

PATTERNS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "qa_patterns.json")

def apply_fixes():
    print(f"Loading {PATTERNS_FILE}...")
    with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    patterns = data.get("patterns", {})
    print(f"Total patterns before: {len(patterns)}")

    # Backup
    backup_file = PATTERNS_FILE + ".bak"
    shutil.copyfile(PATTERNS_FILE, backup_file)
    print(f"Backup created at {backup_file}")

    new_patterns = {
        "naukri_registered_mobile_number": {
            "patterns": [
                "what is your naukri registered mobile number?",
                "what is your naukri registered mobile number",
                "naukri registered mobile number?",
                "naukri registered mobile number",
                "registered mobile number?",
                "registered mobile number",
                "registered mobile no?",
                "registered mobile no",
                "registered mobile",
                "registered phone number",
                "what is your registered mobile number",
                "what is your registered mobile number?"
            ],
            "category": "personal_info",
            "default": "7905828880",
            "priority": 25,
            "sensitive": True,
            "requires_exact_match": True,
            "input_type_defaults": {
                "text": "7905828880",
                "number": "7905828880",
                "tel": "7905828880",
                "radio": "7905828880",
                "select": "7905828880",
                "textarea": "7905828880",
                "checkbox": "7905828880"
            }
        },
        "expected_total_compensation_etc": {
            "patterns": [
                "etc ?",
                "etc?",
                "etc",
                "what is your etc?",
                "what is your etc",
                "expected total compensation",
                "expected total compensation (etc)",
                "expected total compensation?",
                "expected total compensation (etc)?"
            ],
            "category": "salary",
            "default": "30 LPA",
            "priority": 25,
            "requires_exact_match": True,
            "negative_patterns": ["current", "cctc", "experience", "years"],
            "input_type_defaults": {
                "text": "30 LPA",
                "number": "30",
                "text_inr": "3000000",
                "textarea": "30 LPA",
                "radio": "30",
                "select": "30 LPA",
                "checkbox": "30",
                "text_lpa": "30"
            },
            "platform_overrides": {
                "linkedin": "3000000",
                "naukri": "3000000",
                "instahyre": "30 LPA",
                "hirist": "30"
            }
        },
        "notice_period_serving_lwd_compound": {
            "patterns": [
                "what is your notice period? if you are currently serving it, please share your last working day.",
                "what is your notice period? if you are currently serving it, please share your last working day",
                "what is your notice period if you are currently serving it please share your last working day",
                "what is your notice period? if currently serving, please share your last working day.",
                "what is your notice period? if currently serving, please share your last working day",
                "notice period if serving please share your last working day",
                "notice period if currently serving please share your last working day",
                "notice period if you are currently serving it",
                "notice period if you are serving it",
                "notice period and last working day",
                "notice period & last working day"
            ],
            "category": "notice_period",
            "default": "15 days (serving notice, LWD: __DYNAMIC_LWD__)",
            "priority": 25,
            "dynamic_answer": True,
            "input_type_defaults": {
                "text": "15 days (serving notice, LWD: __DYNAMIC_LWD__)",
                "textarea": "I am currently serving a 15-day notice period with Last Working Day on __DYNAMIC_LWD__.",
                "radio": "15 Days",
                "select": "15 Days",
                "number": "15",
                "checkbox": "15"
            },
            "platform_overrides": {
                "linkedin": "15",
                "naukri": "15 Days or less",
                "instahyre": "15 days (serving notice, LWD: __DYNAMIC_LWD__)",
                "hirist": "15 Days or less"
            }
        },
        "days_left_in_last_working_day": {
            "patterns": [
                "how many days are left in your last working day?",
                "how many days are left in your last working day",
                "how many days left in your last working day?",
                "how many days left in your last working day",
                "how many days are left for your last working day",
                "how many days left for your last working day",
                "how many days are left until your last working day",
                "how many days left until your last working day",
                "days left in your last working day",
                "days left for your last working day",
                "days left until your last working day",
                "how many days are left in your notice period?",
                "how many days are left in your notice period",
                "how many days left in your notice period?",
                "how many days left in your notice period",
                "days left in notice period"
            ],
            "category": "notice_period",
            "default": "15",
            "priority": 25,
            "input_type_defaults": {
                "text": "15",
                "number": "15",
                "radio": "15",
                "select": "15",
                "textarea": "15",
                "checkbox": "15"
            }
        },
        "can_join_in_15_to_20_days": {
            "patterns": [
                "can you join in 15-20 days ?",
                "can you join in 15-20 days?",
                "can you join in 15-20 days",
                "can you join in 15 to 20 days",
                "can you join in 15 - 20 days",
                "can you join us in 15-20 days",
                "can you join us in 15 to 20 days",
                "able to join in 15-20 days",
                "able to join in 15 to 20 days",
                "available to join in 15-20 days",
                "available to join in 15 to 20 days"
            ],
            "category": "availability",
            "default": "Yes",
            "priority": 25,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "textarea": "Yes, I am currently serving notice and can join within 15-20 days.",
                "checkbox": "Yes",
                "number": "1"
            }
        },
        "immediate_or_notice_period_clarification": {
            "patterns": [
                "are you an immediate joiner ? or any notice period? please mentioned clearly.",
                "are you an immediate joiner ? or any notice period? please mentioned clearly",
                "are you an immediate joiner or any notice period? please mentioned clearly",
                "are you an immediate joiner or any notice period please mentioned clearly",
                "are you an immediate joiner or any notice period",
                "are you an immediate joiner or serving notice period",
                "immediate joiner or any notice period",
                "immediate joiner or notice period"
            ],
            "category": "notice_period",
            "default": "Serving notice period, 15 days",
            "priority": 25,
            "dynamic_answer": True,
            "input_type_defaults": {
                "text": "Serving notice period, 15 days (LWD: __DYNAMIC_LWD__)",
                "textarea": "I am currently serving notice period with 15 days remaining (Last Working Day: __DYNAMIC_LWD__).",
                "radio": "15 Days",
                "select": "15 Days",
                "checkbox": "15",
                "number": "15"
            }
        },
        "java_spring_boot_min_6_years": {
            "patterns": [
                "how many years of hands-on experience do you have with java and spring boot? (minimum 6 years required)",
                "how many years of hands-on experience do you have with java and spring boot (minimum 6 years required)",
                "how many years of hands-on experience do you have with java and spring boot? (minimum 6 years required)*",
                "how many years of hands-on experience do you have with java and spring boot (minimum 6 years required)*",
                "how many years of hands-on experience do you have with java and spring boot",
                "how many years of experience in java and spring boot? (minimum 6 years required)",
                "how many years of experience in java and spring boot (minimum 6 years required)"
            ],
            "category": "experience",
            "default": "4.2 Years",
            "priority": 25,
            "input_type_defaults": {
                "text": "4.2 Years",
                "textarea": "4.2 Years of hands-on experience in Java and Spring Boot developing scalable microservices and REST APIs.",
                "number": "4.2",
                "radio": "4.2",
                "select": "4.2 Years",
                "checkbox": "Yes"
            },
            "platform_overrides": {
                "linkedin": "4",
                "naukri": "4.2 Years",
                "instahyre": "4.2 Years",
                "hirist": "4"
            }
        },
        "java_experience_7_plus_only": {
            "patterns": [
                "how many years do you have experience in java? (7yrs + only apply)",
                "how many years do you have experience in java (7yrs + only apply)",
                "how many years do you have experience in java? (7yrs + only apply)*",
                "how many years do you have experience in java (7yrs + only apply)*",
                "how many years of experience in java? (7yrs + only apply)",
                "how many years of experience in java (7yrs + only apply)"
            ],
            "category": "experience",
            "default": "4.2 Years",
            "priority": 25,
            "input_type_defaults": {
                "text": "4.2 Years",
                "textarea": "4.2 Years of enterprise Java development experience.",
                "number": "4.2",
                "radio": "4.2",
                "select": "4.2 Years",
                "checkbox": "Yes"
            },
            "platform_overrides": {
                "linkedin": "4",
                "naukri": "4.2 Years",
                "instahyre": "4.2 Years",
                "hirist": "4"
            }
        },
        "women_networking_session": {
            "patterns": [
                "are you available for the offline women networking session on 20th nov from 2:30pm?",
                "are you available for the offline women networking session on 20th nov from 2:30pm",
                "are you available for the offline women networking session",
                "offline women networking session on 20th nov",
                "offline women networking session",
                "women networking session",
                "women networking",
                "offline women networking",
                "women only hiring event",
                "women in tech networking session",
                "women in tech networking"
            ],
            "category": "availability",
            "default": "No",
            "priority": 25,
            "input_type_defaults": {
                "radio": "NO",
                "select": "NO",
                "text": "No",
                "textarea": "No",
                "checkbox": "No",
                "number": "0"
            }
        },
        "onsite_working_in_hyderabad": {
            "patterns": [
                "are you working onsite in hyderabad? you may also have to travel to client locations whenever required",
                "are you working onsite in hyderabad you may also have to travel to client locations whenever required",
                "are you working onsite in hyderabad?",
                "are you working onsite in hyderabad",
                "working onsite in hyderabad",
                "are you currently working onsite in hyderabad",
                "working onsite in hyderabad? you may also have to travel to client locations"
            ],
            "category": "location",
            "default": "No, I can relocate to Hyderabad",
            "priority": 25,
            "input_type_defaults": {
                "radio": "No, I can relocate to Hyderabad",
                "select": "No, I can relocate to Hyderabad",
                "text": "No, currently based in Bangalore but willing to relocate to Hyderabad",
                "textarea": "No, I am currently based in Bangalore, Karnataka, but 100% open to relocating to Hyderabad.",
                "checkbox": "No",
                "number": "0"
            }
        },
        "diagnose_app_load_time_slow": {
            "patterns": [
                "app's initial load time is slow. how will you diagnose and improve it ?",
                "app's initial load time is slow. how will you diagnose and improve it",
                "app initial load time is slow how will you diagnose and improve it",
                "app's initial load time is slow",
                "how will you diagnose and improve initial load time"
            ],
            "category": "technical",
            "default": "Profile using Chrome DevTools Performance panel and Lighthouse to find bottlenecks. Analyze JS bundle size using Webpack Bundle Analyzer and implement route-based code splitting and lazy loading. Optimize static assets with image compression and CDN caching. Implement server-side rendering or static generation where appropriate, and minimize render-blocking CSS/JS.",
            "priority": 25,
            "input_type_defaults": {
                "text": "Profile with DevTools/Lighthouse, code split bundles, optimize assets via CDN caching, and lazy load components.",
                "textarea": "Profile using Chrome DevTools Performance panel and Lighthouse to find bottlenecks. Analyze JS bundle size using Webpack Bundle Analyzer and implement route-based code splitting and lazy loading. Optimize static assets with image compression and CDN caching. Implement server-side rendering or static generation where appropriate, and minimize render-blocking CSS/JS.",
                "radio": "Profile with DevTools, code split bundles, and lazy load components.",
                "select": "Profile with DevTools/Lighthouse, code split bundles, optimize assets via CDN caching, and lazy load components.",
                "checkbox": "Yes",
                "number": ""
            }
        },
        "built_from_zero_decisions": {
            "patterns": [
                "tell me about something you built from zero. what decisions did you make and what would you change?",
                "tell me about something you built from zero. what decisions did you make and what would you change",
                "tell me about something you built from zero",
                "something you built from zero"
            ],
            "category": "technical",
            "default": "At Everbridge, I designed and built an event-driven notification dispatch pipeline from scratch using Java, Spring Boot, Apache Kafka, and Redis. Key decisions included asynchronous decoupled processing for high throughput and idempotency keys to prevent duplicate delivery. In hindsight, I would adopt OpenTelemetry distributed tracing earlier for faster cross-service latency debugging.",
            "priority": 25,
            "input_type_defaults": {
                "text": "At Everbridge, I designed and built an event-driven notification dispatch pipeline from scratch using Java, Spring Boot, Kafka, and Redis.",
                "textarea": "At Everbridge, I designed and built an event-driven notification dispatch pipeline from scratch using Java, Spring Boot, Apache Kafka, and Redis. Key decisions included asynchronous decoupled processing for high throughput and idempotency keys to prevent duplicate delivery. In hindsight, I would adopt OpenTelemetry distributed tracing earlier for faster cross-service latency debugging.",
                "radio": "Designed and built an event-driven notification dispatch pipeline from scratch.",
                "select": "Designed and built an event-driven notification pipeline using Java, Spring Boot, Kafka, and Redis.",
                "checkbox": "Yes",
                "number": ""
            }
        },
        "recent_ai_development": {
            "patterns": [
                "what s one ai development you recently learned about, and what did you do with it?",
                "what is one ai development you recently learned about, and what did you do with it?",
                "what is one ai development you recently learned about",
                "one ai development you recently learned about",
                "what's one ai development you recently learned about"
            ],
            "category": "technical",
            "default": "I explored Agentic AI workflows with LLM tool-calling and structured outputs using LangChain and Python. I built automated form filling and contextual Q&A agents using retrieval-augmented generation (RAG) over vector databases to streamline candidate application screening.",
            "priority": 25,
            "input_type_defaults": {
                "text": "I explored Agentic AI workflows with LLM tool-calling and structured outputs using LangChain, building automated form filling and contextual Q&A agents.",
                "textarea": "I explored Agentic AI workflows with LLM tool-calling and structured outputs using LangChain and Python. I built automated form filling and contextual Q&A agents using retrieval-augmented generation (RAG) over vector databases to streamline candidate application screening.",
                "radio": "Agentic AI workflows with LLM tool-calling and structured outputs.",
                "select": "Agentic AI workflows with LLM tool-calling and structured outputs using LangChain and Python.",
                "checkbox": "Yes",
                "number": ""
            }
        },
        "drupal_upgrades_done": {
            "patterns": [
                "what kind of drupal upgrades have you done?",
                "what kind of drupal upgrades have you done",
                "drupal upgrades have you done",
                "drupal upgrades"
            ],
            "category": "technical",
            "default": "None. My core expertise is in Java, Spring Boot, React, Node.js, and distributed microservices.",
            "priority": 25,
            "input_type_defaults": {
                "text": "None / No Drupal experience. My primary expertise is in Java, Spring Boot, React, Node.js, and distributed microservices.",
                "textarea": "None / No Drupal experience. My primary expertise is in Java, Spring Boot, React, Node.js, and distributed microservices.",
                "radio": "None",
                "select": "None / No Drupal experience",
                "checkbox": "No",
                "number": ""
            }
        },
        "software_development_practices_sdlc": {
            "patterns": [
                "software development practices/lifecycle that you are familiar with?",
                "software development practices/lifecycle that you are familiar with",
                "software development practices that you are familiar with",
                "software development lifecycle that you are familiar with"
            ],
            "category": "technical",
            "default": "Agile/Scrum methodologies, Test-Driven Development (TDD) with JUnit and Mockito, CI/CD automated deployment pipelines, Git trunk-based development, microservices architecture, and comprehensive code reviews.",
            "priority": 25,
            "input_type_defaults": {
                "text": "Agile/Scrum, TDD with JUnit/Mockito, CI/CD automated deployment pipelines, Git trunk-based development, and microservices architecture.",
                "textarea": "Agile/Scrum methodologies, Test-Driven Development (TDD) with JUnit and Mockito, CI/CD automated deployment pipelines, Git trunk-based development, microservices architecture, and comprehensive code reviews.",
                "radio": "Agile/Scrum, TDD with JUnit/Mockito, CI/CD pipelines, Git trunk development.",
                "select": "Agile/Scrum, TDD with JUnit/Mockito, CI/CD automated deployment pipelines, Git trunk-based development.",
                "checkbox": "Yes",
                "number": ""
            }
        }
    }

    # Add new patterns
    for pid, pdata in new_patterns.items():
        patterns[pid] = pdata
        print(f"Added/Updated pattern: {pid}")

    # Update existing patterns
    if "full_name" in patterns:
        fn_pats = set(patterns["full_name"].get("patterns", []))
        fn_pats.update([
            "please enter your full name.",
            "please enter your full name",
            "enter your full name.",
            "enter your full name",
            "enter full name",
            "enter your name",
            "candidate full name",
            "candidate name"
        ])
        patterns["full_name"]["patterns"] = list(fn_pats)
        patterns["full_name"]["priority"] = 25
        print("Updated full_name patterns and priority")

    if "contact_phone" in patterns:
        cp_pats = set(patterns["contact_phone"].get("patterns", []))
        cp_pats.update([
            "what is your naukri registered mobile number?",
            "what is your naukri registered mobile number",
            "naukri registered mobile number?",
            "naukri registered mobile number",
            "what is your registered mobile number",
            "registered mobile number",
            "registered mobile no",
            "registered mobile"
        ])
        patterns["contact_phone"]["patterns"] = list(cp_pats)
        print("Updated contact_phone patterns")

    if "last_working_day" in patterns:
        lwd_neg = set(patterns["last_working_day"].get("negative_patterns", []))
        lwd_neg.update(["how many days", "days left"])
        patterns["last_working_day"]["negative_patterns"] = list(lwd_neg)
        print("Updated last_working_day negative_patterns")

    print(f"Total patterns after: {len(patterns)}")
    print(f"Writing to {PATTERNS_FILE}...")
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Done writing qa_patterns.json!")

if __name__ == "__main__":
    apply_fixes()
