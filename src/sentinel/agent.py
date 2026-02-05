import asyncio
import json
import random
import os
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional, Dict, List, Tuple, Any

from src.sentinel.schemas import (
    ManagerIntent, ActionResult, SentinelState
)
from src.sentinel.prompts import NAUKRI_TASK_CONTEXT
from src.sentinel.question_classifier import (
    QuestionClassifier, classify_question, QuestionCategory, InputType
)
from src.sentinel.question_fingerprint import (
    create_fingerprint, create_fingerprint_hash,
    SuccessTracker, FingerprintMatcher,
    detect_expected_format, validate_answer,
    are_questions_similar
)


# Known question patterns and their answers for fuzzy matching
KNOWN_QA_PATTERNS = {
    # Experience
    'years of experience': '3.8 Years',
    'months of experience': '46',
    'total experience': '3.8 Years',
    'overall experience': '3.8 Years',
    'year of exp': '3.8 Years',
    # Salary (LPA format for Naukri)
    'current salary': '13.5 LPA',
    'what is your current salary?': '13.5 LPA',
    'expected salary': '20 LPA',
    'what is your expected salary?': '20 LPA',
    'gross salary': '13.5 LPA',  # Default to current, will be overridden if "expected" is detected
    'gross current salary': '13.5 LPA',
    'gross expected salary': '20 LPA',
    'salary expectations': '20 LPA',
    # Salary Range Questions - Current: 13.5 LPA, Expected: 20 LPA
    'salary range': '10-15 Lacs',  # For current salary
    'current salary range': '10-15 Lacs',
    'expected salary range': '15-20 Lacs',
    'annual salary': '10-15 Lacs',
    'ctc range': '10-15 Lacs',
    # Personal
    'phone number': '7905828880',
    'mobile number': '7905828880',
    'email address': 'siddhant3646@gmail.com',
    'current location': 'Noida',
    'current city': 'Noida',
    'preferred location': 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune',
    # Company
    'current employer': 'Fiserv',
    'current company': 'Fiserv',
    'previous company': 'Fiserv',
    # Notice
    'notice period': '30 days',
    'serving notice': 'Yes',
    # Education
    'graduation year': '2022',
    'cgpa': '8.51',
    'percentage': '85',
    'degree': 'B.Tech Computer Science',
    'college name': 'VIT Bhopal University',
    # Links
    'linkedin url': 'https://www.linkedin.com/in/siddhant3646',
    'github url': 'https://github.com/siddhant3646',
    # Yes/No common
    'willing to relocate': 'Yes',
    'work authorization': 'Yes',
    'legally authorized': 'Yes',
    'background check': 'Yes',
    'drug test': 'Yes',
    'remote work': 'Yes',
    'hybrid work': 'Yes',
    'visa sponsorship': 'No',
    'require sponsorship': 'No',
    # Walk-in Interview - Always "No" since user is based in Noida
    'available for walk in': 'No, I am currently based in Noida and cannot attend walk-in interviews in other cities on short notice.',
    'walk in on': 'No, I am currently based in Noida and cannot attend walk-in interviews in other cities on short notice.',
    'walk-in': 'No, I am currently based in Noida and cannot attend walk-in interviews in other cities on short notice.',
    'walk in': 'No, I am currently based in Noida and cannot attend walk-in interviews in other cities on short notice.',
    # Employment/Relationship - Always "No"
    'employed by any of the': 'No',
    'currently employed as a': 'No',
    'third party': 'No',
    'temporary employee': 'No',
    'have you ever worked for': 'No',
    'previously employed by': 'No',
    'close relative working': 'No',
    'relative working': 'No',
    'family member working': 'No',
    'family members working': 'No',
    'family members in company': 'No',
    'relatives in company': 'No',
    'relatives working in': 'No',
    'family in company': 'No',
    'conflict of interest': 'No',
    'currently an employee of': 'No',
    # Location Specific Questions - User is in Noida, willing to relocate
    'present location': 'Noida',
    'location': 'Noida',
    'current location': 'Noida',
    'based in': 'Noida',
    'current city': 'Noida',
    'live in': 'Noida',
    'living in': 'Noida',
    'located in': 'Noida',
    'residing in': 'Noida',
    'residence': 'Noida',
    # Location preference questions
    'preferred location': 'Bangalore, Hyderabad, Mumbai, Pune, Delhi NCR',
    'location preference': 'Bangalore, Hyderabad, Mumbai, Pune, Delhi NCR',
    'work location': 'Bangalore, Hyderabad, Mumbai, Pune, Delhi NCR',
    'relocation': 'Yes, open to relocation to any metro city including Bangalore, Hyderabad, Mumbai, Pune, Delhi NCR',
    'willing to relocate': 'Yes, open to relocation to any metro city including Bangalore, Hyderabad, Mumbai, Pune, Delhi NCR',
    'open to relocate': 'Yes, open to relocation to any metro city including Bangalore, Hyderabad, Mumbai, Pune, Delhi NCR',
    'relocate to': 'Yes, open to relocation to any metro city including Bangalore, Hyderabad, Mumbai, Pune, Delhi NCR',
    # Skills
    'programming languages': 'Java, Python, JavaScript',
    'technical skills': 'Java, Spring Boot, React, AWS, Docker',
    # Competencies
    'primary competencies': 'Full Stack Development, Cloud Architecture, System Design',
    'top competencies': 'Full Stack Development, Cloud Architecture, System Design',
    'core competencies': 'Full Stack Development, Cloud Architecture, System Design',
    'key skills': 'Java, Spring Boot, React, AWS, Microservices',
    'top 3 primary competencies': 'Full Stack Development, Cloud Architecture, System Design',
    # Interview
    'face to face interview': 'Yes',
    'f2f interview': 'Yes',
    'available for interview': 'Yes',
    'interested for interview': 'Yes',
    'virtual interview': 'Yes',
    'telephonic interview': 'Yes',
    'interested for f2f interview': 'Yes',
    'available on': 'Yes',
    # Contract to Hire
    'contract to hire': 'Yes',
    'c2h position': 'Yes',
    'interested in c2h': 'Yes',
    'contract to hire position': 'Yes',
    # Date of Birth
    'date of birth': '17/12/2000',
    'dob': '17/12/2000',
    # DevOps / Tools
    'tools used': 'Docker, Kubernetes, Jenkins, GitHub Actions, AWS CloudFormation, Terraform, Ansible, PostgreSQL, MongoDB, Bash, Python',
    'configuration tools': 'Ansible, Terraform, AWS CloudFormation',
    'deployment tools': 'Docker, Kubernetes, Jenkins, GitHub Actions',
    'monitoring tools': 'Prometheus, Grafana, CloudWatch, ELK Stack',
    'automation tools': 'Jenkins, GitHub Actions, Ansible, Terraform',
    'tools used on extensive basis': 'Docker, Kubernetes, Jenkins, GitHub Actions, Terraform, Ansible, PostgreSQL, MongoDB, Bash, Python',
    # CI/CD
    'ci/cd setup': 'Yes, deployed React and Angular applications using Jenkins, GitHub Actions, and AWS CodePipeline with automated testing and deployment to S3/CloudFront',
    'frontend ci/cd': 'Yes, implemented CI/CD pipelines for React applications using GitHub Actions with automated builds, tests, and deployments to AWS S3 and CloudFront',
    'deployed frontend': 'Yes, deployed multiple React and Angular frontend applications using CI/CD pipelines with automated testing and CDN deployment',
    'deployed frontend applications': 'Yes',
    # Security
    'frontend security': 'Implemented CSP headers, XSS prevention, CSRF tokens, secure cookie handling, input sanitization, HTTPS enforcement, and OAuth2/JWT authentication',
    'security practices': 'CSP headers, XSS prevention, CSRF protection, input sanitization, secure authentication with OAuth2/JWT, HTTPS enforcement',
    'frontend security practices': 'CSP headers, XSS prevention, CSRF protection, input sanitization, OAuth2/JWT authentication',
    # Trading / Blockchain
    'trading platform': 'Built high-performance microservices handling real-time data processing with event-driven architecture using Kafka, Redis caching, and WebSocket for live updates - similar patterns used in trading systems for low-latency data flow',
    'blockchain platform': 'Developed distributed systems with event sourcing patterns, immutable audit logs, and cryptographic verification - architectural patterns aligned with blockchain fundamentals',
    'real-time system': 'Implemented real-time notification systems and live dashboards using WebSocket, Redis Pub/Sub, and event-driven microservices with sub-second latency',
    'real-time trading': 'Built event-driven microservices with Kafka and Redis for low-latency real-time data processing, similar to trading platform patterns',
    # Enterprise Platforms
    'enterprise platforms': 'Yes, worked with Google Cloud Platform, Microsoft Azure, AWS, and integrated with enterprise systems including Salesforce and ServiceNow APIs',
    'diverse platforms': 'Yes, have experience with Google Cloud, Microsoft Azure, AWS, Salesforce integration, and ServiceNow API development',
    'diverse enterprise platforms': 'Yes',
    'exposure to diverse enterprise platforms': 'Yes',
    # Shift Timings
    'comfortable working in shift': 'Yes',
    'shift timing': 'Yes',
    'night shift': 'Yes',
    'rotational shift': 'Yes',
    # TCS Registration & PAN
    'pan number': 'MTKPS1941P',
    'pan card number': 'MTKPS1941P',
    'pan card': 'MTKPS1941P',
    'mention your pan card number': 'MTKPS1941P',
    'mention your pan number': 'MTKPS1941P',
    'your pan card number': 'MTKPS1941P',
    'your pan number': 'MTKPS1941P',
    'name as per pan': 'Siddhant Singh',
    'name as per pan card': 'Siddhant Singh',
    'mention your name as per pan': 'Siddhant Singh',
    'your name as per pan card': 'Siddhant Singh',
    'date of birth as per pan': '17/12/2000',
    # Aadhar Details
    'name as per aadhar': 'Siddhant Singh',
    'first name as per aadhar': 'Siddhant',
    'last name as per aadhar': 'Singh',
    'first name:last name': 'Siddhant Singh',
    'aadhar first name': 'Siddhant',
    'aadhar last name': 'Singh',
    'current payroll company': 'Fiserv, First Name: Siddhant, Last Name: Singh',
    'payroll company': 'Fiserv',
    'registered in tcs': 'No',
    'tcs registration': 'N/A',
    'registered in tata consultancy': 'No',
    # REST APIs
    'restful apis': 'Yes',
    'designed and developed restful apis': 'Yes',
    'rest api': 'Yes',
    'production systems': 'Yes',
    # Docker/Kubernetes
    'docker or kubernetes': 'Yes',
    'docker': 'Yes',
    'kubernetes': 'Yes',
    'hands-on exposure to docker': 'Yes',
    'exposure to docker or kubernetes': 'Yes',
    # Kafka
    'kafka': 'Yes',
    'exp in kafka': 'Yes',
    'experience in kafka': 'Yes',
    # Location
    'city': 'Noida',
    'home address': 'Noida',
    'currently located': 'Noida',
    'where are you located': 'Noida',
    # On-site / Availability
    'available to work full-time on-site': 'Yes',
    'full-time on-site': 'Yes',
    # Experience Details
    'years of work experience do you have in your chosen engineering field': '4',
    'experience in your chosen engineering field': '4',
    'area have you most experience in': 'Full-stack',
    'area of most experience': 'Full-stack',
    # Interview Scheduling & Preferences
    'prefer gurgaon': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'prefer bangalore': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'prefer mumbai': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'prefer pune': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'prefer hyderabad': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'prefer chennai': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'prefer kolkata': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'preferred city': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'city preference': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'interview city': 'All cities are fine - Gurgaon, Bangalore, Mumbai, Pune, Hyderabad, Chennai, Kolkata',
    'tentative dates': 'Any slot available - flexible with dates and times on weekdays',
    'time slots': 'Any slot available - flexible with dates and times on weekdays',
    'video interview': 'Yes, available for video interview - any slot works',
    'interview slot': 'Any slot available - flexible with dates and times on weekdays',
    'interview availability': 'Any slot available - flexible with dates and times on weekdays',
    'weekday interview': 'Yes, available on any weekday - flexible with timing',
    '2 tentative dates': 'Any slot available - flexible with dates and times on weekdays',
    'dates and time slots': 'Any slot available - flexible with dates and times on weekdays',
    # Reason for Job Change
    'reason for job change': 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals',
    'why job change': 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals',
    'why are you looking': 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals',
    'why switching': 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals',
    'reason for leaving': 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals',
    # Gen AI / AI Tools
    'gen ai tool': 'Yes, I use GitHub Copilot and ChatGPT for code generation, debugging, documentation, and learning new technologies',
    'ai tool you used': 'GitHub Copilot for code completion and ChatGPT for problem-solving, debugging, and documentation',
    'generative ai tool': 'GitHub Copilot and ChatGPT for code generation, debugging, and improving productivity',
    # Hiring Manager Message
    'message to the hiring manager': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    'message to hiring manager': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    'your message': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    'cover letter': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    'message': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    'why are you interested': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    'why do you want': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    'additional information': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    'comments': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    # CTC in Lakhs (for questions specifically asking in lakhs/LPA)
    'current ctc in lakhs': '13.5',
    'current ctc in lpa': '13.5',
    'current ctc [in lpa]': '13.5',
    'current ctc(in lpa)': '13.5',
    'current ctc (in lpa)': '13.5',
    'ctc in lacs per annum': '13.5',
    'ctc in lacs': '13.5',
    'expected ctc in lakhs': '20',
    'expected ctc in lpa': '20',
    'expected ctc [in lpa]': '20',
    'ctc in lakhs': '20',
    # CCTC = Current CTC (abbreviation)
    'cctc': '13.5',
    'what is your cctc': '13.5',
    'your cctc': '13.5',
    # ECTC = Expected CTC (abbreviation)
    'ectc': '20',
    'what is your ectc': '20',
    'your ectc': '20',
    # NP = Notice Period (abbreviation)
    'what is your np': '30',
    'your np': '30',
    'mention np': '30',
    # US Customer Communication / English Fluency
    'talking to us customers': 'Yes, I have 3.8+ years of experience working with US-based clients, conducting daily standups and demos. I am fluent in English with clear communication skills.',
    'flawless english': 'Yes, I have excellent English communication skills with experience in client-facing roles with US-based teams.',
    'neutral accent english': 'Yes, I am fluent in English with clear communication. I regularly interact with US-based clients and stakeholders.',
    'confidence in talking': 'Yes, I have 3.8+ years of experience working with international clients, comfortable with daily video calls and presentations.',
    # Product Based / BFSI Domain
    'product based': 'Yes, I have experience working at Fiserv which is a product-based company in the BFSI domain.',
    'bfsi domain': 'Yes, I am currently working at Fiserv in the BFSI (Banking, Financial Services, Insurance) domain with 3.8 years of experience.',
    'bfsi': 'Yes',
    'fintech': 'Yes',
    'banking domain': 'Yes',
    # WFO / 5 Days Office
    '5 days working from office': 'Yes',
    '5 days wfo': 'Yes',
    'comfortable for 5 days': 'Yes',
    'working from office': 'Yes',
    'wfo': 'Yes',
    # TCS EP Number
    'tcs registration no': 'N/A - Not registered in TCS',
    'ep no': 'N/A',
    'ep number': 'N/A',
    # Angular + Microservices Experience
    'exp in angular and microservices': '3.8 years experience in both Angular and Microservices architecture',
    'exp. in angular': '3.8 years',
    # Notice Period Negotiation
    'notice period negotiated': 'Yes',
    'notice period that must be served': 'Yes',
    'can it be negotiated': 'Yes',
    'negotiated with your current employer': 'Yes',
    'negotiate notice period': 'Yes',
    # Salary Acceptance
    'willing to accept': 'Yes',
    'accept an annual salary': 'Yes',
    'salary of between': 'Yes',
    'based upon your experience': 'Yes',
    'accept salary': 'Yes',
    'accept the compensation': 'Yes',
    # Technical Assessment
    'technical assessment': 'Yes',
    'available to take a technical assessment': 'Yes',
    'take a technical assessment': 'Yes',
    'coding assessment': 'Yes',
    'online assessment': 'Yes',
    'available for assessment': 'Yes',
    # Assessment Date / When can we send
    'what date can we send': 'Any weekday works - I am flexible with the date and time',
    'when can we send you the assessment': 'Any weekday works - I am flexible with the date and time',
    'send you the technical assessment': 'Any weekday works - I am flexible with the date and time',
    'date for technical assessment': 'Any weekday works - I am flexible with the date and time',
    'preferred date': 'Any weekday works - I am flexible with the date and time',
    'what date': 'Any weekday works - I am flexible with the date and time',
    # Additional Skip Patterns
    'no worries': '',
    'you can change your input': '',
    'change your input': '',
    # Skip patterns (return empty to trigger skip)
    'skip this question': '',
    'try again': '',
    'restart conversation': '',
    # Proficiency/Rating Questions (1-10 scale)
    'rate proficiency': '8',
    'rate your proficiency': '8',
    'proficiency in typescript': '8',
    'proficiency in javascript': '9',
    'proficiency in react': '8',
    'proficiency in java': '9',
    'proficiency in python': '8',
    'proficiency in angular': '7',
    'proficiency in node': '8',
    'proficiency in aws': '7',
    'proficiency in sql': '8',
    'rate yourself': '8',
    'rate on a scale': '8',
    'on a scale of 1-10': '8',
    'on a scale of 1 to 10': '8',
    '1-10': '8',
    '1 to 10': '8',
    # Preferred Position / Role
    'preferred position': 'Backend',
    'frontend/backend': 'Backend',
    'frontend or backend': 'Backend',
    'frontend backend': 'Backend',
    'preferred role': 'Backend',
    'which role': 'Backend Developer',
    'preferred domain': 'Backend Development',
    # Database Knowledge
    'strong knowledge in db': 'Yes',
    'knowledge in db': 'Yes',
    'database knowledge': 'Yes',
    'db knowledge': 'Yes',
    'database experience': 'Yes',
    'sql knowledge': 'Yes',
    'must have strong knowledge': 'Yes',
    # DSA / Data Structures
    'how good are you in dsa': '8 - Strong understanding of data structures and algorithms with hands-on problem solving experience',
    'dsa': '8',
    'dsa skills': '8',
    'data structures and algorithms': '8',
    'data structures': '8',
    'algorithms': '8',
    'problem solving': 'Strong - regularly practice on LeetCode and HackerRank',
    'competitive programming': '8',
    'coding skills': '8',
    # Tech Stacks / Python Libraries
    'tech stack': 'Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis',
    'major tech stack': 'Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis',
    'tech-stack': 'Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis',
    'worked upon': 'Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis',
    'python libraries': 'NumPy, Pandas, FastAPI, Flask, SQLAlchemy, Celery, PyTorch, TensorFlow, Scikit-learn, LangChain, OpenAI',
    'which python libraries': 'NumPy, Pandas, FastAPI, Flask, SQLAlchemy, Celery, PyTorch, TensorFlow, Scikit-learn, LangChain, OpenAI',
    'python packages': 'NumPy, Pandas, FastAPI, Flask, SQLAlchemy, Celery, PyTorch, TensorFlow, Scikit-learn, LangChain, OpenAI',
    # Location-Specific Questions
    'based in bangalore': 'No, I am currently based in Noida. However, I am willing to relocate to Bangalore.',
    'based in mumbai': 'No, I am currently based in Noida. However, I am willing to relocate to Mumbai.',
    'based in pune': 'No, I am currently based in Noida. However, I am willing to relocate to Pune.',
    'based in hyderabad': 'No, I am currently based in Noida. However, I am willing to relocate to Hyderabad.',
    'based in chennai': 'No, I am currently based in Noida. However, I am willing to relocate to Chennai.',
    'from mumbai': 'No, I am currently based in Noida. However, I am willing to relocate.',
    'where do you stay': 'Noida, Delhi NCR',
    'stay currently': 'Noida, Delhi NCR',
    # Referral / Encouraged to Apply
    'referred for this position': 'No',
    'referred by': 'No',
    'employee referral': 'No',
    'encouraged to apply': 'No',
    'digicert employee': 'No',
    # Job Change Reasons
    'reasons for your job change': 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals',
    # Total Experience (short forms)
    'total exp': '3.8 Years',
    'your total exp': '3.8 Years',
    'what is your total exp': '3.8 Years',
    # Database Names (not experience years)
    'which database': 'PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB',
    'what database': 'PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB',
    'database do you have experience': 'PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB',
    'database experience working': 'PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB',
    'databases have you worked': 'PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB',
    # Project Count
    'how many projects': '5',
    'number of projects': '5',
    'projects you have worked': '5',
    'projects worked on': '5',
    'projects as fullstack': '5',
    # Yes/No Proficiency (not rating)
    'strong proficiency': 'Yes',
    'good grasp': 'Yes',
    'do you have proficiency': 'Yes',
    'do you have experience in etl': 'Yes',
    'good grasp of etl': 'Yes',
    'etl concepts': 'Yes',
    # E-commerce Domain Experience
    'e-commerce experience': 'Yes, I have experience building scalable e-commerce platforms with payment gateway integration (Stripe, Razorpay), inventory management, order processing, and real-time tracking systems.',
    'experience in e-commerce': 'Yes, I have experience building scalable e-commerce platforms with payment gateway integration (Stripe, Razorpay), inventory management, order processing, and real-time tracking systems.',
    'ecommerce experience': 'Yes, I have experience building scalable e-commerce platforms with payment gateway integration (Stripe, Razorpay), inventory management, order processing, and real-time tracking systems.',
    # Composite HR Questions (CTC + ECTC + NP)
    'share your ctc': 'Current CTC: 13.5 LPA, Expected CTC: 20 LPA, Notice Period: 30 Days (Negotiable)',
    'ctc ectc np': 'Current CTC: 13.5 LPA, Expected CTC: 20 LPA, Notice Period: 30 Days (Negotiable)',
    'ctc and np': 'Current CTC: 13.5 LPA, Expected CTC: 20 LPA, Notice Period: 30 Days (Negotiable)',
    'ctc,ectc and np': 'Current CTC: 13.5 LPA, Expected CTC: 20 LPA, Notice Period: 30 Days (Negotiable)',
    # Location-exclusive questions (Mumbai-only, etc.)
    'candidates from mumbai': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    'need candidates from mumbai': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    'from mumbai itself': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    'stay currently in mumbai': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    'andheri mumbai': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
}

FUZZY_MATCH_THRESHOLD = 0.6  # Minimum similarity score to consider a match


class SentinelAgent:
    """
    Sentinel Agent - 100% Scripted Browser Automation.
    Operates on DOM to control a browser without LLM calls.
    """
    
    MAX_STEPS_LINKEDIN = 120  # LinkedIn tasks get more steps
    MAX_STEPS_DEFAULT = 50    # All other tasks
    MEMORY_CLEANUP_INTERVAL = 50  # Refresh context every N steps
    SCREENSHOT_DIR = os.path.expanduser("~/Desktop/sentinel_errors")
    UNKNOWN_QUESTIONS_LOG = os.path.expanduser("~/Desktop/sentinel_errors/unknown_questions.log")
    ALL_QUESTIONS_LOG = os.path.expanduser("~/Desktop/sentinel_errors/all_questions.log")
    METRICS_LOG = os.path.expanduser("~/Desktop/sentinel_errors/metrics.jsonl")
    
    def __init__(self, browser=None):
        self.browser = browser
        self._page = None  # Set by runner
        self.state = SentinelState()
        self.linkedin_applications = 0
        self.linkedin_rate_limit_until = None  # Timestamp when LinkedIn can resume
        self.naukri_rate_limit_until = None  # Timestamp when Naukri can resume
        self._task_context = NAUKRI_TASK_CONTEXT
        self._steps_since_cleanup = 0  # Track steps for memory cleanup
        self._logged_questions = set()  # Track already logged questions to avoid duplicates
        self._all_logged_questions = set()  # Track questions logged to all_questions.log
        self._last_result = ""  # Track last result for loop detection
        self._same_result_count = 0  # Counter for repeated results
        
        # Metrics tracking
        self.metrics = {
            'task_name': '',
            'start_time': None,
            'end_time': None,
            'applications_submitted': 0,
            'questions_answered': 0,
            'errors_encountered': 0,

            'login_prompts': 0,
            'steps_taken': 0,
            'success': False
        }
        
        # Question classifier for smart defaults
        self._question_classifier: Optional[QuestionClassifier] = None
        self._current_platform: str = "default"
        
        # Fingerprint matcher and success tracker
        self._fingerprint_matcher = FingerprintMatcher()
        self._fingerprint_matcher.build_from_patterns(KNOWN_QA_PATTERNS)
        self._success_tracker = SuccessTracker()
        
        # Ensure screenshot directory exists
        os.makedirs(self.SCREENSHOT_DIR, exist_ok=True)

    def _detect_platform(self) -> str:
        """Detect current platform from URL or context."""
        try:
            if self._page:
                url = self._page.url.lower()
                if 'linkedin.com' in url:
                    return 'linkedin'
                elif 'naukri.com' in url:
                    return 'naukri'
                elif 'instahyre.com' in url:
                    return 'instahyre'
        except:
            pass
        return self._current_platform

    def _fuzzy_match_question(self, question: str) -> Tuple[Optional[str], float]:
        """Find closest known question pattern using improved keyword + fuzzy matching."""
        # Update platform detection before processing
        self._current_platform = self._detect_platform()
        
        question_lower = question.lower().strip()
        best_match = None
        best_score = 0.0
        
        # ==========================================
        # PHASE 0: Skip Patterns (highest priority)
        # ==========================================
        skip_patterns = ['skip this question', 'try again', 'restart conversation', 'no worries', 'change your input']
        if any(skip in question_lower for skip in skip_patterns):
            return '', 1.0  # Return empty string to trigger skip
        
        # ==========================================
        # PHASE 0.5: Fingerprint Matching
        # Normalize questions to match variations
        # ==========================================
        if self._fingerprint_matcher:
            fp_match = self._fingerprint_matcher.match(question)
            if fp_match:
                answer, confidence = fp_match
                # Validate answer format
                format_type = detect_expected_format(question)
                if format_type:
                    is_valid, error_msg = validate_answer(answer, format_type)
                    if not is_valid:
                        print(f"   ⚠️ Fingerprint match failed validation: {error_msg}")
                    else:
                        print(f"   🔍 Fingerprint match (conf: {confidence:.2f}): {answer[:50]}...")
                        return answer, confidence
                else:
                    print(f"   🔍 Fingerprint match (conf: {confidence:.2f}): {answer[:50]}...")
                    return answer, confidence
        
        # ==========================================
        # PHASE 1: Keyword-based Priority Matching
        # Prevents CTC questions matching experience patterns
        # ==========================================
        
        # Define keyword categories for priority matching
        salary_keywords = ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc']
        experience_keywords = ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp']
        notice_keywords = ['notice', 'serving', 'join', 'availability']
        location_keywords = ['location', 'city', 'relocate', 'preferred location']
        
        # LWD (Last Working Day) detection - BEFORE experience keywords
        lwd_keywords = ['last working day', 'lwd', 'exact lwd', 'exact last working']
        is_lwd_question = any(kw in question_lower for kw in lwd_keywords)
        
        # NP abbreviation detection (Notice Period) - special handling
        np_keywords = ['your np', 'what is your np', 'mention np', 'np?']
        is_np_abbreviation = any(kw in question_lower for kw in np_keywords)
        
        # Rating/Proficiency questions (1-10 scale) - CHECK BEFORE EXPERIENCE
        rating_keywords = ['rate proficiency', 'rate yourself', 'rate your', 'on a scale', '1-10', '1 to 10', 'proficiency in']
        is_rating_question = any(kw in question_lower for kw in rating_keywords)
        
        # Preferred position questions
        position_keywords = ['preferred position', 'frontend/backend', 'frontend or backend', 'preferred role', 'which role']
        is_position_question = any(kw in question_lower for kw in position_keywords)
        
        # Database/Knowledge questions
        db_knowledge_keywords = ['knowledge in db', 'strong knowledge', 'database knowledge', 'db knowledge']
        is_db_question = any(kw in question_lower for kw in db_knowledge_keywords)
        
        # DSA questions
        dsa_keywords = ['dsa', 'data structures', 'algorithms', 'how good are you']
        is_dsa_question = any(kw in question_lower for kw in dsa_keywords)
        
        # Tech stacks / Python libraries questions - MUST CHECK BEFORE EXPERIENCE
        tech_stack_keywords = ['tech stack', 'tech-stack', 'technologies worked', 'worked upon', 'major tech']
        python_lib_keywords = ['python libraries', 'python library', 'python libs', 'python packages', 'which python']
        is_tech_question = any(kw in question_lower for kw in tech_stack_keywords)
        is_python_lib_question = any(kw in question_lower for kw in python_lib_keywords)
        
        # Database NAME questions (not experience) - CHECK BEFORE EXPERIENCE
        db_name_keywords = ['which database', 'what database', 'database do you have', 'database have you', 'database experience working', 'database worked', 'databases do you', 'databases have you']
        is_db_name_question = any(kw in question_lower for kw in db_name_keywords)
        
        # Location specific questions - "based in X", "located in X", "from X", "stay in X"
        location_specific_keywords = ['based in', 'located in', 'from mumbai', 'from bangalore', 'from pune', 'from hyderabad', 'from chennai', 'from delhi', 'stay currently', 'where do you stay', 'which city do you', 'candidates from', 'need candidates from', 'andheri']  # Added Mumbai-specific patterns
        is_location_specific = any(kw in question_lower for kw in location_specific_keywords)
        
        # Referral questions - "referred by", "encouraged to apply"
        referral_keywords = ['referred', 'referral', 'encouraged to apply', 'employee referral', 'referred by']
        is_referral_question = any(kw in question_lower for kw in referral_keywords)
        
        # Job change reason questions
        job_change_keywords = ['reason for job change', 'reasons for job change', 'reasons for your job change', 'why are you changing', 'why job change', 'reason for leaving', 'reason for change']
        is_job_change_question = any(kw in question_lower for kw in job_change_keywords)
        
        # Total experience question (short form like "total Exp")
        total_exp_keywords = ['total exp', 'what is your total exp']
        is_total_exp_question = any(kw in question_lower for kw in total_exp_keywords) and 'ctc' not in question_lower
        
        # Project count questions
        project_count_keywords = ['how many projects', 'number of projects', 'projects you have worked', 'projects as fullstack']
        is_project_count = any(kw in question_lower for kw in project_count_keywords)
        
        # Yes/No Proficiency questions (NOT rating scale)
        yes_no_proficiency_keywords = ['strong proficiency', 'good grasp', 'do you have proficiency', 'etl concepts', 'good understanding of']
        is_yes_no_proficiency = any(kw in question_lower for kw in yes_no_proficiency_keywords)
        
        # E-commerce domain experience
        ecommerce_keywords = ['e-commerce', 'ecommerce', 'e commerce']
        is_ecommerce_question = any(kw in question_lower for kw in ecommerce_keywords) and ('experience' in question_lower or 'worked' in question_lower)
        
        # Composite HR question (CTC + ECTC + NP in one)
        is_composite_hr = ('ctc' in question_lower and ('np' in question_lower or 'notice' in question_lower or 'ectc' in question_lower))
        
        # Country/State questions
        country_keywords = ['country you currently', 'which country', 'country currently', 'state you', 'which state']
        is_country_question = any(kw in question_lower for kw in country_keywords)
        
        # Handle high-priority question types FIRST
        
        # Composite HR question (must check BEFORE individual NP/salary)
        if is_composite_hr:
            return 'Current CTC: 13.5 LPA, Expected CTC: 20 LPA, Notice Period: 30 Days (Negotiable)', 0.98
        
        # NP abbreviation (Notice Period) - after composite check
        if is_np_abbreviation:
            return '30', 0.98
        
        # LWD (Last Working Day) questions - calculate date 30 days from now
        if is_lwd_question:
            lwd_date = datetime.now() + timedelta(days=30)
            return lwd_date.strftime('%d %B %Y'), 0.98  # e.g., "01 March 2026"
        
        # Project count questions
        if is_project_count:
            return '5', 0.98
        
        # Yes/No Proficiency (must be BEFORE rating questions)
        if is_yes_no_proficiency:
            return 'Yes', 0.98
        
        # E-commerce experience (must be BEFORE generic experience)
        if is_ecommerce_question:
            return 'Yes, I have experience building scalable e-commerce platforms with payment gateway integration (Stripe, Razorpay), inventory management, order processing, and real-time tracking systems.', 0.98
        
        if is_rating_question:
            return '8', 0.95
        
        if is_position_question:
            return 'Backend', 0.95
        
        if is_db_question:
            return 'Yes', 0.95
        
        if is_dsa_question:
            return '8', 0.95
        
        # Handle tech stack and python library questions - BEFORE experience check
        if is_python_lib_question:
            return 'NumPy, Pandas, FastAPI, Flask, SQLAlchemy, Celery, PyTorch, TensorFlow, Scikit-learn, LangChain, OpenAI', 0.95
        
        if is_tech_question:
            return 'Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis', 0.95
        
        # Handle database NAME questions - BEFORE experience check
        if is_db_name_question:
            return 'PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB', 0.95
        
        # Handle location-specific questions
        if is_location_specific:
            # Check for Mumbai-only/exclusivity requirements
            if ('mumbai' in question_lower or 'andheri' in question_lower) and ('need candidates from' in question_lower or 'candidates from mumbai' in question_lower or 'from mumbai itself' in question_lower):
                return 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.', 0.95
            # Check for specific city mentions
            if 'bangalore' in question_lower or 'bengaluru' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Bangalore.', 0.95
            if 'mumbai' in question_lower or 'andheri' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Mumbai.', 0.95
            if 'pune' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Pune.', 0.95
            if 'hyderabad' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Hyderabad.', 0.95
            if 'chennai' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Chennai.', 0.95
            if 'delhi' in question_lower or 'ncr' in question_lower or 'noida' in question_lower or 'gurgaon' in question_lower or 'gurugram' in question_lower:
                return 'Yes, I am currently based in Noida, Delhi NCR.', 0.95
            return 'Noida, Delhi NCR', 0.95
        
        # Handle referral questions
        if is_referral_question:
            return 'No', 0.95
        
        # Handle job change reason questions
        if is_job_change_question:
            return 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals', 0.95
        
        # Handle total experience (short form) questions
        if is_total_exp_question:
            return '3.8 Years', 0.95
        
        # Handle country/state questions
        if is_country_question:
            return 'India', 0.95
        
        # Check which category the question falls into
        is_salary_question = any(kw in question_lower for kw in salary_keywords)
        is_experience_question = any(kw in question_lower for kw in experience_keywords) and not is_salary_question and not is_rating_question and not is_tech_question and not is_python_lib_question
        is_notice_question = any(kw in question_lower for kw in notice_keywords)
        is_location_question = any(kw in question_lower for kw in location_keywords)
        
        # Priority patterns based on detected category
        if is_salary_question:
            # Check for abbreviations CCTC (Current) and ECTC (Expected)
            if 'cctc' in question_lower:
                return '13.5 LPA', 0.98
            if 'ectc' in question_lower:
                return '20 LPA', 0.98
            
            # Check for expected vs current - always use LPA format
            if 'expected' in question_lower or 'expect' in question_lower:
                return '20 LPA', 0.95
            elif 'current' in question_lower or 'present' in question_lower:
                return '13.5 LPA', 0.95
            # Default to expected if unclear
            return '20 LPA', 0.90
        
        # Specific Experience Questions (Priority over generic check)
        if 'area' in question_lower and 'experience' in question_lower:
            return 'Full-stack', 0.98
            
        if 'chosen engineering field' in question_lower:
            return '4', 0.98

        if is_experience_question:
            if 'month' in question_lower:
                return KNOWN_QA_PATTERNS.get('months of experience', '46'), 0.95
            # LinkedIn requires whole numbers - return '4' for those cases
            if 'whole number' in question_lower or 'enter a number' in question_lower:
                return '4', 0.98
            return KNOWN_QA_PATTERNS.get('years of experience', '3.8 Years'), 0.95
        
        if is_notice_question:
            # Check if question asks for LWD (Last Working Day) specifically
            if 'last working day' in question_lower or 'lwd' in question_lower:
                # Calculate LWD as 30 days from today
                lwd_date = datetime.now() + timedelta(days=30)
                lwd_formatted = lwd_date.strftime('%d %B %Y')  # e.g., "07 February 2026"
                return f'Serving 30 days notice, LWD: {lwd_formatted}', 0.95
            elif 'serving' in question_lower:
                return KNOWN_QA_PATTERNS.get('serving notice', 'Yes'), 0.95
            elif 'in days' in question_lower:
                return '30', 0.98
            return KNOWN_QA_PATTERNS.get('notice period', '30 days'), 0.95
        
        if is_location_question:
            if 'preferred' in question_lower:
                return KNOWN_QA_PATTERNS.get('preferred location', 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune'), 0.95
            return KNOWN_QA_PATTERNS.get('current location', 'Noida'), 0.95
        
        # ==========================================
        # PHASE 2: Fuzzy Matching for Other Questions
        # ==========================================
        for pattern, answer in KNOWN_QA_PATTERNS.items():
            # Calculate similarity score
            score = SequenceMatcher(None, question_lower, pattern).ratio()
            
            # Boost score if pattern is contained in question
            if pattern in question_lower:
                score = max(score, 0.90)
            
            # Also boost if all words in pattern are found in question
            pattern_words = pattern.split()
            if len(pattern_words) > 1 and all(word in question_lower for word in pattern_words):
                score = max(score, 0.85)
            
            if score > best_score:
                best_score = score
                best_match = answer
        
        if best_score >= FUZZY_MATCH_THRESHOLD:
            return best_match, best_score
        
        # ==========================================
        # PHASE 3: Smart Category Fallback
        # Use question classifier for intelligent defaults
        # ==========================================
        if self._question_classifier is None:
            self._question_classifier = QuestionClassifier(self._current_platform)
        
        category, cat_confidence = self._question_classifier.classify(question)
        
        if category != QuestionCategory.UNKNOWN and cat_confidence >= 0.4:
            # Get platform-specific answer
            answer, ans_confidence = self._question_classifier.get_answer(question, category)
            if answer:
                combined_confidence = max(best_score, cat_confidence * 0.8)  # Slightly lower confidence for fallback
                print(f"   🤖 Smart fallback [{category.value}]: {answer[:50]}...")
                return answer, combined_confidence
        
        return None, best_score

    def _log_unknown_question(self, question: str, context: str = "", 
                               input_type: str = "", options: List[str] = None, 
                               selected_option: str = ""):
        """Log unrecognized questions to file for later review."""
        try:
            # Avoid duplicate logging
            q_hash = hash(question.lower().strip()[:100])
            if q_hash in self._logged_questions:
                return
            self._logged_questions.add(q_hash)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] [{context}]\n"
            log_entry += f"  Q: {question}\n"
            if input_type:
                log_entry += f"  Input Type: {input_type}\n"
            if options:
                log_entry += f"  Options: {', '.join(options)}\n"
            if selected_option:
                log_entry += f"  Selected: {selected_option}\n"
            log_entry += "  ---\n"
            
            with open(self.UNKNOWN_QUESTIONS_LOG, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            
            print(f"   📝 Logged unknown question to file")
        except Exception as e:
            print(f"   ⚠️ Failed to log question: {e}")

    def _log_all_questions(self, question: str, answer: str, context: str = "", 
                           match_confidence: str = "", input_type: str = "",
                           options: List[str] = None, selected_option: str = ""):
        """Log ALL questions encountered during Naukri and LinkedIn tasks for analysis."""
        try:
            # Avoid duplicate logging (same question in same session)
            q_hash = hash((question.lower().strip()[:100], context))
            if q_hash in self._all_logged_questions:
                return
            self._all_logged_questions.add(q_hash)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            confidence_str = f" [{match_confidence}]" if match_confidence else ""
            log_entry = f"[{timestamp}] [{context}]{confidence_str}\n"
            log_entry += f"  Q: {question}\n"
            log_entry += f"  A: {answer}\n"
            if input_type:
                log_entry += f"  Input Type: {input_type}\n"
            if options:
                log_entry += f"  Options: {', '.join(options)}\n"
            if selected_option:
                log_entry += f"  Selected: {selected_option}\n"
            log_entry += "  ---\n"
            
            with open(self.ALL_QUESTIONS_LOG, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            
            # Track in metrics
            self.metrics['questions_answered'] += 1
        except Exception as e:
            print(f"   ⚠️ Failed to log question: {e}")

    def _log_question_detailed(self, question_data: Dict[str, Any]):
        """
        Log a question with complete details including options and selection.
        Called from JavaScript form handlers to capture full context.
        
        Args:
            question_data: Dict containing:
                - question: Question text
                - answer: Answer provided
                - input_type: Type of input (text, radio, checkbox, select)
                - options: List of available options
                - selected_option: The option that was selected
                - context: Platform/context (linkedin, naukri, etc.)
                - url: Page URL
                - confidence: Match confidence score
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            question = question_data.get('question', '')
            answer = question_data.get('answer', '')
            input_type = question_data.get('input_type', '')
            options = question_data.get('options', [])
            selected_option = question_data.get('selected_option', '')
            context = question_data.get('context', 'unknown')
            url = question_data.get('url', '')
            confidence = question_data.get('confidence', '')
            
            # Create structured log entry
            log_entry = f"[{timestamp}] [{context}]\n"
            log_entry += f"  URL: {url}\n"
            log_entry += f"  Q: {question}\n"
            log_entry += f"  A: {answer}\n"
            if confidence:
                log_entry += f"  Confidence: {confidence}\n"
            if input_type:
                log_entry += f"  Input Type: {input_type}\n"
            if options:
                log_entry += f"  All Options: {', '.join(str(o) for o in options)}\n"
            if selected_option:
                log_entry += f"  Selected: {selected_option}\n"
            log_entry += "  ---\n"
            
            # Also create a JSON version for structured parsing
            json_entry = {
                'timestamp': timestamp,
                'context': context,
                'url': url,
                'question': question,
                'answer': answer,
                'confidence': confidence,
                'input_type': input_type,
                'options': options,
                'selected_option': selected_option
            }
            
            # Write to detailed log
            detailed_log = os.path.join(self.SCREENSHOT_DIR, 'all_questions_detailed.log')
            with open(detailed_log, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            
            # Write to JSON log for programmatic access
            json_log = os.path.join(self.SCREENSHOT_DIR, 'all_questions.jsonl')
            with open(json_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(json_entry) + '\n')
            
            print(f"   📝 Logged detailed question: {question[:50]}...")
        except Exception as e:
            print(f"   ⚠️ Failed to log detailed question: {e}")

    def track_question_attempt(self, question: str, answer: str, success: bool, confidence: float = 0.0):
        """
        Track the success/failure of a question answering attempt.
        
        Args:
            question: The question that was asked
            answer: The answer that was provided
            success: Whether the answer was accepted
            confidence: Match confidence score
        """
        try:
            if self._success_tracker:
                self._success_tracker.record_attempt(question, answer, success, confidence)
                
                # Log low success patterns for review
                stats = self._success_tracker.get_stats(question, answer)
                if stats and stats.attempts >= 3 and stats.success_rate < 0.7:
                    print(f"   ⚠️ Low success pattern: {question[:50]}... (rate: {stats.success_rate:.1%})")
        except Exception as e:
            print(f"   ⚠️ Failed to track attempt: {e}")

    def get_pattern_stats(self) -> Dict:
        """Get statistics about pattern success rates."""
        if self._success_tracker:
            return self._success_tracker.get_stats_summary()
        return {}

    def _save_metrics(self):
        """Save task metrics to JSONL file for analysis."""
        try:
            self.metrics['end_time'] = datetime.now().isoformat()
            self.metrics['steps_taken'] = self.state.step_count
            
            with open(self.METRICS_LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps(self.metrics) + '\n')
            
            print(f"📊 Metrics saved: {self.metrics['applications_submitted']} apps, {self.metrics['questions_answered']} Q&A, {self.metrics['errors_encountered']} errors")
        except Exception as e:
            print(f"   ⚠️ Failed to save metrics: {e}")

    async def _screenshot_on_error(self, error_context: str = "unknown"):
        """Save screenshot when error occurs for debugging."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.SCREENSHOT_DIR}/error_{error_context}_{timestamp}.png"
            await self._page.screenshot(path=filename, full_page=False)
            print(f"   📸 Screenshot saved: {filename}")
            return filename
        except Exception as e:
            print(f"   ⚠️ Screenshot failed: {e}")
            return None

    async def _check_page_health(self) -> bool:
        """Verify page is responsive before actions."""
        try:
            # Quick JS evaluation to check if page responds
            result = await asyncio.wait_for(
                self._page.evaluate("() => document.readyState"),
                timeout=5.0
            )
            if result != 'complete':
                print(f"   ⚠️ Page not ready: {result}")
                await asyncio.sleep(2)
                return False
            return True
        except asyncio.TimeoutError:
            print("   ⚠️ Page health check timeout - page may be unresponsive")
            await self._screenshot_on_error("page_unresponsive")
            return False
        except Exception as e:
            print(f"   ⚠️ Page health check failed: {e}")
            return False

    async def _maybe_cleanup_memory(self):
        """Periodic memory cleanup by refreshing page if needed."""
        self._steps_since_cleanup += 1
        
        if self._steps_since_cleanup >= self.MEMORY_CLEANUP_INTERVAL:
            print("   🧹 Memory cleanup: Refreshing page state...")
            try:
                # Clear JS memory by running garbage collection hint
                await self._page.evaluate("""() => {
                    // Clear any stored data
                    if (window.gc) window.gc();
                    // Clear console
                    console.clear();
                    return 'CLEANUP_DONE';
                }""")
                self._steps_since_cleanup = 0
                print("   ✅ Memory cleanup complete")
            except Exception as e:
                print(f"   ⚠️ Memory cleanup failed: {e}")



    async def _check_login_state(self) -> bool:
        """Detect if session expired and need re-login. Returns True if logged in."""
        try:
            current_url = self._page.url.lower()
            
            # LinkedIn login detection
            if 'linkedin' in current_url:
                login_required = await self._page.evaluate("""() => {
                    // Check for auth wall or login prompts
                    const authWall = document.querySelector('[data-test="authwall"]');
                    const loginForm = document.querySelector('form.login-form, #session_key');
                    const signInBtn = document.querySelector('a[data-tracking-control-name="guest_homepage-basic_sign-in-button"]');
                    const bodyText = document.body?.innerText || '';
                    
                    return !!(authWall || loginForm || signInBtn || 
                             bodyText.includes('Sign in to LinkedIn'));
                }""")
                
                if login_required:
                    print("⚠️ LinkedIn session expired - waiting 60s for re-login...")
                    await self._screenshot_on_error("linkedin_session_expired")
                    self.metrics['login_prompts'] += 1
                    await asyncio.sleep(60)
                    return False
            
            # Naukri login detection
            elif 'naukri' in current_url:
                login_required = await self._page.evaluate("""() => {
                    const loginBtn = document.querySelector('a[href*="login"], .login-btn');
                    const loginForm = document.querySelector('#login-form, .login-container');
                    const bodyText = document.body?.innerText || '';
                    
                    return !!(loginForm || 
                             (loginBtn && bodyText.includes('Login')));
                }""")
                
                if login_required:
                    print("⚠️ Naukri session expired - waiting 60s for re-login...")
                    await self._screenshot_on_error("naukri_session_expired")
                    self.metrics['login_prompts'] += 1
                    await asyncio.sleep(60)
                    return False
            
            # Instahyre login detection
            elif 'instahyre' in current_url:
                login_required = await self._page.evaluate("""() => {
                    const googleSignIn = document.querySelector('[data-google-signin], .google-signin-btn, button[id*="google"]');
                    const loginForm = document.querySelector('.login-form, #loginForm, .auth-container');
                    const signInText = document.body?.innerText || '';
                    
                    return !!(googleSignIn || loginForm || 
                             signInText.includes('Sign in with Google') ||
                             signInText.includes('Login to continue'));
                }""")
                
                if login_required:
                    print("⚠️ Instahyre session expired - waiting 60s for re-login...")
                    await self._screenshot_on_error("instahyre_session_expired")
                    self.metrics['login_prompts'] += 1
                    await asyncio.sleep(60)
                    return False
            
            return True
        except Exception as e:
            print(f"   ⚠️ Login state check failed: {e}")
            return True  # Assume logged in on error


    async def _human_mouse_move(self, target_x: int = None, target_y: int = None):
        """Add random micro-movements before clicks to simulate human behavior."""
        try:
            # Get current viewport size
            viewport = await self._page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
            
            # If no target, pick random point in viewport
            if target_x is None:
                target_x = random.randint(100, viewport['w'] - 100)
            if target_y is None:
                target_y = random.randint(100, viewport['h'] - 100)
            
            # Start from random position
            start_x = random.randint(50, viewport['w'] - 50)
            start_y = random.randint(50, viewport['h'] - 50)
            
            # Move in 2-4 small steps with slight randomness
            steps = random.randint(2, 4)
            for i in range(steps):
                # Calculate intermediate position with jitter
                progress = (i + 1) / steps
                jitter_x = random.randint(-15, 15)
                jitter_y = random.randint(-10, 10)
                
                curr_x = int(start_x + (target_x - start_x) * progress + jitter_x)
                curr_y = int(start_y + (target_y - start_y) * progress + jitter_y)
                
                await self._page.mouse.move(curr_x, curr_y)
                await asyncio.sleep(random.uniform(0.02, 0.08))
            
            # Final move to target
            await self._page.mouse.move(target_x, target_y)
        except Exception:
            pass  # Silent fail - this is just for human simulation

    async def _human_scroll(self, direction: str = "down", amount: int = None):
        """Variable scroll patterns - sometimes slow, sometimes fast."""
        try:
            # Random scroll behavior type
            scroll_type = random.choice(['smooth', 'stepped', 'quick'])
            
            if amount is None:
                # Variable scroll amounts
                if scroll_type == 'smooth':
                    amount = random.randint(200, 400)
                elif scroll_type == 'stepped':
                    amount = random.randint(100, 200)
                else:  # quick
                    amount = random.randint(400, 600)
            
            scroll_y = amount if direction == "down" else -amount
            
            if scroll_type == 'smooth':
                # Smooth scroll with small increments
                steps = random.randint(5, 8)
                step_amount = scroll_y // steps
                for _ in range(steps):
                    await self._page.evaluate(f"window.scrollBy(0, {step_amount})")
                    await asyncio.sleep(random.uniform(0.03, 0.08))
            
            elif scroll_type == 'stepped':
                # Stepped scroll with pauses (like reading)
                steps = random.randint(2, 4)
                step_amount = scroll_y // steps
                for _ in range(steps):
                    await self._page.evaluate(f"window.scrollBy(0, {step_amount})")
                    await asyncio.sleep(random.uniform(0.1, 0.3))  # Reading pause
            
            else:  # quick
                # Quick single scroll
                await self._page.evaluate(f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(0.2, 0.4))
            
            # Occasional micro-adjustment after scroll
            if random.random() < 0.3:
                micro = random.randint(-30, 30)
                await self._page.evaluate(f"window.scrollBy(0, {micro})")
                
        except Exception:
            pass  # Silent fail

    async def _human_click(self, locator):
        """Human-like click with mouse movement and slight delay."""
        try:
            # Get element position
            box = await locator.bounding_box()
            if box:
                # Calculate click position with slight randomness (not dead center)
                target_x = box['x'] + box['width'] * random.uniform(0.3, 0.7)
                target_y = box['y'] + box['height'] * random.uniform(0.3, 0.7)
                
                # Move mouse to element
                await self._human_mouse_move(int(target_x), int(target_y))
                await asyncio.sleep(random.uniform(0.05, 0.15))
                
                # Click
                await locator.click()
            else:
                # Fallback to regular click
                await locator.click()
        except Exception:
            # Fallback to regular click
            await locator.click()

    # ==========================================
    # ROBUST CLICK HELPERS - Bypass viewport issues
    # ==========================================
    
    async def _robust_click(self, locator, description: str = "element", timeout: int = 5000, retries: int = 3) -> bool:
        """
        Robust click that handles viewport issues with multiple fallback strategies.
        Returns True if click succeeded, False otherwise.
        """
        for attempt in range(retries):
            try:
                # Strategy 1: Try normal Playwright click with short timeout
                try:
                    await locator.click(timeout=min(timeout, 3000))
                    return True
                except Exception:
                    pass
                
                # Strategy 2: Scroll into view and use JS click
                try:
                    await locator.evaluate('el => { el.scrollIntoView({block: "center", behavior: "instant"}); }')
                    await asyncio.sleep(0.1)
                    await locator.evaluate('el => el.click()')
                    return True
                except Exception:
                    pass
                
                # Strategy 3: Force scroll to element and dispatch click event
                try:
                    await locator.evaluate('''el => {
                        el.scrollIntoView({block: "center"});
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    }''')
                    return True
                except Exception:
                    pass
                
                # Strategy 4: Get coordinates and click at position
                try:
                    box = await locator.bounding_box()
                    if box:
                        x = box['x'] + box['width'] / 2
                        y = box['y'] + box['height'] / 2
                        await self._page.mouse.click(x, y)
                        return True
                except Exception:
                    pass
                
                if attempt < retries - 1:
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                if attempt == retries - 1:
                    print(f"   ⚠️ Robust click failed after {retries} attempts on {description}: {e}")
        
        return False

    async def _robust_js_click(self, selector: str, description: str = "element", timeout: int = 5000) -> bool:
        """
        Click element using pure JavaScript - most reliable for viewport issues.
        Returns True if click succeeded, False otherwise.
        """
        try:
            result = await self._page.evaluate(f"""(selector) => {{
                const el = document.querySelector(selector);
                if (!el) return 'NOT_FOUND';
                
                // Scroll into view
                el.scrollIntoView({{block: 'center', behavior: 'instant'}});
                
                // Try direct click
                try {{ el.click(); return 'CLICKED'; }} catch(e) {{}}
                
                // Fallback: dispatch event
                try {{
                    el.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true, view: window}}));
                    return 'DISPATCHED';
                }} catch(e) {{
                    return 'FAILED: ' + e.message;
                }}
            }}""", selector)
            
            if result in ['CLICKED', 'DISPATCHED']:
                return True
            else:
                print(f"   ⚠️ JS click on {description}: {result}")
                return False
        except Exception as e:
            print(f"   ⚠️ JS click failed on {description}: {e}")
            return False

    async def _robust_click_by_text(self, text: str, tag: str = "*", exact: bool = False, timeout: int = 3000) -> bool:
        """
        Click element containing specific text, using JS to bypass viewport issues.
        """
        try:
            result = await self._page.evaluate(f"""(text, tag, exact) => {{
                const elements = document.querySelectorAll(tag);
                for (const el of elements) {{
                    const elText = el.innerText || el.textContent || '';
                    const matches = exact ? elText.trim() === text : elText.toLowerCase().includes(text.toLowerCase());
                    if (matches && el.offsetParent !== null) {{
                        el.scrollIntoView({{block: 'center'}});
                        el.click();
                        return 'CLICKED: ' + elText.substring(0, 50);
                    }}
                }}
                return 'NOT_FOUND';
            }}""", text, tag, exact)
            
            if 'CLICKED' in result:
                return True
            return False
        except Exception as e:
            print(f"   ⚠️ Click by text '{text}' failed: {e}")
            return False

    async def _robust_radio_click(self, value_or_text: str, fallback_index: int = None) -> bool:
        """
        Robustly click a radio button by value, id, or label text.
        Uses JS to bypass viewport issues.
        """
        try:
            result = await self._page.evaluate(f"""(valueOrText, fallbackIndex) => {{
                const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                if (radios.length === 0) return 'NO_RADIOS';
                
                // Try to find by value, id, or associated label
                for (const r of radios) {{
                    const val = (r.value || '').toLowerCase();
                    const id = (r.id || '').toLowerCase();
                    const label = r.closest('label') || document.querySelector('label[for="' + r.id + '"]');
                    const labelText = label ? label.innerText.toLowerCase() : '';
                    
                    if (val.includes(valueOrText.toLowerCase()) || 
                        id.includes(valueOrText.toLowerCase()) || 
                        labelText.includes(valueOrText.toLowerCase())) {{
                        r.scrollIntoView({{block: 'center'}});
                        r.click();
                        return 'CLICKED: ' + (label ? label.innerText : val);
                    }}
                }}
                
                // Fallback to index
                if (fallbackIndex !== null && fallbackIndex < radios.length) {{
                    radios[fallbackIndex].scrollIntoView({{block: 'center'}});
                    radios[fallbackIndex].click();
                    return 'CLICKED_INDEX: ' + fallbackIndex;
                }}
                
                return 'NOT_FOUND';
            }}""", value_or_text, fallback_index)
            
            if 'CLICKED' in result:
                return True
            return False
        except Exception as e:
            print(f"   ⚠️ Radio click '{value_or_text}' failed: {e}")
            return False

    async def _robust_checkbox_click(self, value_or_text: str = None, select_all: bool = False) -> bool:
        """
        Robustly click checkboxes, optionally all visible ones or by value/text.
        Uses JS to bypass viewport issues.
        """
        try:
            result = await self._page.evaluate(f"""(valueOrText, selectAll) => {{
                const cbs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                let clicked = 0;
                
                for (const cb of cbs) {{
                    if (cb.offsetParent === null) continue;  // Skip hidden
                    if (cb.checked) continue;  // Skip already checked
                    
                    const val = (cb.value || '').toLowerCase();
                    const label = cb.closest('label') || document.querySelector('label[for="' + cb.id + '"]');
                    const labelText = label ? label.innerText.toLowerCase() : '';
                    
                    if (selectAll) {{
                        cb.scrollIntoView({{block: 'center'}});
                        cb.click();
                        clicked++;
                    }} else if (valueOrText) {{
                        if (val.includes(valueOrText.toLowerCase()) || labelText.includes(valueOrText.toLowerCase())) {{
                            cb.scrollIntoView({{block: 'center'}});
                            cb.click();
                            return 'CLICKED: ' + (label ? label.innerText : val);
                        }}
                    }}
                }}
                
                if (selectAll) return clicked > 0 ? 'CLICKED_ALL: ' + clicked : 'NONE_TO_CLICK';
                return 'NOT_FOUND';
            }}""", value_or_text, select_all)
            
            if 'CLICKED' in result:
                return True
            return False
        except Exception as e:
            print(f"   ⚠️ Checkbox click failed: {e}")
            return False

    async def _robust_button_click(self, text_patterns: list, fallback_selector: str = None) -> bool:
        """
        Click button by text pattern with JS fallback.
        text_patterns: List of text strings to look for (first match wins)
        """
        for pattern in text_patterns:
            try:
                result = await self._page.evaluate(f"""(pattern) => {{
                    const buttons = document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"], .btn, a.button');
                    for (const btn of buttons) {{
                        const text = btn.innerText || btn.value || '';
                        if (text.toLowerCase().includes(pattern.toLowerCase()) && btn.offsetParent !== null) {{
                            btn.scrollIntoView({{block: 'center'}});
                            btn.click();
                            return 'CLICKED: ' + text.substring(0, 30);
                        }}
                    }}
                    return 'NOT_FOUND';
                }}""", pattern)
                
                if 'CLICKED' in result:
                    return True
            except Exception:
                continue
        
        # Try fallback selector
        if fallback_selector:
            return await self._robust_js_click(fallback_selector, f"button fallback")
        
        return False

    async def _scroll_element_into_view(self, selector_or_locator, block: str = "center") -> bool:
        """
        Scroll element into viewport using multiple strategies.
        """
        try:
            if isinstance(selector_or_locator, str):
                await self._page.evaluate(f"""(selector, block) => {{
                    const el = document.querySelector(selector);
                    if (el) el.scrollIntoView({{block: block, behavior: 'instant'}});
                }}""", selector_or_locator, block)
            else:
                await selector_or_locator.evaluate(f'el => el.scrollIntoView({{block: "{block}", behavior: "instant"}})')
            await asyncio.sleep(0.1)
            return True
        except Exception:
            return False


    async def _dismiss_browser_dialogs(self):
        """Dismiss common browser dialogs like 'Restore pages?'"""
        try:
            result = await self._page.evaluate("""() => {
                // Chrome "Restore pages?" dialog - click X button
                const restoreDialog = document.querySelector('[aria-label="Restore pages?"], [aria-describedby*="restore"]');
                if (restoreDialog) {
                    const closeBtn = restoreDialog.querySelector('button[aria-label="Close"], .close-button, button:has(svg)');
                    if (closeBtn) {
                        closeBtn.click();
                        return 'CLOSED_RESTORE_DIALOG';
                    }
                }
                
                // Any dialog with "Restore" button - click X instead
                const restoreBtn = document.querySelector('button:has-text("Restore")');
                if (restoreBtn) {
                    const dialog = restoreBtn.closest('[role="dialog"], .modal, [aria-modal="true"]');
                    if (dialog) {
                        const closeBtn = dialog.querySelector('button[aria-label*="close"], button[aria-label*="dismiss"], .close');
                        if (closeBtn) {
                            closeBtn.click();
                            return 'CLOSED_DIALOG';
                        }
                    }
                }
                
                // Generic modal dismiss
                const genericModals = document.querySelectorAll('[role="dialog"], [aria-modal="true"]');
                for (let modal of genericModals) {
                    if (modal.innerText && modal.innerText.includes("didn't shut down")) {
                        const xBtn = modal.querySelector('button[aria-label*="Close"], svg, .close-button');
                        if (xBtn) {
                            xBtn.click();
                            return 'CLOSED_CRASH_DIALOG';
                        }
                    }
                }
                
                return 'NO_DIALOG';
            }""")
            
            if 'CLOSED' in result:
                print(f"   🚫 {result}")
                await asyncio.sleep(0.5)
                return True
            return False
        except Exception:
            return False


    def _log_js_msg(self, msg):
        """Helper to log JS console messages."""
        print(f"   🖥️ JS: {msg.text}")

    def _get_max_steps(self) -> int:
        """Determine max steps based on task type - LinkedIn gets 120, others get 50."""
        task_desc = getattr(self, '_task_description', '').lower()
        current_url = self._page.url.lower() if self._page else ''
        
        if 'linkedin' in task_desc or 'linkedin' in current_url:
            return self.MAX_STEPS_LINKEDIN
        return self.MAX_STEPS_DEFAULT

    async def run(self, task_description: str = "") -> bool:
        """Main execution loop - 100% SCRIPTED (No LLM)."""
        self._task_description = task_description  # Store for use in handlers
        max_steps = self._get_max_steps()
        print(f"\n🚀 Sentinel Starting Task (Script Mode): {task_description}")
        print(f"   📊 Max Steps: {max_steps}")
        
        # Initialize metrics for this task
        self.metrics = {
            'task_name': task_description[:50] if task_description else 'Unknown',
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'applications_submitted': 0,
            'questions_answered': 0,
            'errors_encountered': 0,

            'login_prompts': 0,
            'steps_taken': 0,
            'success': False
        }
        
        # Enable console logging from browser (Safe Mode)
        if self._page and not getattr(self, '_console_listening', False):
            try:
                self._page.on("console", self._log_js_msg)
                self._console_listening = True
                print("   ✅ Browser console logging enabled")
            except Exception as e:
                print(f"   ⚠️ Could not enable browser console logging: {e}")
        
        while self.state.step_count < max_steps and not self.state.task_complete:
            self.state.step_count += 1
            print(f"\n📍 Step {self.state.step_count}/{max_steps}")
            
            try:
                current_url = self._page.url if self._page else ""
                
                # Periodic memory cleanup
                await self._maybe_cleanup_memory()
                
                # Page health check before actions
                if not await self._check_page_health():
                    print("   🔄 Retrying after page health issue...")
                    await asyncio.sleep(3)
                    continue
                

                
                # Login state check - pause for re-login
                if not await self._check_login_state():
                    print("   🔄 Resuming after login...")
                    continue
                
                # Dismiss any browser dialogs (Restore pages?, etc.)
                await self._dismiss_browser_dialogs()
                
                # Occasional random human behaviors (simulate natural browsing)
                if random.random() < 0.2:  # 20% chance of random mouse movement
                    await self._human_mouse_move()
                if random.random() < 0.15:  # 15% chance of random small scroll
                    await self._human_scroll(direction=random.choice(["down", "up"]))
                
                await asyncio.sleep(random.uniform(4, 8))  # Random 4-8 sec gap between actions
                
                # Run scripted fallback
                result = await self._handle_scripted_fallback()
                print(f"📜 Script Result: {result}")
                
                # Handle question data logging if present
                if result and '|' in result:
                    parts = result.split('|', 1)
                    action = parts[0]
                    if len(parts) > 1:
                        try:
                            question_data_json = parts[1]
                            question_data = json.loads(question_data_json)
                            current_url = self._page.url if self._page else ''
                            for q_data in question_data:
                                self._log_question_detailed({
                                    'question': q_data.get('question', ''),
                                    'answer': q_data.get('answer', ''),
                                    'input_type': q_data.get('inputType', ''),
                                    'options': q_data.get('options', []),
                                    'selected_option': q_data.get('selectedOption', ''),
                                    'context': self._detect_platform(),
                                    'url': current_url,
                                    'confidence': 'form_filled'
                                })
                            # Update result to just the action part
                            result = action
                        except json.JSONDecodeError:
                            pass
                
                # Handle results
                if result == 'TASK_COMPLETE': 
                    print("🎉 Task Completed Successfully!")
                    self.state.task_complete = True
                    break
                
                # Naukri: Task complete after target jobs applied
                if 'NAUKRI_TASK_DONE' in result:
                    print("🎉 Naukri task complete - applied to 5 jobs successfully!")
                    self.state.task_complete = True
                    break
                
                # Naukri: Rate limit detected (error popup)
                if 'NAUKRI_RATE_LIMITED' in result:
                    self.naukri_rate_limit_until = datetime.now() + timedelta(hours=3)
                    print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                    self.state.task_complete = True
                    break
                
                if 'SUCCESS' in result:
                    # For LinkedIn, we want to apply to multiple jobs (up to limit)
                    if 'LinkedIn' in self._task_description:
                         print("🎉 Job application successful! Moving to next job...")
                         # Do NOT break here, let the loop continue
                    else:
                        # For other tasks (Naukri single apply), we break
                        print("🎉 Task Completed Successfully!")
                        self.state.task_complete = True
                        break
                
                # LinkedIn: Success detected but need to navigate to next job
                if 'LINKEDIN_SUCCESS_NEED_NAV' in result:
                    print("✅ LinkedIn success! Need to navigate to next job...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # LinkedIn: Success modal was closed, need to navigate to next job
                if 'LINKEDIN_SUCCESS_MODAL_CLOSED' in result:
                    print("✅ Success modal closed. Looking for next job...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # LinkedIn: Safety modal "Continue applying" button clicked
                if 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED' in result:
                    print("✅ LinkedIn safety modal dismissed, continuing application...")
                    await asyncio.sleep(random.uniform(4, 6))
                    continue
                
                # LinkedIn: First job opened (when no currentJobId in URL)
                if 'LINKEDIN_FIRST_JOB' in result:
                    print(f"✅ {result}")
                    await asyncio.sleep(random.uniform(4, 6))
                    continue
                
                # LinkedIn: Navigation results
                if 'LINKEDIN_NAVIGATED' in result:
                    print(f"✅ {result}")
                    await asyncio.sleep(random.uniform(4, 6))  # Wait for job details to load
                    continue
                
                # LinkedIn: Scrolled for more jobs
                if 'LINKEDIN_SCROLLED' in result:
                    print(f"📜 {result}")
                    await asyncio.sleep(random.uniform(4, 8))  # Wait for new jobs to load
                    continue
                
                # LinkedIn: Skip non-Easy Apply jobs or already applied jobs
                if 'LINKEDIN_JOB_SKIPPED' in result:
                    print(f"   ℹ️ Result: {result}")  # Debug log
                    if 'SCROLLED_FOR_MORE' in result:
                        print("📜 Scrolled job list to load more jobs, waiting...")
                        await asyncio.sleep(random.uniform(4, 8))  # Wait for new jobs to load
                    elif 'FOUND_UNAPPLIED' in result:
                        print("🔍 Found non-applied job, navigating to it...")
                        await asyncio.sleep(random.uniform(4, 8))  # Wait for job details to load
                    elif 'NEXT' in result:
                        print("⏭️ Skipped to next job in list")
                        await asyncio.sleep(random.uniform(4, 8))  # Wait for job details to load
                    else:
                        print("⏭️ Skipped job (already applied or not Easy Apply)")
                    continue
                
                # LinkedIn Autopilot
                if 'APPLY_CLICKED_LINKEDIN' in result:
                    # STRICT CHECK: If we've already submitted 5 applications, mark task complete
                    if self.linkedin_applications >= 5:
                        print(f"✅ LinkedIn limit reached ({self.linkedin_applications}/5). Task complete.")
                        self.state.task_complete = True
                        continue
                    
                    print("🔄 Entering LinkedIn Autopilot Mode...")
                    same_result_count = 0
                    last_result = ""
                    submit_attempt_count = 0  # Track submit attempts without success
                    max_submit_attempts = 3   # Max retries per job before skipping
                    autopilot_iteration = 0   # Track total iterations in autopilot
                    max_autopilot_iterations = 50  # Safety limit per job
                    
                    while True:
                        autopilot_iteration += 1
                        
                        # SAFETY: Exit autopilot if too many iterations (prevents infinite loop)
                        if autopilot_iteration > max_autopilot_iterations:
                            print(f"⚠️ Max iterations ({max_autopilot_iterations}) reached for this job. Skipping...")
                            # Try to close any open modal and move on
                            await self._page.evaluate("""() => {
                                // Try multiple selectors for LinkedIn modal close button
                                const closeSelectors = [
                                    'button[aria-label*="Dismiss"]',
                                    'button[aria-label*="dismiss"]', 
                                    'button[aria-label*="Close"]',
                                    'button[aria-label*="close"]',
                                    'button[data-test-modal-close-btn]',
                                    '.artdeco-modal__dismiss',
                                    '.artdeco-button--circle[aria-label]',
                                    'button[aria-label*="Discard"]'
                                ];
                                for (let sel of closeSelectors) {
                                    const btn = document.querySelector(sel);
                                    if (btn && btn.offsetParent !== null) {
                                        btn.click();
                                        return;
                                    }
                                }
                            }""")
                            await asyncio.sleep(1)
                            break
                        
                        await asyncio.sleep(random.uniform(4, 8))
                        
                        # Check for rate limit message before proceeding
                        rate_limited = await self._page.evaluate("""() => {
                            const bodyText = document.body.innerText.toLowerCase();
                            return bodyText.includes('we limit daily submissions') || 
                                   bodyText.includes('prevent bots') ||
                                   bodyText.includes('apply tomorrow');
                        }""")
                        
                        if rate_limited:
                            self.linkedin_rate_limit_until = datetime.now() + timedelta(hours=3)
                            print(f"⚠️ LinkedIn Rate Limit Detected! Pausing until {self.linkedin_rate_limit_until.strftime('%H:%M')}")
                            self.state.task_complete = True
                            break
                        
                        # Check for application loading error ("We experienced an error loading this application")
                        app_load_error = await self._page.evaluate("""() => {
                            const errorMsg = document.querySelector('.artdeco-inline-feedback--error .artdeco-inline-feedback__message');
                            if (errorMsg) {
                                const text = (errorMsg.innerText || '').toLowerCase();
                                if (text.includes('experienced an error') || text.includes('error loading')) {
                                    return true;
                                }
                            }
                            // Also check for general error text on page
                            const bodyText = document.body.innerText.toLowerCase();
                            return bodyText.includes('we experienced an error loading this application');
                        }""")
                        
                        if app_load_error:
                            print("⚠️ LinkedIn Application Loading Error Detected! Skipping this job...")
                            # Close any open modal
                            await self._page.evaluate("""() => {
                                const closeSelectors = [
                                    'button[aria-label*="Dismiss"]',
                                    'button[aria-label*="dismiss"]', 
                                    'button[aria-label*="Close"]',
                                    'button[aria-label*="close"]',
                                    'button[data-test-modal-close-btn]',
                                    '.artdeco-modal__dismiss',
                                    'button[aria-label*="Discard"]'
                                ];
                                for (let sel of closeSelectors) {
                                    const btn = document.querySelector(sel);
                                    if (btn && btn.offsetParent !== null) {
                                        btn.click();
                                        return 'CLOSED';
                                    }
                                }
                                return 'NO_CLOSE_BTN';
                            }""")
                            await asyncio.sleep(1)
                            break  # Skip to next job
                        
                        next_result = await self._handle_scripted_fallback()
                        print(f"   📜 Autopilot: {next_result}")
                        
                        # Check for rate limit in result
                        if 'LINKEDIN_RATE_LIMITED' in next_result:
                            self.linkedin_rate_limit_until = datetime.now() + timedelta(hours=3)
                            print(f"⚠️ LinkedIn Rate Limit! Pausing until {self.linkedin_rate_limit_until.strftime('%H:%M')}")
                            self.state.task_complete = True
                            break
                        
                        # DETECT SUBMISSION FAILURE: If no modal present after submit, it likely failed
                        if 'LINKEDIN_SUBMISSION_FAILED' in next_result:
                            print(f"❌ Submission failed (attempt {submit_attempt_count + 1}/{max_submit_attempts})")
                            submit_attempt_count += 1
                            if submit_attempt_count >= max_submit_attempts:
                                print("⚠️ Max submit attempts reached. Skipping this job...")
                                break
                            continue
                        
                        # Prevent infinite loop if same result repeats
                        if next_result == last_result:
                            same_result_count += 1
                            if same_result_count >= 5:
                                print("⚠️ Stuck in loop, skipping this job...")
                                break
                        else:
                            same_result_count = 0
                        last_result = next_result
                        
                        if 'LINKEDIN_SUCCESS' in next_result:
                            self.linkedin_applications += 1
                            print(f"🎉 LinkedIn Application {self.linkedin_applications}/5 Submitted!")
                            submit_attempt_count = 0  # Reset on success
                            
                            if self.linkedin_applications >= 5:
                                print("✅ LinkedIn target (5 applications) reached. Task complete!")
                                self.state.task_complete = True
                                break
                                
                            await asyncio.sleep(random.uniform(2, 4))
                            # Exit autopilot after successful submit to navigate to next job
                            break
                        elif 'LINKEDIN_SUBMITTED' in next_result:
                            submit_attempt_count += 1
                            print(f"✅ Clicked Submit (attempt {submit_attempt_count}/{max_submit_attempts})")
                            
                            # If we've clicked submit too many times without success, the submission is failing
                            if submit_attempt_count >= max_submit_attempts:
                                print("⚠️ Submit not working (possible 403 error). Skipping this job...")
                                # Try to close the modal
                                await self._page.evaluate("""() => {
                                    // Try multiple selectors for LinkedIn modal close button
                                    const closeSelectors = [
                                        'button[aria-label*="Dismiss"]',
                                        'button[aria-label*="dismiss"]', 
                                        'button[aria-label*="Close"]',
                                        'button[aria-label*="close"]',
                                        'button[data-test-modal-close-btn]',
                                        '.artdeco-modal__dismiss',
                                        '.artdeco-button--circle[aria-label]',
                                        'button[aria-label*="Discard"]'
                                    ];
                                    for (let sel of closeSelectors) {
                                        const btn = document.querySelector(sel);
                                        if (btn && btn.offsetParent !== null) {
                                            btn.click();
                                            return;
                                        }
                                    }
                                }""")
                                await asyncio.sleep(1)
                                break
                            continue
                        elif 'LINKEDIN_SAFETY_CONTINUE_CLICKED' in next_result:
                            print("🛡️ Acknowledged Safety Reminder")
                            continue
                        elif 'LINKEDIN_NEXT_CLICKED' in next_result or 'LINKEDIN_REVIEW_CLICKED' in next_result:
                            print("➡ Clicked Next/Review")
                            # NOTE: Do NOT reset submit_attempt_count here!
                            # The 403 loop shows Next/Review buttons after failed submit
                            continue
                        elif 'LINKEDIN_FORM_FILLED' in next_result:
                            print("📝 Filled form fields")
                            submit_attempt_count = 0  # Reset when filling (progress made)
                            
                            # Parse and log Q&A data if present
                            if '|' in next_result:
                                try:
                                    qa_json = next_result.split('|', 1)[1]
                                    qa_pairs = json.loads(qa_json)
                                    for qa in qa_pairs:
                                        self._log_all_questions(
                                            qa.get('q', 'Unknown'),
                                            qa.get('a', ''),
                                            context="LinkedIn_Form",
                                            match_confidence="Keyword Match"
                                        )
                                except Exception as e:
                                    pass  # Silently handle parse errors
                            continue
                        elif 'LINKEDIN_CITY_TYPED' in next_result:
                            print("🏙️ Typed city, waiting for dropdown...")
                            await asyncio.sleep(1.5)  # Wait for dropdown to appear
                            continue
                        elif 'LINKEDIN_CITY_SELECTED' in next_result:
                            print("✅ Selected city from dropdown")
                            continue
                        elif 'LINKEDIN_CHECKBOX_CHECKED' in next_result:
                            print("☑️ Checked Terms/Privacy checkbox")
                            continue
                        elif 'NO_ACTION' in next_result or 'MODAL_OPEN_NO_ACTION' in next_result:
                            print("⚠️ Exiting Autopilot...")
                            break
                        elif 'LINKEDIN_JOB_SKIPPED' in next_result:
                            print("⏭️ Job skipped, moving to next...")
                            break
                
                # Naukri Profile Update - Resume Headline Toggle
                # NOTE: Only run if NOT an Employment LWD task (same URL, different task)
                if 'profile' in current_url and 'naukri.com' in current_url and 'Employment' not in self._task_description:
                    print("📝 Naukri Profile Page - Running headline update...")
                    try:
                        update_result = await self._page.evaluate("""() => {
                            // Find the Resume Headline section
                            const headlineSection = document.querySelector('#lazyResumeHead, .resumeHeadline');
                            if (!headlineSection) return 'NO_HEADLINE_SECTION';
                            
                            // Find the edit icon
                            const editIcon = headlineSection.querySelector('span.edit.icon, span.icon.edit, [class*="edit"][class*="icon"]');
                            if (!editIcon) return 'NO_EDIT_ICON';
                            
                            editIcon.click();
                            return 'EDIT_CLICKED';
                        }""")
                        print(f"   📜 Step 1 - Edit click: {update_result}")
                        
                        if update_result == 'EDIT_CLICKED':
                            await asyncio.sleep(random.uniform(4, 8))  # Wait for modal to fully open
                            
                            # Step 2: Remove fullstop (using exact selector from screenshot)
                            # Step 2: Remove fullstop using Keyboard (Backpsace)
                            remove_result = await self._page.evaluate("""() => {
                                const textarea = document.querySelector('#resumeHeadline, textarea[id="resumeHeadline"]');
                                if (!textarea) return 'NO_TEXTAREA';
                                if (textarea.value.endsWith('.')) return 'HAS_FULLSTOP';
                                return 'NO_FULLSTOP';
                            }""")
                            
                            if remove_result == 'HAS_FULLSTOP':
                                # Robust Method: Select All -> Rewrite without dot
                                text_val = await self._page.evaluate("document.querySelector('#resumeHeadline').value")
                                new_text = text_val.rstrip('.')
                                
                                textarea = self._page.locator('#resumeHeadline')
                                await textarea.focus()
                                await textarea.select_text()
                                await textarea.press('Backspace')
                                await asyncio.sleep(0.5)
                                await textarea.type(new_text)
                                remove_result = 'FULLSTOP_REMOVED'
                            
                            print(f"   📜 Step 2 - Remove fullstop: {remove_result}")
                            
                            await asyncio.sleep(random.uniform(4, 8))  # Wait before clicking Save
                            
                            # Step 3: Click Save button
                            try:
                                save_btn = self._page.locator('.form-actions button.btn-dark-ot, .action.s12 button.btn-dark-ot, button.btn-dark-ot[type="submit"]').first
                                await save_btn.wait_for(state='visible', timeout=5000)
                                await save_btn.scroll_into_view_if_needed()
                                # Try double click which can be more reliable for React buttons
                                await save_btn.dblclick()
                                save_result = 'SAVE_CLICKED'
                            except Exception as e:
                                print(f"      ⚠️ Save error: {e}")
                                save_result = 'NO_SAVE_BUTTON'
                            print(f"   📜 Step 3 - First save: {save_result}")
                            
                            await asyncio.sleep(random.uniform(4, 8))  # Wait for save to complete
                            
                            # Navigate back to profile page explicitly to ensure clean state
                            print("   🔄 Navigating back to profile page...")
                            try:
                                await self._page.goto('https://www.naukri.com/mnjuser/profile?id=&altresid', timeout=60000)
                                await self._page.wait_for_selector('#lazyResumeHead, .resumeHeadline', timeout=30000)
                            except Exception as e:
                                print(f"      ⚠️ Navigation error: {e}")
                            await asyncio.sleep(random.uniform(4, 8))
                            
                            # Step 4: Click edit again
                            edit2_result = await self._page.evaluate("""() => {
                                const headlineSection = document.querySelector('#lazyResumeHead, .resumeHeadline');
                                if (!headlineSection) return 'NO_HEADLINE_SECTION';
                                const editIcon = headlineSection.querySelector('span.edit.icon, span.icon.edit, [class*="edit"][class*="icon"]');
                                if (!editIcon) return 'NO_EDIT_ICON';
                                editIcon.click();
                                return 'EDIT_CLICKED_2';
                            }""")
                            print(f"   📜 Step 4 - Edit again: {edit2_result}")
                            
                            await asyncio.sleep(random.uniform(4, 8))  # Wait for second modal to open
                            
                            # Step 5: Add fullstop back using keyboard
                            add_result = await self._page.evaluate("""() => {
                                const textarea = document.querySelector('#resumeHeadline, textarea[id="resumeHeadline"]');
                                if (!textarea) return 'NO_TEXTAREA';
                                if (!textarea.value.endsWith('.')) return 'NEEDS_FULLSTOP';
                                return 'ALREADY_HAS_FULLSTOP';
                            }""")
                            
                            if add_result == 'NEEDS_FULLSTOP':
                                # Robust Method: Select All -> Rewrite with dot
                                text_val = await self._page.evaluate("document.querySelector('#resumeHeadline').value")
                                if not text_val.endswith('.'):
                                    new_text = text_val + '.'
                                    
                                    textarea = self._page.locator('#resumeHeadline')
                                    await textarea.focus()
                                    await textarea.select_text()
                                    await textarea.press('Backspace')
                                    await asyncio.sleep(0.5)
                                    await textarea.type(new_text)
                                    add_result = 'FULLSTOP_ADDED'
                            
                            print(f"   📜 Step 5 - Add fullstop: {add_result}")
                            
                            await asyncio.sleep(random.uniform(4, 8))  # Wait before second Save
                            
                            # Step 6: Click Save button
                            try:
                                save_btn2 = self._page.locator('.form-actions button.btn-dark-ot, .action.s12 button.btn-dark-ot, button.btn-dark-ot[type="submit"]').first
                                await save_btn2.wait_for(state='visible', timeout=5000)
                                await save_btn2.scroll_into_view_if_needed()
                                await save_btn2.dblclick()
                                save2_result = 'SAVE_CLICKED_2'
                            except Exception as e:
                                print(f"      ⚠️ Save error: {e}")
                                save2_result = 'NO_SAVE_BUTTON'
                            print(f"   📜 Step 6 - Second save: {save2_result}")
                            
                            print("🎉 Profile headline updated successfully!")
                            self.state.task_complete = True
                            break
                            
                    except Exception as e:
                        print(f"⚠️ Profile update error: {e}")
                
                # Naukri Employment LWD Update - Set Expected Last Working Day
                if 'profile' in current_url and 'naukri.com' in current_url and 'Employment' in self._task_description:
                    print("📅 Naukri Employment - Running LWD update...")
                    try:
                        # Step 1: Click the Employment section's edit icon
                        edit_result = await self._page.evaluate("""() => {
                            // More robust selectors for Employment section
                            // Try multiple ways to find the Employment section's edit icon
                            
                            // Method 1: Find by lazy load ID
                            let empSection = document.querySelector('#lazyEmployment');
                            
                            // Method 2: Find by data-plugin attribute
                            if (!empSection) {
                                empSection = document.querySelector('[data-plugin="lazyload"][id*="Employment"]');
                            }
                            
                            // Method 3: Find parent containing "Employment" heading
                            if (!empSection) {
                                const headings = document.querySelectorAll('h2, h3, .widgetHead');
                                for (let h of headings) {
                                    if (h.innerText && h.innerText.trim() === 'Employment') {
                                        empSection = h.closest('.widgetContainer, [class*="widget"], .card, section');
                                        break;
                                    }
                                }
                            }
                            
                            if (empSection) {
                                // Find edit icon - try multiple selectors
                                const editSelectors = [
                                    'span.edit.icon',
                                    '.edit.icon',
                                    '[class*="edit"][class*="icon"]',
                                    'span[class*="edit"]',
                                    '.editIcon'
                                ];
                                
                                for (let sel of editSelectors) {
                                    const editIcons = empSection.querySelectorAll(sel);
                                    if (editIcons.length > 0) {
                                        editIcons[0].click();
                                        return 'EDIT_CLICKED';
                                    }
                                }
                            }
                            
                            // Last resort: Find any edit icon near text "Software Engineer" or "Fiserv"
                            const allEditIcons = document.querySelectorAll('span.edit.icon, .edit.icon');
                            for (let icon of allEditIcons) {
                                const parent = icon.closest('.row, div[class*="item"], .card');
                                if (parent) {
                                    const text = parent.innerText || '';
                                    if (text.includes('Software Engineer') || text.includes('Fiserv')) {
                                        icon.click();
                                        return 'EDIT_CLICKED';
                                    }
                                }
                            }
                            
                            return 'NO_EMPLOYMENT_SECTION';
                        }""")
                        print(f"   📜 Step 1 - Employment edit: {edit_result}")
                        
                        if edit_result == 'EDIT_CLICKED':
                            await asyncio.sleep(random.uniform(3, 5))  # Wait for modal to open
                            
                            # Step 2: Calculate system date + days (31 or 30 based on task description)
                            days_offset = 31 if ('31 days' in self._task_description or '+31' in self._task_description) else 30
                            future_date = datetime.now() + timedelta(days=days_offset)
                            year_val = str(future_date.year)
                            month_num = str(future_date.month)  # Month NUMBER for data-id
                            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                            month_display = month_names[future_date.month - 1]  # For logging
                            day_val = str(future_date.day)
                            
                            print(f"   📅 Setting LWD to: {day_val} {month_display} {year_val}")
                            
                            # Step 3: Set dropdowns using EXACT data-id selector WITH RETRY
                            async def set_single_dropdown(name, dropdown_id, data_prefix, option_value, max_retries=3):
                                print(f"   📅 Setting {name} to {option_value}...")
                                for attempt in range(max_retries):
                                    try:
                                        # 1. Click dropdown to open (with short timeout)
                                        await self._page.click(dropdown_id, timeout=5000)
                                        await asyncio.sleep(0.8)
                                        
                                        # 2. Try data-id selector first
                                        data_id = f"{data_prefix}{option_value}"
                                        result = await self._page.evaluate("""(dataId) => {
                                            const anchor = document.querySelector('a[data-id="' + dataId + '"]');
                                            if (anchor && anchor.offsetParent !== null) {
                                                anchor.scrollIntoView({block: 'center'});
                                                anchor.click();
                                                return 'SELECTED';
                                            }
                                            // Fallback: Find by text within open dropdown
                                            const openDropdown = document.querySelector('.dropdownList[style*="display: block"], .dropdownList:not([style*="display: none"])');
                                            if (openDropdown) {
                                                const items = openDropdown.querySelectorAll('li a, li');
                                                for (let item of items) {
                                                    if ((item.innerText || '').trim() === dataId.split('_')[1]) {
                                                        item.click();
                                                        return 'SELECTED_BY_TEXT';
                                                    }
                                                }
                                            }
                                            return 'NOT_FOUND: ' + dataId;
                                        }""", data_id)
                                        
                                        if 'SELECTED' in result:
                                            # 3. Close dropdown
                                            await asyncio.sleep(0.3)
                                            await self._page.evaluate("() => document.body.click()")
                                            await asyncio.sleep(0.3)
                                            return f"{result}: {option_value}"
                                        
                                        # If not found, close dropdown and retry
                                        await self._page.evaluate("() => document.body.click()")
                                        await asyncio.sleep(0.5)
                                        
                                    except Exception as e:
                                        if attempt < max_retries - 1:
                                            print(f"      ⚠️ Retry {attempt + 1}/{max_retries} for {name}: {str(e)[:50]}")
                                            await asyncio.sleep(1)
                                        else:
                                            return f"ERROR: {e}"
                                
                                return f"FAILED_AFTER_{max_retries}_ATTEMPTS: {option_value}"

                            # Execute with data-id prefixes (month uses NAME like lwdMonth_Feb)
                            year_result = await set_single_dropdown('Year', '#lwdYearFor', 'lwdYear_', year_val)
                            # Use month_num (e.g. '3') instead of text ('Mar') to match generic data-id patterns (like lwdDay_1)
                            month_result = await set_single_dropdown('Month', '#lwdMonthFor', 'lwdMonth_', month_num)
                            day_result = await set_single_dropdown('Day', '#lwdDayFor', 'lwdDay_', day_val)
                            
                            print(f"   📜 Step 2 - Dropdowns: Year={year_result}, Month={month_result}, Day={day_result}")
                            
                            print("   ⏳ Waiting 2s for state to settle before saving...")
                            await asyncio.sleep(2)
                            
                            # Step 4: Click Save button with multiple fallback attempts
                            save_result = 'NOT_ATTEMPTED'
                            for save_attempt in range(3):
                                save_result = await self._page.evaluate("""() => {
                                    // Try multiple selectors for save button
                                    const selectors = [
                                        '#submitEmployment',
                                        'button[type="submit"]',
                                        'button.btn-dark-ot', 
                                        'button.waves-effect'
                                    ];
                                    for (let sel of selectors) {
                                        const btn = document.querySelector(sel);
                                        if (btn && btn.offsetParent !== null) {
                                            btn.scrollIntoView({block: 'center'});
                                            btn.click();
                                            return 'SAVE_CLICKED: ' + sel;
                                        }
                                    }
                                    // Fallback: find by text
                                    const allBtns = document.querySelectorAll('button');
                                    for (let btn of allBtns) {
                                        if ((btn.innerText || '').trim().toLowerCase() === 'save' && btn.offsetParent !== null) {
                                            btn.scrollIntoView({block: 'center'});
                                            btn.click();
                                            return 'SAVE_CLICKED: text-match';
                                        }
                                    }
                                    return 'NO_SAVE_BUTTON';
                                }""")
                                
                                if 'SAVE_CLICKED' in save_result:
                                    break
                                await asyncio.sleep(1)
                            
                            print(f"   📜 Step 3 - Save: {save_result}")
                            
                            # Wait for page to reload to profile URL (success indicator) - shorter timeout
                            try:
                                await self._page.wait_for_url('**/mnjuser/profile**', timeout=8000)
                                print(f"🎉 Employment LWD updated to {day_val} {month_display} {year_val}!")
                                self.state.task_complete = True
                                break
                            except Exception:
                                # Check if modal closed anyway (alternative success indicator)
                                modal_gone = await self._page.evaluate("""() => {
                                    return !document.querySelector('.modal-content, .edit-container');
                                }""")
                                if modal_gone:
                                    print(f"🎉 Employment LWD updated (modal closed)!")
                                    self.state.task_complete = True
                                    break
                                print("      ⚠️ Page didn't reload to profile. Will retry...")
                            
                    except Exception as e:
                        print(f"⚠️ Employment LWD update error: {e}")
                
                # Naukri Early Access Jobs - Share Interest
                if 'recommended-earjobs' in current_url and 'naukri.com' in current_url:
                    print("🚀 Naukri Early Access - Clicking Share Interest...")
                    try:
                        # Click the first "Share interest" button
                        share_result = await self._page.evaluate("""() => {
                            // Try specific selector first
                            const specificBtn = document.querySelector("body > main > div > div > div > section.lp__left-section-container > div > div:nth-child(1) > div > div.row7 > div > div.tf__content > button");
                            if (specificBtn && specificBtn.offsetParent !== null) {
                                specificBtn.click();
                                return 'SHARE_CLICKED_SPECIFIC';
                            }
                            
                            // Fallback: Find any "Share interest" button
                            const allBtns = document.querySelectorAll('button');
                            for (let btn of allBtns) {
                                if (btn.innerText && btn.innerText.toLowerCase().includes('share interest')) {
                                    if (btn.offsetParent !== null) {
                                        btn.click();
                                        return 'SHARE_CLICKED';
                                    }
                                }
                            }
                            return 'NO_SHARE_BUTTON';
                        }""")
                        print(f"   📜 Share Interest: {share_result}")
                        
                        if 'SHARE_CLICKED' in share_result:
                            await asyncio.sleep(random.uniform(2, 4))
                            
                            # Verify success
                            success = await self._page.evaluate("""() => {
                                // Check for success message
                                const successMsg = document.querySelector('.apply-status-header.green .apply-message, .apply-status-header .apply-message');
                                if (successMsg && successMsg.innerText.toLowerCase().includes('interest shared')) {
                                    return true;
                                }
                                // Also check for general success text on page
                                return document.body.innerText.includes('Interest shared successfully');
                            }""")
                            
                            if success:
                                print("🎉 Interest shared successfully!")
                            else:
                                print("✅ Share Interest clicked (success not verified)")
                            
                            self.state.task_complete = True
                            break
                        else:
                            print("⚠️ No Share Interest button found")
                            self.state.task_complete = True
                            break
                            
                    except Exception as e:
                        print(f"⚠️ Early Access error: {e}")
                
                
                # Naukri: Handle CHECKBOX_CLICKED_NEED_MORE - continue selecting more checkboxes
                if 'CHECKBOX_CLICKED_NEED_MORE' in result and 'naukri.com' in current_url:
                    # Extract count info from result (e.g., "CHECKBOX_CLICKED_NEED_MORE: 2/5")
                    try:
                        count_info = result.split(': ')[1] if ': ' in result else ''
                        print(f"📋 Selected job {count_info}, continuing to select more...")
                    except:
                        print(f"📋 Checkbox selected, continuing to select more...")
                    await asyncio.sleep(random.uniform(0.5, 1))
                    continue  # Continue loop to select more checkboxes
                
                # Naukri: After checkbox, try Apply immediately (only for regular CHECKBOX_CLICKED, not NEED_MORE)
                if 'CHECKBOX_CLICKED' in result and 'NEED_MORE' not in result and 'naukri.com' in current_url:
                    print("✅ Checkbox clicked, trying Apply...")
                    await asyncio.sleep(random.uniform(4, 8))
                    # Try to click apply immediately with robust logic and 2s monitoring
                    # NOTE: Using regular function expression for better Playwright compatibility
                    apply_result = await self._page.evaluate("""function() {
                        const applyBtn = document.querySelector('.multi-apply-button');
                        if (applyBtn && applyBtn.offsetParent !== null) {
                            applyBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
                            // NOTE: await removed - Python handles delays between evaluate calls

                            applyBtn.click();
                            applyBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            applyBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            applyBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));

                            // MONITOR: Check for error snackbar
                            // NOTE: Loop-based await removed - single check only, Python handles polling
                            for (let i = 0; i < 1; i++) {
                                // NOTE: await new Promise removed - Python handles delays between evaluate calls
                                // Target the exact structure found in DOM inspection
                                const snackBody = document.querySelector('.ss-snackbar-body');
                                if (snackBody && snackBody.offsetParent !== null) {
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong')) {
                                        // Dismiss if close button exists
                                        const closeBtn = document.querySelector('button.ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }
                                }
                                // Generic fallback check
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"]');
                                if (genericSnack && genericSnack.innerText.toLowerCase().includes('error')) {
                                    return 'NAUKRI_RATE_LIMITED: Generic error detected';
                                }
                            }
                            return 'APPLY_CLICKED';
                        }
                        return 'NO_APPLY_BUTTON';
                    }""")
                    
                    # Playwright fallback if JS click didn't trigger modal (and no error detected)
                    if 'NO_APPLY_BUTTON' in apply_result or (apply_result == 'APPLY_CLICKED' and not await self._page.is_visible('.chatbot_DrawerContentWrapper')):
                        print("⚠️ JS click failed or button not found, trying Playwright native click fallback...")
                        try:
                            await self._page.click('.multi-apply-button', timeout=3000)
                            apply_result = 'APPLY_CLICKED_FALLBACK'
                        except Exception as e:
                            print(f"⚠️ Playwright fallback click also failed: {e}")
                    
                    print(f"   📜 Apply result: {apply_result}")
                    
                    if 'APPLY_CLICKED' in apply_result:
                        print("⏳ Waiting for Naukri chatbot...")
                        await asyncio.sleep(random.uniform(4, 8))
                        chatbot_done = await self._handle_chatbot_loop()
                        if chatbot_done == 'CONTINUE':
                            # MCC popup detected, continue main loop for scripted fallback
                            continue
                        elif isinstance(chatbot_done, str) and 'NAUKRI_RATE_LIMITED' in chatbot_done:
                            # Error popup detected - set rate limit and exit
                            self.naukri_rate_limit_until = datetime.now() + timedelta(hours=3)
                            print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                            self.state.task_complete = True
                            break
                        elif chatbot_done:
                            print("🎉 Naukri Application Completed!")
                            self.state.task_complete = True
                            break
                
                # Naukri Chatbot handling (for direct APPLY_CLICKED)
                if 'APPLY_CLICKED' in result and 'LINKEDIN' not in result and 'naukri.com' in current_url:
                    print("⏳ Waiting for Naukri chatbot...")
                    await asyncio.sleep(random.uniform(4, 8))
                    chatbot_done = await self._handle_chatbot_loop()
                    if chatbot_done == 'CONTINUE':
                        continue
                    elif isinstance(chatbot_done, str) and 'NAUKRI_RATE_LIMITED' in chatbot_done:
                        # Error popup detected - set rate limit and exit
                        self.naukri_rate_limit_until = datetime.now() + timedelta(hours=3)
                        print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                        self.state.task_complete = True
                        break
                    elif chatbot_done:
                        # Check if this was a partial application (less than target)
                        if 'PARTIAL' in result:
                            # Extract how many were applied (e.g., "APPLY_CLICKED_PARTIAL: 2/5" -> 2)
                            try:
                                applied_count = int(result.split(': ')[1].split('/')[0])
                                target_count = int(result.split('/')[1])
                                print(f"🔄 Applied to {applied_count}/{target_count} jobs. Looking for more on next section...")
                            except:
                                print("🔄 Partial application. Looking for more jobs on next section...")
                            
                            # Navigate to next tab to find more jobs
                            await asyncio.sleep(2)
                            next_tab_result = await self._page.evaluate("""() => {
                                // Tab IDs in order: profile -> apply -> preference -> similar_jobs -> top_candidate
                                const tabIds = ['profile', 'apply', 'preference', 'similar_jobs', 'top_candidate'];
                                const tabNames = ['Profile', 'Applies', 'Preferences', 'You might like', 'Top Candidate'];
                                
                                // Find which tab is currently active
                                let currentTabIndex = -1;
                                for (let i = 0; i < tabIds.length; i++) {
                                    const wrapper = document.querySelector('#' + tabIds[i]);
                                    if (wrapper) {
                                        const activeItem = wrapper.querySelector('.tab-list-active');
                                        if (activeItem) {
                                            currentTabIndex = i;
                                            break;
                                        }
                                    }
                                }
                                
                                // Try to click the next tab
                                const nextTabIndex = currentTabIndex + 1;
                                if (nextTabIndex < tabIds.length) {
                                    const nextTabId = tabIds[nextTabIndex];
                                    const nextTabName = tabNames[nextTabIndex];
                                    
                                    const nextWrapper = document.querySelector('#' + nextTabId);
                                    if (nextWrapper) {
                                        const tabItem = nextWrapper.querySelector('.tab-list-item');
                                        if (tabItem && tabItem.offsetParent !== null) {
                                            tabItem.click();
                                            return 'TAB_CLICKED: ' + nextTabName;
                                        }
                                        nextWrapper.click();
                                        return 'TAB_CLICKED: ' + nextTabName;
                                    }
                                }
                                
                                return 'NO_MORE_TABS';
                            }""")
                            
                            if 'TAB_CLICKED' in next_tab_result:
                                tab_name = next_tab_result.split(': ')[1] if ': ' in next_tab_result else 'Unknown'
                                print(f"📑 Switched to tab: {tab_name} to find more jobs")
                                await asyncio.sleep(random.uniform(4, 8))
                                continue  # Continue loop to find and apply to more jobs
                            else:
                                print("📭 No more tabs available. Finishing with current applications.")
                        
                        print("🎉 Naukri Application Completed!")
                        self.state.task_complete = True
                        break
                
                # Naukri: Chatbot detected by scripted fallback - trigger chatbot loop
                if result == 'CHATBOT_DETECTED' and 'naukri.com' in current_url:
                    chatbot_done = await self._handle_chatbot_loop()
                    if chatbot_done == 'CONTINUE':
                        continue  # MCC popup, let scripted fallback handle it
                    elif chatbot_done:
                        print("🎉 Naukri Application Completed!")
                        self.state.task_complete = True
                        break
                
                # Naukri: Tab clicked - wait for page to load new jobs
                if 'TAB_CLICKED' in result and 'naukri.com' in current_url:
                    tab_name = result.split(': ')[1] if ': ' in result else 'Unknown'
                    if 'FOR_MORE' in result:
                        print(f"📑 Only 1 job in current section - switching to tab: {tab_name} to select 2 jobs")
                    else:
                        print(f"📑 Switched to tab: {tab_name}")
                    await asyncio.sleep(random.uniform(4, 8))  # Wait for new jobs to load
                    continue  # Continue to try finding checkboxes on new tab
                
                # Naukri: No more tabs to check
                if 'NO_MORE_TABS_NAUKRI' in result:
                    print("📭 All Naukri tabs checked. No more jobs with checkboxes.")
                    self.state.task_complete = True
                    break
                
                # Handle NO_MORE_JOBS
                if 'NO_MORE_JOBS' in result:
                    print(f"   ℹ️ Result: {result}")  # Debug log
                    if 'NO_CARDS' in result:
                        print("❌ No job cards found on page! Check selectors.")
                    else:
                        print("📭 No more jobs to apply. Task complete.")
                    self.state.task_complete = True
                    break
                
                # Instahyre: Show Results clicked - continue to View/Apply phase
                if 'INSTAHYRE_SHOW_RESULTS_CLICKED' in result:
                    print("🔍 Instahyre search configured, now looking for jobs to apply...")
                    await asyncio.sleep(random.uniform(3, 5))  # Wait for results to load
                    continue  # Continue to View/Apply loop
                
                # Instahyre: Application submitted
                if 'INSTAHYRE_APPLY_CLICKED' in result:
                    if not hasattr(self, '_instahyre_apply_count'):
                        self._instahyre_apply_count = 0
                    self._instahyre_apply_count += 1
                    print(f"✅ Instahyre Application {self._instahyre_apply_count}/10 submitted!")
                    
                    if self._instahyre_apply_count >= 10:
                        print("🎉 Completed 10 Instahyre applications!")
                        self._instahyre_apply_count = 0  # Reset for next cycle
                        self.state.task_complete = True
                        break
                    
                    await asyncio.sleep(random.uniform(2, 4))  # Wait for modal to close
                    continue  # Continue to next application
                
                # Instahyre: View clicked - wait for modal
                if 'INSTAHYRE_VIEW_CLICKED' in result:
                    print("👁️ Viewing job details, looking for Apply button...")
                    await asyncio.sleep(random.uniform(2, 3))  # Wait for modal to open
                    continue
                
                # Instahyre: Modal closed after success
                if 'INSTAHYRE_MODAL_CLOSED_SUCCESS' in result:
                    print("✅ Application confirmed, looking for next job...")
                    await asyncio.sleep(random.uniform(1, 2))
                    continue
                
                # Instahyre: No more jobs
                if 'INSTAHYRE_NO_MORE_JOBS' in result:
                    applied_count = getattr(self, '_instahyre_apply_count', 0)
                    print(f"📭 No more Instahyre jobs found. Applied to {applied_count} jobs.")
                    self._instahyre_apply_count = 0
                    self.state.task_complete = True
                    break
                
                # Instahyre: Other actions (scrolling, etc.)
                if 'INSTAHYRE_' in result and 'instahyre.com' in current_url:
                    print(f"   📜 Instahyre: {result}")
                    await asyncio.sleep(random.uniform(1, 2))
                    continue
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                await self._screenshot_on_error("main_loop_error")
                self.state.errors.append(str(e))
                self.metrics['errors_encountered'] += 1
                if len(self.state.errors) > 5:
                    print("🚨 Too many errors. Stopping.")
                    break
        
        # Save metrics at end of task
        self.metrics['success'] = self.state.task_complete
        self._save_metrics()
        
        return self.state.task_complete

    async def _handle_chatbot_loop(self) -> "bool | str":
        """Handle Naukri chatbot questionnaire. Returns True if done, 'CONTINUE' for MCC popup, False on failure."""
        patterns_json = json.dumps(KNOWN_QA_PATTERNS)
        max_iterations = 20
        
        for iteration in range(max_iterations):
            await asyncio.sleep(random.uniform(1.5, 3))
            
            result = await self._page.evaluate(f"""async () => {{
                const KNOWN_PATTERNS = {patterns_json};
                
                const fuzzyMatch = (question) => {{
                    if (!question) return null;
                    const qLower = question.toLowerCase().trim();
                    for (const [key, val] of Object.entries(KNOWN_PATTERNS)) {{
                        if (qLower.includes(key.toLowerCase())) return val;
                    }}
                    return null;
                }};
                
                // PRIORITY 0: Check for error snackbar immediately
                const snackBody = document.querySelector('.ss-snackbar-body');
                if (snackBody && snackBody.offsetParent !== null) {{
                    const snackText = snackBody.innerText.toLowerCase();
                    if (snackText.includes('error') || snackText.includes('limit') || snackText.includes('reached') || snackText.includes('something went wrong')) {{
                        const closeBtn = document.querySelector('button.ss-close');
                        if (closeBtn) closeBtn.click();
                        return 'NAUKRI_RATE_LIMITED: Error popup detected at loop start';
                    }}
                }}
                // Generic fallback
                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"]');
                if (genericSnack && genericSnack.innerText.toLowerCase().includes('error')) {{
                    return 'NAUKRI_RATE_LIMITED: Generic error at loop start';
                }}
                
                // Check for MCC/update popup (needs main loop handling)
                const mccPopup = document.querySelector('.mcc-popup, [class*="update-popup"], [class*="confirmation-modal"]');
                if (mccPopup && mccPopup.offsetParent !== null) {{
                    return 'MCC_POPUP_DETECTED';
                }}
                
                // Check for success/completion
                const successIndicators = [
                    document.querySelector('.chatbot_SuccessMsg'),
                    document.querySelector('[class*="success"]'),
                    document.body.innerText.includes('Application submitted'),
                    document.body.innerText.includes('Successfully applied')
                ];
                if (successIndicators.some(Boolean)) {{
                    return 'CHATBOT_COMPLETE';
                }}
                
                // Check if chatbot is visible (try multiple selectors)
                let chatLayer = document.querySelector('.chatbot_DrawerContentWrapper');
                if (!chatLayer) {{
                    // Try alternative selectors for Naukri questionnaire modals
                    chatLayer = document.querySelector('[class*="drawer"], [class*="modal"], [role="dialog"]');
                }}
                if (!chatLayer || chatLayer.offsetParent === null) {{
                    // Chatbot not visible - check if already done
                    if (document.body.innerText.includes('applied')) {{
                        return 'CHATBOT_COMPLETE';
                    }}
                    return 'NO_CHATBOT';
                }}
                
                // Handle question input - search more broadly in chatLayer OR globally
                let questionEl = chatLayer.querySelector('.chatbot_QuestionContainer, .botMsg, [class*="question"]');
                let qText = '';
                if (questionEl) {{
                    qText = questionEl.innerText || '';
                }} else {{
                    // Fallback: get any text content from the modal that looks like a question
                    qText = chatLayer.innerText || '';
                }}
                
                const answer = fuzzyMatch(qText) || '3.8';
                
                // Try text input - GLOBAL SEARCH FIRST for Naukri's specific input
                let input = document.querySelector('input[placeholder*="Type message"], input[placeholder*="type message"], input[placeholder*="message here"]');
                if (!input || !input.offsetParent) {{
                    // Try chatLayer if available
                    if (chatLayer) {{
                        input = chatLayer.querySelector('input[type="text"], textarea, input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])');
                    }}
                }}
                if (!input || !input.offsetParent) {{
                    // Global fallback for any visible input
                    input = document.querySelector('[role="dialog"] input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), [class*="modal"] input:not([type="hidden"]), textarea');
                }}
                
                if (input && input.offsetParent !== null) {{
                    if (!input.value || input.value.trim() === '') {{
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        if (setter) setter.call(input, answer);
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        
                        // Click Save button - search for button with Save text first
                        let saveBtn = Array.from(document.querySelectorAll('button, div[tabindex], [role="button"]')).find(el => 
                            el.innerText.toLowerCase().trim() === 'save' && el.offsetParent !== null);
                        if (!saveBtn) {{
                            saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                        }}
                        if (saveBtn && saveBtn.offsetParent !== null) {{
                            saveBtn.click();
                            return 'CHATBOT_ANSWERED_AND_SAVE: ' + qText.slice(0, 50);
                        }}
                        return 'CHATBOT_ANSWERED: ' + qText.slice(0, 50);
                    }}
                }}
                
                // Try dropdown (INDEPENDENT block - not nested inside input)
                const select = chatLayer.querySelector('select');
                if (select && select.offsetParent !== null) {{
                    const selectOptions = Array.from(select.options);
                    // Try to find matching option
                    for (const opt of selectOptions) {{
                        if (opt.text.toLowerCase().includes(answer.toLowerCase())) {{
                            select.value = opt.value;
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            // Click Save after selecting dropdown
                            const saveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                            if (saveDiv && saveDiv.offsetParent !== null) {{
                                saveDiv.click();
                                return 'CHATBOT_DROPDOWN_AND_SAVE: ' + opt.text;
                            }}
                            return 'CHATBOT_SELECTED: ' + opt.text;
                        }}
                    }}
                    // Default to first non-empty option
                    if (selectOptions.length > 1) {{
                        select.selectedIndex = 1;
                        select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        const saveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                        if (saveDiv && saveDiv.offsetParent !== null) {{
                            saveDiv.click();
                            return 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE';
                        }}
                        return 'CHATBOT_SELECTED_DEFAULT';
                    }}
                }}
                
                // Try radio buttons (INDEPENDENT block - prefer Yes/Serving Notice)
                const radios = chatLayer.querySelectorAll('input[type="radio"]');
                let clickedRadio = false;
                for (const radio of radios) {{
                    const label = radio.parentElement?.innerText || radio.nextSibling?.textContent || '';
                    if (label.toLowerCase().includes('yes') || label.toLowerCase().includes('serving')) {{
                        if (!radio.checked) {{
                            radio.click();
                            clickedRadio = true;
                        }}
                        break;
                    }}
                }}
                // If no preferred radio found but radios exist, click first unchecked one
                if (!clickedRadio && radios.length > 0) {{
                    for (const radio of radios) {{
                        if (!radio.checked) {{
                            radio.click();
                            clickedRadio = true;
                            break;
                        }}
                    }}
                }}
                
                // After selecting radio, click Save/Submit button
                if (clickedRadio) {{
                    // PRIORITY 1: Naukri's Save button is div.sendMsg (not a button element!)
                    const naukSaveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg, #sendMsg__vjhkrpzhhInputBox .sendMsg');
                    if (naukSaveDiv && naukSaveDiv.offsetParent !== null) {{
                        naukSaveDiv.click();
                        return 'CHATBOT_RADIO_AND_SAVE';
                    }}
                    
                    // PRIORITY 2: Find Save button by text content in modal
                    const allButtons = chatLayer ? 
                        Array.from(chatLayer.querySelectorAll('button, div[tabindex], span[tabindex]')) : 
                        Array.from(document.querySelectorAll('[role="dialog"] button, [class*="modal"] button'));
                    
                    for (const btn of allButtons) {{
                        const btnText = btn.innerText.toLowerCase().trim();
                        if ((btnText === 'save' || btnText === 'submit' || btnText === 'next' || btnText === 'continue') 
                            && btn.offsetParent !== null) {{
                            btn.click();
                            return 'CHATBOT_RADIO_AND_SAVE';
                        }}
                    }}
                    
                    // PRIORITY 3: Global search for any visible Save element
                    const globalSave = Array.from(document.querySelectorAll('button, div[tabindex], [role="button"]')).find(el => 
                        el.innerText.toLowerCase().trim() === 'save' && el.offsetParent !== null);
                    if (globalSave) {{
                        globalSave.click();
                        return 'CHATBOT_GLOBAL_SAVE';
                    }}
                    
                    return 'CHATBOT_RADIO_CLICKED';
                }}
                
                // Try option buttons (INDEPENDENT block)
                const optionBtns = chatLayer.querySelectorAll('.chatbot_OptionContainer button, [class*="option"] button');
                if (optionBtns.length > 0) {{
                    optionBtns[0].click();
                    return 'CHATBOT_OPT_CLICKED';
                }}
                
                // Try to click Send/Submit/Next button
                const sendBtns = chatLayer.querySelectorAll('.chatbot_sendBtn, button.send, button[class*="send"], button[class*="submit"], button[class*="next"]');
                for (const btn of sendBtns) {{
                    if (btn.offsetParent !== null && !btn.disabled) {{
                        btn.click();
                        return 'CHATBOT_SENT';
                    }}
                }}
                
                // Check for any clickable button
                const anyBtn = chatLayer.querySelector('button:not([disabled])');
                if (anyBtn && anyBtn.offsetParent !== null) {{
                    anyBtn.click();
                    return 'CHATBOT_BTN_CLICKED';
                }}
                
                return 'CHATBOT_WAITING';
            }}""")
            
            # Only log CHATBOT_WAITING every 5th iteration to reduce noise
            if result != 'CHATBOT_WAITING' or iteration % 5 == 0:
                print(f"   📜 Chatbot[{iteration}]: {result}")
            
            if result == 'CHATBOT_COMPLETE':
                self.metrics['applications_submitted'] += 1
                return True
            elif result == 'MCC_POPUP_DETECTED':
                return 'CONTINUE'  # Signal main loop to handle MCC
            elif 'NAUKRI_RATE_LIMITED' in result:
                # Error popup detected - return to main loop for rate limiting
                return result
            elif result == 'NO_CHATBOT':
                # Check if maybe we're done
                if iteration > 3:
                    return True
                continue
            elif 'CHATBOT_WAITING' in result:
                # Nothing to do, wait
                continue
        
        print("⚠️ Chatbot loop exhausted")
        return False

    async def _handle_scripted_fallback(self) -> str:
        """Execute the scripted JavaScript fallback logic and return the result string."""
        # Serialize patterns for JS injection
        patterns_json = json.dumps(KNOWN_QA_PATTERNS)
        
        try:
            # We use a formatted string to inject the JSON, but we must escape braces for the JS function
            # NOTE: This function must NOT use async/await - Playwright's evaluate handles timing via Python asyncio
            # Using a function expression (wrapped in parens) - function statements require a name in JS
            js_code = f"""(function() {{
                // 1. INJECTED KNOWLEDGE
                const KNOWN_PATTERNS = {patterns_json};
                const MAX_RETRIES = 3;
                
                // 2. SHARED UTILS (Restored from Legacy)
                // NOTE: sleep removed - use Python's asyncio.sleep() between evaluate calls instead
                // const sleep = (ms) => new Promise(r => setTimeout(r, ms));  // REMOVED - causes SyntaxError
                const isVisible = (elem) => !!(elem && (elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length));

                // Fuzzy Matcher implementation
                const fuzzyMatch = (question) => {{
                    if (!question) return null;
                    const qLower = question.toLowerCase().trim();
                    // Direct Key Lookup
                    for (const [key, val] of Object.entries(KNOWN_PATTERNS)) {{
                        if (qLower.includes(key.toLowerCase())) return val;
                    }}
                    return null;
                }};               
                
                // Helper: Find best matching option
                const findBestMatch = (answer, options) => {{
                    if (!answer || !options) return null;
                    const ans = answer.toLowerCase();
                    for (const opt of options) {{
                        const text = (opt.text || opt.label || '').toLowerCase();
                        if (text.includes(ans) || ans.includes(text)) return opt;
                    }}
                    return null;
                }};
                
                // Helper: Find salary range match for range-based options
                const findSalaryRangeMatch = (answer, options, isCurrentSalary) => {{
                    if (!answer || !options || options.length === 0) return null;
                    
                    // Extract numeric salary from answer (e.g., "13.5 LPA" → 13.5)
                    const salaryMatch = answer.match(/(\d+(?:\.\d+)?)/);
                    if (!salaryMatch) return null;
                    const salary = parseFloat(salaryMatch[1]);
                    
                    let bestMatch = null;
                    let bestScore = -1;
                    
                    for (const opt of options) {{
                        const text = (opt.text || opt.label || '').toLowerCase();
                        
                        // Match patterns like "0-5 Lacs", "10-15 Lacs Per Annum", "5 to 10 LPA"
                        const rangeMatch = text.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                        if (rangeMatch) {{
                            const min = parseFloat(rangeMatch[1]);
                            const max = parseFloat(rangeMatch[2]);
                            
                            // Check if salary falls within this range
                            if (salary >= min && salary <= max) {{
                                // Score based on how centered the salary is in the range
                                const rangeCenter = (min + max) / 2;
                                const score = 1 - Math.abs(salary - rangeCenter) / (max - min);
                                
                                if (score > bestScore) {{
                                    bestScore = score;
                                    bestMatch = opt;
                                }}
                            }}
                        }}
                    }}
                    
                    return bestMatch;
                }};                
                
                // Helper: Check if answer is affirmative
                const isYes = (ans) => ans && ['yes', 'true', 'agree'].some(w => ans.toLowerCase().includes(w));
                const isNo = (ans) => ans && ['no', 'false'].some(w => ans.toLowerCase().includes(w));

                const isLinkedIn = document.title.includes('LinkedIn') || window.location.href.includes('linkedin.com');
                const isNaukri = document.title.includes('Naukri') || window.location.href.includes('naukri.com');
                const isInstahyre = document.title.includes('Instahyre') || window.location.href.includes('instahyre.com');

                // ============================================================
                // LINKEDIN LOGIC (Restored)
                // ============================================================
                if (isLinkedIn) {{
                    // FIRST: Check for city dropdown and select first option
                    const cityDropdown = document.querySelector('[role="listbox"]');
                    if (cityDropdown) {{
                        const options = cityDropdown.querySelectorAll('[role="option"]');
                        if (options.length > 0) {{
                            // Click the first option
                            options[0].click();
                            return 'LINKEDIN_CITY_SELECTED';
                        }}
                    }}
                    
                    // DEBUG: Log DOM structure for troubleshooting
                    console.log('=== LINKEDIN DOM DEBUG ===');
                    console.log('URL: ' + window.location.href);
                    console.log('Title: ' + document.title);
                    
                    // Check sidebar selectors
                    const debugSelectors = [
                        '.jobs-search-results-list',
                        '.scaffold-layout__list-container',
                        'ul.scaffold-layout__list-container',
                        '.jobs-search-results-list__list',
                        '[data-test-results-list]',
                        '.jobs-search-two-pane__results-list',
                        '.scaffold-layout__list',
                        '[role="main"] .scaffold-layout__list-container',
                        '.jobs-search__results-list',
                        'div[class*="results-list"]'
                    ];
                    console.log('Sidebar detection:');
                    for (const sel of debugSelectors) {{
                        const el = document.querySelector(sel);
                        console.log('  ' + sel + ': ' + (el ? 'FOUND (' + el.tagName + ')' : 'not found'));
                    }}
                    
                    // Check for job cards
                    const jobCardSelectors = [
                        'li.scaffold-layout__list-item',
                        'li[data-occludable-job-id]',
                        '.job-card-container',
                        '[data-job-id]'
                    ];
                    console.log('Job card detection:');
                    for (const sel of jobCardSelectors) {{
                        const count = document.querySelectorAll(sel).length;
                        console.log('  ' + sel + ': ' + count + ' found');
                    }}
                    
                    // Check Easy Apply button
                    const easyApplyBtn = document.querySelector('button.jobs-apply-button');
                    console.log('Easy Apply button: ' + (easyApplyBtn ? 'FOUND - "' + easyApplyBtn.innerText.substring(0, 30) + '"' : 'NOT FOUND'));
                    
                    // Check current job ID
                    const currentId = new URLSearchParams(window.location.search).get('currentJobId');
                    console.log('Current Job ID: ' + currentId);
                    
                    // Check applied status
                    const bodyText = document.body.innerText;
                    if (bodyText.includes('Applied')) {{
                        const match = bodyText.match(/Applied[^\\n]{{0,50}}/);
                        console.log('Applied status: "' + (match ? match[0] : 'Found') + '"');
                    }} else {{
                        console.log('Applied status: Not applied');
                    }}
                    console.log('=== END DEBUG ===');
                    // FIRST: Check for "Job search safety reminder" modal (appears after clicking Easy Apply)
                    const safetyModal = document.querySelector('[role="dialog"]');
                    if (safetyModal) {{
                        const modalText = safetyModal.innerText || '';
                        if (modalText.includes('Job search safety reminder')) {{
                            console.log('LINKEDIN: Detected safety reminder modal');
                            
                            // DEBUG: Log all buttons found
                            const allButtons = safetyModal.querySelectorAll('button');
                            console.log('LINKEDIN: Found ' + allButtons.length + ' buttons in modal');
                            for (let i = 0; i < allButtons.length; i++) {{
                                console.log('  Button ' + i + ': "' + (allButtons[i].innerText || 'empty').trim() + '"');
                            }}
                            
                            // Find "Continue applying" button by text
                            let continueBtn = null;
                            for (const btn of allButtons) {{
                                const btnText = (btn.innerText || '').toLowerCase().trim();
                                console.log('LINKEDIN: Checking button text: "' + btnText + '"');
                                if (btnText.includes('continue')) {{
                                    continueBtn = btn;
                                    console.log('LINKEDIN: Found continue button!');
                                    break;
                                }}
                            }}
                            
                            if (continueBtn) {{
                                console.log('LINKEDIN: Clicking "Continue applying" button');
                                continueBtn.click();
                                // NOTE: await removed - Python handles delays between evaluate calls
                                return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                            }} else if (allButtons.length > 0) {{
                                // Fallback: click the LAST button (typically the primary action on right)
                                console.log('LINKEDIN: Fallback - clicking LAST button (index ' + (allButtons.length - 1) + ')');
                                const lastBtn = allButtons[allButtons.length - 1];
                                lastBtn.click();
                                // NOTE: await removed - Python handles delays between evaluate calls
                                return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                            }}
                        }}
                    }}
                    
                    // SECOND: Check for success modal ("Application sent" dialog with Done button)
                    const successModal = document.querySelector('[role="dialog"]');
                    if (successModal) {{
                        const modalText = successModal.innerText || '';
                        if (modalText.includes('Application sent') || modalText.includes('Application submitted')) {{
                            // Click Done button to close
                            const doneBtn = successModal.querySelector('button');
                            if (doneBtn && doneBtn.innerText.toLowerCase().includes('done')) {{
                                doneBtn.click();
                                // NOTE: await removed - Python handles delays between evaluate calls
                                return 'LINKEDIN_SUCCESS_MODAL_CLOSED';
                            }}
                            // Fallback: any button in success modal
                            const anyBtn = successModal.querySelector('button.artdeco-button--primary, button');
                            if (anyBtn) {{
                                anyBtn.click();
                                // NOTE: await removed - Python handles delays between evaluate calls
                                return 'LINKEDIN_SUCCESS_MODAL_CLOSED';
                            }}
                        }}
                    }}
                    
                    // Check for artdeco success feedback (modal or toast)
                    let successDetected = false;
                    const successToast = document.querySelector('div.artdeco-inline-feedback--success, .artdeco-toast-item--success');
                    const successVisible = successToast && successToast.offsetParent !== null;
                    const successInText = document.body.innerText.includes('Application submitted') && 
                                          document.body.innerText.length < 50000; // Limit scope

                    if (successVisible || successInText) {{
                        const closeBtn = document.querySelector('button[aria-label="Dismiss"], button.artdeco-toast-item__dismiss');
                        if (closeBtn) closeBtn.click();
                        successDetected = true;
                        // NOTE: await removed - Python handles delays between evaluate calls
                    }}

                    // NAVIGATION & SKIP LOGIC: Move to next job if current is applied or not Easy Apply
                    // Try multiple sidebar selectors - LinkedIn changes these frequently
                    // Based on DOM inspection: .scaffold-layout__list works
                    const sidebarSelectors = [
                        '.scaffold-layout__list',
                        'div[class*="results-list"]',
                        '.jobs-search-results-list',
                        '.scaffold-layout__list-container',
                        'ul.scaffold-layout__list-container',
                        '.jobs-search-results-list__list',
                        '[data-test-results-list]',
                        '.jobs-search-two-pane__results-list',
                        '[class*="jobs-search"][class*="list"]'
                    ];
                    
                    let sidebar = null;
                    for (const selector of sidebarSelectors) {{
                        sidebar = document.querySelector(selector);
                        if (sidebar) {{
                            console.log('LINKEDIN: Found sidebar with selector: ' + selector);
                            break;
                        }}
                    }}
                    
                    // If we have a sidebar, try to navigate to next job if needed
                    if (sidebar) {{
                        // NOTE: await removed - Python handles delays between evaluate calls
                        
                        // Find all job cards - use the selector that works
                        const jobCards = Array.from(sidebar.querySelectorAll('li.scaffold-layout__list-item'));
                        console.log('LINKEDIN: Found ' + jobCards.length + ' job cards');
                        
                        // Helper function to extract job ID from card (defined BEFORE use)
                        const getJobIdFromCard = (card) => {{
                            // Try data attributes first
                            let jobId = card.getAttribute('data-job-id') || card.getAttribute('data-occludable-job-id');
                            if (jobId) return jobId;
                            
                            // Try to extract from child element
                            const childWithId = card.querySelector('[data-job-id], [data-occludable-job-id]');
                            if (childWithId) {{
                                jobId = childWithId.getAttribute('data-job-id') || childWithId.getAttribute('data-occludable-job-id');
                                if (jobId) return jobId;
                            }}
                            
                            // Extract from link href
                            const link = card.querySelector('a[href*="currentJobId="]');
                            if (link) {{
                                const href = link.getAttribute('href');
                                const match = href.match(/currentJobId=(\d+)/);
                                if (match) return match[1];
                            }}
                            
                            return null;
                        }};
                        
                        if (jobCards.length > 0) {{
                            // Get current job ID
                            const urlParams = new URLSearchParams(window.location.search);
                            const currentJobId = urlParams.get('currentJobId');
                            console.log('LINKEDIN: Current job ID: ' + currentJobId);
                            
                            // NO CURRENT JOB: Click first unapplied job to open it
                            if (!currentJobId) {{
                                console.log('LINKEDIN: No current job, looking for first unapplied job');
                                for (let i = 0; i < jobCards.length; i++) {{
                                    const card = jobCards[i];
                                    const cardText = card.innerText || '';
                                    const cardId = getJobIdFromCard(card);
                                    
                                    // Skip applied jobs
                                    if (cardText.includes('Applied') || cardText.includes('See application')) {{
                                        console.log('LINKEDIN: Skipping job ' + i + ' (already applied)');
                                        continue;
                                    }}
                                    
                                    console.log('LINKEDIN: Clicking first unapplied job at index ' + i + ', ID=' + cardId);
                                    card.scrollIntoView({{ block: 'center' }});
                                    // NOTE: await removed - Python handles delays between evaluate calls
                                    
                                    const link = card.querySelector('a');
                                    if (link) {{
                                        link.click();
                                        // NOTE: await removed - Python handles delays between evaluate calls
                                        return 'LINKEDIN_FIRST_JOB: Opened job ' + cardId;
                                    }}
                                    
                                    card.click();
                                    // NOTE: await removed - Python handles delays between evaluate calls
                                    return 'LINKEDIN_FIRST_JOB: Clicked job ' + cardId;
                                }}
                                console.log('LINKEDIN: All jobs appear to be applied');
                            }}
                            
                            // Find currently active card
                            let activeIndex = -1;
                            for (let i = 0; i < jobCards.length; i++) {{
                                const card = jobCards[i];
                                const cardId = getJobIdFromCard(card);
                                if (cardId === currentJobId ||
                                    card.classList.contains('jobs-search-results-list__list-item--active')) {{
                                    activeIndex = i;
                                    break;
                                }}
                            }}
                            if (activeIndex === -1) activeIndex = 0;
                            
                            // Check if current job is applied
                            const currentCard = jobCards[activeIndex];
                            const currentText = currentCard ? currentCard.innerText : '';
                            const isApplied = currentText.includes('Applied') || 
                                             currentText.includes('See application') ||
                                             /Applied\s+\d+\s+(seconds?|minutes?)\s+ago/i.test(currentText);
                            
                            console.log('LINKEDIN: Active index=' + activeIndex + ', isApplied=' + isApplied);
                            
                            // Check for Easy Apply button
                            const hasEasyApply = !!document.querySelector('button.jobs-apply-button');
                            console.log('LINKEDIN: Has Easy Apply=' + hasEasyApply);
                            
                            // NAVIGATE if: applied, no easy apply, or success was detected
                            if (isApplied || !hasEasyApply || successDetected) {{
                                console.log('LINKEDIN: Looking for next unapplied job, starting from index ' + (activeIndex + 1));
                                // Find next unapplied job
                                for (let i = activeIndex + 1; i < jobCards.length; i++) {{
                                    const card = jobCards[i];
                                    const cardText = card.innerText || '';
                                    const cardId = getJobIdFromCard(card);
                                    
                                    console.log('LINKEDIN: Checking job ' + i + ', ID=' + cardId);
                                    
                                    // Skip applied jobs
                                    if (cardText.includes('Applied') || cardText.includes('See application')) {{
                                        console.log('LINKEDIN: Skipping job ' + i + ' (already applied)');
                                        continue;
                                    }}
                                    
                                    console.log('LINKEDIN: Found unapplied job at index ' + i + ', ID=' + cardId);
                                    
                                    // Found unapplied job - navigate to it
                                    card.scrollIntoView({{ block: 'center' }});
                                    // NOTE: await removed - Python handles delays between evaluate calls
                                    
                                    // Strategy 1: Try to find clickable link with href
                                    const link = card.querySelector('a');
                                    console.log('LINKEDIN: Link found=' + (link ? 'YES' : 'NO') + ', href=' + (link ? link.href : 'N/A'));
                                    
                                    if (link) {{
                                        // Click the link to navigate
                                        link.click();
                                        console.log('LINKEDIN: Clicked link for job ' + cardId);
                                        
                                        // NOTE: await removed - Python handles delays between evaluate calls
                                        
                                        // Check if we navigated
                                        const newUrl = window.location.href;
                                        if (newUrl.includes(cardId) || newUrl.includes('currentJobId')) {{
                                            return 'LINKEDIN_NAVIGATED: To job ' + cardId;
                                        }}
                                        return 'LINKEDIN_NAVIGATED: Attempted navigation to job ' + cardId;
                                    }}
                                    
                                    // Strategy 2: Click the card itself
                                    console.log('LINKEDIN: Trying card.click()');
                                    card.click();
                                    // NOTE: await removed - Python handles delays between evaluate calls
                                    return 'LINKEDIN_NAVIGATED: Clicked card ' + cardId;
                                }}
                                
                                console.log('LINKEDIN: No more unapplied jobs found, need to scroll');
                                
                                // No more jobs - scroll for more
                                sidebar.scrollTop += 800;
                                return 'LINKEDIN_SCROLLED: Looking for more jobs';
                            }}
                        }} else {{
                            console.log('LINKEDIN: Sidebar not found with any selector, continuing with apply flow');
                        }}
                    
                    // If success was detected but we didn't navigate to a new job above,
                    // it means we're still on the success page. Return success to trigger navigation.
                    // But only if Easy Apply button is NOT present (meaning we can't apply to current job)
                    if (successDetected) {{
                        const hasEasyApply = !!document.querySelector('button.jobs-apply-button');
                        if (!hasEasyApply) {{
                            console.log('LINKEDIN: Success detected, no Easy Apply button - need to navigate');
                            return 'LINKEDIN_SUCCESS_NEED_NAV';
                        }}
                    }}
                    
                    const modal = document.querySelector('div.jobs-easy-apply-modal, div[data-test-modal="jobs-easy-apply-modal"]');
                    if (!modal) {{
                        const easyApplyBtn = document.querySelector('button.jobs-apply-button');
                        if (easyApplyBtn && easyApplyBtn.innerText.toLowerCase().includes('easy apply')) {{
                            easyApplyBtn.click();
                            return 'APPLY_CLICKED_LINKEDIN';
                        }}
                        return 'LINKEDIN_NO_MODAL';
                    }}
                    // Handle Interactions
                    const nextBtn = document.querySelector('button[aria-label="Continue to next step"], button[aria-label="Review your application"], button[aria-label="Submit application"]');
                    if (nextBtn) {{
                        // Collect all question data for logging
                        const questionLogData = [];
                        
                        // Fill ALL form fields before clicking next
                        const formGroups = modal.querySelectorAll('.fb-dash-form-element, [data-test-form-element], .jobs-easy-apply-form-section__grouping');
                        
                        for (const group of formGroups) {{
                            // Get the label/question for this field
                            const labelEl = group.querySelector('label, .fb-dash-form-element__label, span[class*="label"]');
                            const qText = labelEl ? labelEl.innerText : '';
                            const answer = fuzzyMatch(qText);
                            
                            let inputType = '';
                            let options = [];
                            let selectedOption = '';
                            let finalAnswer = answer || '';
                            
                            // Handle text inputs
                            const textInput = group.querySelector('input[type="text"], input[type="number"], input[type="tel"], input[type="email"], textarea');
                            if (textInput && !textInput.disabled && textInput.offsetParent !== null) {{
                                inputType = textInput.type || 'text';
                                if (!textInput.value || textInput.value.trim() === '') {{
                                    // LinkedIn often requires whole numbers - detect and normalize
                                    const qLower = qText.toLowerCase();
                                    const isNumericField = qLower.includes('number') ||
                                                           qLower.includes('how many') ||
                                                           qLower.includes('experience') ||
                                                           qLower.includes('years') ||
                                                           qLower.includes('notice') ||
                                                           qLower.includes('period') ||
                                                           qLower.includes('days') ||
                                                           qLower.includes('ctc') ||
                                                           qLower.includes('salary') ||
                                                           qLower.includes('pay') ||
                                                           textInput.type === 'number';
                                    
                                     // Only use default '4' for known experience fields, not for all numeric fields
                                     const isExperienceField = qLower.includes('experience') || qLower.includes('years');
                                     const isSalaryField = qLower.includes('salary') || qLower.includes('ctc') || qLower.includes('pay') || qLower.includes('gross') || qLower.includes('expectation');
                                     const isNoticeField = qLower.includes('notice') || qLower.includes('period') || qLower.includes('days');
                                     
                                     // Determine default value based on field type
                                     let defaultValue = '';
                                     if (isExperienceField) defaultValue = '4';
                                     else if (isSalaryField) {{
                                         // Smart salary detection: check if "expected" or "current" is mentioned
                                         if (qLower.includes('expected') || qLower.includes('expectation')) {{
                                             defaultValue = '20 LPA';  // Expected salary
                                         }} else if (qLower.includes('current')) {{
                                             defaultValue = '13.5 LPA';  // Current salary
                                         }} else if (qLower.includes('gross')) {{
                                             // For "gross salary" without context, check if "expected" is also mentioned
                                             defaultValue = qLower.includes('expected') ? '20 LPA' : '13.5 LPA';
                                         }} else {{
                                             defaultValue = '20 LPA';  // Default to expected salary for generic salary fields
                                         }}
                                     }}
                                     else if (isNoticeField) defaultValue = '30 days';
                                    else if (textInput.tagName.toLowerCase() === 'textarea') defaultValue = 'I am excited about this opportunity and believe my experience would be valuable to your team.';
                                    
                                    let value = answer || defaultValue;
                                    
                                     if (isNumericField && value) {{
                                         // Smart numeric field handling with proper defaults
                                         const numericValue = value.replace(/[^0-9.]/g, '');
                                          if (numericValue) {{
                                              if (qLower.includes('experience') || qLower.includes('years')) {{
                                                  // Experience: Use '4' for LinkedIn, '3.8' for other platforms
                                                  value = isLinkedIn ? '4' : '3.8';
                                              }} else if (qLower.includes('ctc') || qLower.includes('salary') || qLower.includes('pay') || qLower.includes('gross')) {{
                                                 // Salary: Extract the correct numeric value based on expected/current
                                                 if (qLower.includes('expected')) {{
                                                     value = '20';  // Expected salary
                                                 }} else if (qLower.includes('current')) {{
                                                     value = '13.5';  // Current salary  
                                                 }} else if (value.includes('20')) {{
                                                     value = '20';  // If value contains 20, use 20
                                                 }} else if (value.includes('13.5')) {{
                                                     value = '13.5';  // If value contains 13.5, use 13.5
                                                 }} else {{
                                                     value = '20';  // Default to expected salary
                                                 }}
                                             }} else if (qLower.includes('notice') || qLower.includes('period') || qLower.includes('days')) {{
                                                 // Notice period: Extract just the number
                                                 value = '30';
                                             }} else {{
                                                 // Otherwise just use the numeric part
                                                 value = numericValue.includes('.') ? Math.round(parseFloat(numericValue)).toString() : numericValue;
                                             }}
                                         }}
                                     }}
                                    
                                    finalAnswer = value;

                                    // Check if this is a city/location typeahead field
                                    const isCityTypeahead = textInput.getAttribute('role') === 'combobox' ||
                                                           textInput.getAttribute('aria-autocomplete') === 'list' ||
                                                           qLower.includes('city') ||
                                                           qLower.includes('location');
                                    
                                    if (isCityTypeahead && value) {{
                                        // For city typeaheads, type the value and return special code
                                        textInput.focus();
                                        textInput.value = value;
                                        textInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        textInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        // Don't blur - keep focus for dropdown to appear
                                        return 'LINKEDIN_CITY_TYPED:' + value;
                                    }}

                                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                    if (setter) setter.call(textInput, value);
                                    textInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    textInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    textInput.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                    
                                    // Check for validation errors and retry with numeric-only if needed
                                    setTimeout(() => {{
                                        // Look for validation errors near this input
                                        const parent = textInput.closest('div[class*="form"], div[class*="field"], div[class*="group"], form-group');
                                        const errorElement = parent ? parent.querySelector('[class*="error"], [class*="invalid"], [role="alert"], .error-message') : null;
                                        const errorText = errorElement ? errorElement.innerText.toLowerCase() : '';
                                        
                                        // If there's a validation error and the value contains non-numeric characters
                                        if ((errorText.includes('numeric') || errorText.includes('number') || errorText.includes('invalid') || textInput.classList.contains('error')) && 
                                            (value.includes('lpa') || value.includes('years') || value.includes('days'))) {{
                                            
                                            // Retry with numeric-only value
                                            const numericValue = value.replace(/[^0-9.]/g, '');
                                            if (numericValue) {{
                                                if (setter) setter.call(textInput, numericValue);
                                                textInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                                textInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                                textInput.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                                finalAnswer = numericValue;
                                            }}
                                        }}
                                    }}, 500); // Wait 500ms for validation to trigger
                                }} else {{
                                    finalAnswer = textInput.value;
                                }}
                            }}
                            
                            // Handle select dropdowns with smart matching
                            const select = group.querySelector('select');
                            if (select && select.offsetParent !== null) {{
                                inputType = 'select';
                                const selectOptions = Array.from(select.options);
                                options = selectOptions.map(o => o.text).filter(t => t.trim());
                                
                                if (select.selectedIndex <= 0) {{
                                    let matched = false;
                                    
                                    // Smart location handling for dropdowns
                                    const qTextLowerSelect = (qText || '').toLowerCase();
                                    
                                    // Use smart matcher if we have an answer
                                    if (answer) {{
                                        // Check if this is a salary question
                                        const isSalaryQuestionSelect = qTextLowerSelect.includes('salary') || 
                                                                       qTextLowerSelect.includes('ctc') || 
                                                                       qTextLowerSelect.includes('current salary') ||
                                                                       qTextLowerSelect.includes('expected salary');
                                        const isExpectedSalarySelect = qTextLowerSelect.includes('expected');
                                        
                                        let bestMatch = null;
                                        
                                        if (isSalaryQuestionSelect) {{
                                            // Use smart salary range matching
                                            bestMatch = findSalaryRangeMatch(answer, selectOptions, !isExpectedSalarySelect);
                                        }}
                                        
                                        // Fallback to regular matching if no salary range match found
                                        if (!bestMatch) {{
                                            bestMatch = findBestMatch(answer, selectOptions);
                                        }}
                                        
                                        if (bestMatch) {{
                                            select.value = bestMatch.value;
                                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            selectedOption = bestMatch.text;
                                            finalAnswer = bestMatch.text;
                                            matched = true;
                                        }}
                                    }}
                                    const isCurrentLocationQuestionSelect = qTextLowerSelect.includes('present location') || qTextLowerSelect.includes('current location') || 
                                                                      qTextLowerSelect.includes('live in') || qTextLowerSelect.includes('living in') || 
                                                                      qTextLowerSelect.includes('based in') || qTextLowerSelect.includes('located in') ||
                                                                      qTextLowerSelect.includes('residing in') || qTextLowerSelect.includes('current city');
                                    const isLocationPreferenceQuestionSelect = qTextLowerSelect.includes('preferred location') || qTextLowerSelect.includes('location preference') ||
                                                               qTextLowerSelect.includes('work location') || qTextLowerSelect.includes('relocate') ||
                                                               qTextLowerSelect.includes('willing to relocate');
                                    const hasBangaloreOptionsSelect = selectOptions.some(o => o.text.toLowerCase().includes('bangalore'));
                                    
                                    if (!matched && hasBangaloreOptionsSelect) {{
                                        if (isCurrentLocationQuestionSelect) {{
                                            // For current location questions: Select "Outside Bangalore" since user is in Noida
                                            const outsideBangaloreOption = selectOptions.find(o => 
                                                o.text.toLowerCase().includes('outside') && o.text.toLowerCase().includes('bangalore')
                                            );
                                            if (outsideBangaloreOption) {{
                                                select.value = outsideBangaloreOption.value;
                                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                                selectedOption = outsideBangaloreOption.text;
                                                finalAnswer = 'Outside Bangalore';
                                                matched = true;
                                            }}
                                        }} else if (isLocationPreferenceQuestionSelect) {{
                                            // For location preference questions: Select preferred metro cities
                                            const preferredCityOption = selectOptions.find(o => {{
                                                const text = o.text.toLowerCase();
                                                return text.includes('bangalore') || text.includes('hyderabad') || text.includes('mumbai') || text.includes('pune') || text.includes('delhi');
                                            }});
                                            if (preferredCityOption) {{
                                                select.value = preferredCityOption.value;
                                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                                selectedOption = preferredCityOption.text;
                                                finalAnswer = preferredCityOption.text;
                                                matched = true;
                                            }}
                                        }}
                                    }}
                                    
                                    // Fallback: try to match Yes/No based on answer type
                                    // Or if question requires "No" answer (employment/relationship questions)
                                    const noRequiredPatternsSelect = [
                                        'employed by any of the',
                                        'currently employed as a',
                                        'third party / temporary',
                                        'have you ever worked for',
                                        'close relative working at',
                                        'relative working',
                                        'family member working',
                                        'conflict of interest',
                                        'currently an employee of',
                                        'previously employed by'
                                    ];
                                    const shouldAnswerNoSelect = noRequiredPatternsSelect.some(pattern => qTextLowerSelect.includes(pattern));
                                    
                                    if (!matched) {{
                                        if (shouldAnswerNoSelect) {{
                                            // Force "No" for employment/relationship questions
                                            const noOption = selectOptions.find(o =>
                                                ['no', 'false', 'decline'].includes(o.text.toLowerCase())
                                            );
                                            if (noOption) {{
                                                select.value = noOption.value;
                                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                                selectedOption = noOption.text;
                                                finalAnswer = noOption.text;
                                                matched = true;
                                            }}
                                        }} else if (isYes(answer)) {{
                                            const yesOption = selectOptions.find(o =>
                                                ['yes', 'true', 'agree', 'accept'].includes(o.text.toLowerCase())
                                            );
                                            if (yesOption) {{
                                                select.value = yesOption.value;
                                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                                selectedOption = yesOption.text;
                                                finalAnswer = yesOption.text;
                                                matched = true;
                                            }}
                                        }} else if (isNo(answer)) {{
                                            const noOption = selectOptions.find(o =>
                                                ['no', 'false', 'decline'].includes(o.text.toLowerCase())
                                            );
                                            if (noOption) {{
                                                select.value = noOption.value;
                                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                                selectedOption = noOption.text;
                                                finalAnswer = noOption.text;
                                                matched = true;
                                            }}
                                        }}
                                    }}
                                    
                                    if (!matched && selectOptions.length > 1) {{
                                        // Default: select first non-empty option
                                        select.selectedIndex = 1;
                                        select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        selectedOption = selectOptions[1].text;
                                        finalAnswer = selectOptions[1].text;
                                    }}
                                }} else {{
                                    selectedOption = selectOptions[select.selectedIndex]?.text || '';
                                    finalAnswer = selectedOption;
                                }}
                            }}
                            
                            // Handle radio buttons with smart matching
                            const radios = group.querySelectorAll('input[type="radio"]');
                            if (radios.length > 0) {{
                                inputType = 'radio';
                                options = Array.from(radios).map(r => {{
                                    const label = r.parentElement?.innerText || r.nextElementSibling?.innerText || r.value || '';
                                    return label.trim();
                                }}).filter(t => t);
                                
                                let clicked = false;
                                
                                // Check if already selected
                                for (const radio of radios) {{
                                    if (radio.checked) {{ 
                                        clicked = true; 
                                        const label = radio.parentElement?.innerText || radio.nextElementSibling?.innerText || radio.value || '';
                                        selectedOption = label.trim();
                                        finalAnswer = selectedOption;
                                        break; 
                                    }}
                                }}
                                
                                // Smart location handling - Current vs Preferred vs Bangalore-specific questions
                                const qTextLower = (qText || '').toLowerCase();
                                const isCurrentLocationQuestion = qTextLower.includes('present location') || qTextLower.includes('current location') || 
                                                                qTextLower.includes('live in') || qTextLower.includes('living in') || 
                                                                qTextLower.includes('based in') || qTextLower.includes('located in') ||
                                                                qTextLower.includes('residing in') || qTextLower.includes('current city');
                                const isLocationPreferenceQuestion = qTextLower.includes('preferred location') || qTextLower.includes('location preference') ||
                                                             qTextLower.includes('work location') || qTextLower.includes('relocate') ||
                                                             qTextLower.includes('willing to relocate');
                                const hasBangaloreOptions = Array.from(radios).some(r => {{
                                    const label = (r.parentElement?.innerText || r.nextElementSibling?.innerText || r.value || '').toLowerCase();
                                    return label.includes('bangalore');
                                }});
                                
                                if (!clicked && hasBangaloreOptions) {{
                                    if (isCurrentLocationQuestion) {{
                                        // For current location questions: Select "Outside Bangalore" since user is in Noida
                                        for (const radio of radios) {{
                                            const label = (radio.parentElement?.innerText || radio.nextElementSibling?.innerText || radio.value || '').toLowerCase();
                                            if (label.includes('outside') && label.includes('bangalore')) {{
                                                radio.click();
                                                clicked = true;
                                                selectedOption = 'Outside Bangalore';
                                                finalAnswer = 'Outside Bangalore';
                                                break;
                                            }}
                                        }}
                                    }} else if (isLocationPreferenceQuestion) {{
                                        // For location preference questions: Select Bangalore or preferred location
                                        for (const radio of radios) {{
                                            const label = (radio.parentElement?.innerText || radio.nextElementSibling?.innerText || radio.value || '').toLowerCase();
                                            if (label.includes('bangalore') || label.includes('hyderabad') || label.includes('mumbai') || label.includes('pune')) {{
                                                radio.click();
                                                clicked = true;
                                                selectedOption = label.trim();
                                                finalAnswer = label.trim();
                                                break;
                                            }}
                                        }}
                                    }}
                                }}
                                
                                // Use smart matcher if we have an answer and nothing selected
                                if (!clicked && answer) {{
                                    const radioOptions = Array.from(radios).map(r => ({{
                                        element: r,
                                        text: r.parentElement?.innerText || r.nextElementSibling?.innerText || r.value || '',
                                        value: r.value
                                    }}));
                                    
                                    // Check if this is a salary question
                                    const isSalaryQuestion = qTextLower.includes('salary') || 
                                                             qTextLower.includes('ctc') || 
                                                             qTextLower.includes('current salary') ||
                                                             qTextLower.includes('expected salary');
                                    const isExpectedSalary = qTextLower.includes('expected');
                                    
                                    let bestMatch = null;
                                    
                                    if (isSalaryQuestion) {{
                                        // Use smart salary range matching
                                        bestMatch = findSalaryRangeMatch(answer, radioOptions, !isExpectedSalary);
                                    }}
                                    
                                    // Fallback to regular matching if no salary range match found
                                    if (!bestMatch) {{
                                        bestMatch = findBestMatch(answer, radioOptions);
                                    }}
                                    
                                    if (bestMatch) {{
                                        bestMatch.element.click();
                                        clicked = true;
                                        selectedOption = bestMatch.text.trim();
                                        finalAnswer = selectedOption;
                                    }}
                                }}
                                
                                // Fallback to Yes/No based on answer type
                                if (!clicked) {{
                                    if (isYes(answer)) {{
                                        for (const radio of radios) {{
                                            const label = radio.parentElement?.innerText || radio.nextElementSibling?.innerText || '';
                                            if (['yes', 'true', 'agree'].includes(label.toLowerCase())) {{
                                                radio.click();
                                                clicked = true;
                                                selectedOption = label.trim();
                                                finalAnswer = selectedOption;
                                                break;
                                            }}
                                        }}
                                    }} else if (isNo(answer)) {{
                                        for (const radio of radios) {{
                                            const label = radio.parentElement?.innerText || radio.nextElementSibling?.innerText || '';
                                            if (['no', 'false', 'decline'].includes(label.toLowerCase())) {{
                                                radio.click();
                                                clicked = true;
                                                selectedOption = label.trim();
                                                finalAnswer = selectedOption;
                                                break;
                                            }}
                                        }}
                                    }}
                                }}
                                
                                // Check for questions that should ALWAYS be answered "No"
                                // These are employment history, relative, and conflict of interest questions
                                const noRequiredPatterns = [
                                    'employed by any of the',
                                    'currently employed as a',
                                    'third party / temporary',
                                    'have you ever worked for',
                                    'close relative working at',
                                    'relative working',
                                    'family member working',
                                    'family members working',
                                    'family members in company',
                                    'relatives in company',
                                    'relatives working in',
                                    'family in company',
                                    'conflict of interest',
                                    'currently an employee of',
                                    'previously employed by'
                                ];
                                const shouldAnswerNo = noRequiredPatterns.some(pattern => qTextLower.includes(pattern));
                                
                                // If question requires "No" and nothing selected yet
                                if (!clicked && shouldAnswerNo) {{
                                    for (const radio of radios) {{
                                        const label = radio.parentElement?.innerText || radio.nextElementSibling?.innerText || '';
                                        if (['no', 'false', 'decline'].includes(label.toLowerCase())) {{
                                            radio.click();
                                            clicked = true;
                                            selectedOption = label.trim();
                                            finalAnswer = selectedOption;
                                            break;
                                        }}
                                    }}
                                }}
                                
                                // Final fallback: click first option
                                if (!clicked) {{
                                    radios[0].click();
                                    const label = radios[0].parentElement?.innerText || radios[0].nextElementSibling?.innerText || radios[0].value || '';
                                    selectedOption = label.trim();
                                    finalAnswer = selectedOption;
                                }}
                            }}
                            
                            // Handle checkboxes (Privacy Policy, Terms & Conditions, etc.)
                            const checkboxes = group.querySelectorAll('input[type="checkbox"]');
                            if (checkboxes.length > 0) {{
                                inputType = 'checkbox';
                                options = Array.from(checkboxes).map(cb => {{
                                    const label = cb.closest('label') || document.querySelector('label[for="' + cb.id + '"]');
                                    return label ? label.innerText.trim() : (cb.value || '');
                                }}).filter(t => t);
                                
                                for (const checkbox of checkboxes) {{
                                    // Skip already checked boxes
                                    if (checkbox.checked) continue;
                                    
                                    const labelEl = checkbox.closest('label') || document.querySelector('label[for="' + checkbox.id + '"]');
                                    const labelText = labelEl ? labelEl.innerText.toLowerCase() : '';
                                    
                                    // Check if this is a privacy policy / terms checkbox
                                    const isPrivacyOrTerms = 
                                        labelText.includes('privacy') ||
                                        labelText.includes('terms') ||
                                        labelText.includes('conditions') ||
                                        labelText.includes('agree') ||
                                        labelText.includes('smartrecruiters') ||
                                        labelText.includes('syngenta') ||
                                        checkbox.id?.toLowerCase().includes('privacy') ||
                                        checkbox.id?.toLowerCase().includes('terms') ||
                                        checkbox.name?.toLowerCase().includes('privacy') ||
                                        checkbox.name?.toLowerCase().includes('terms') ||
                                        checkbox.className?.toLowerCase().includes('privacy') ||
                                        checkbox.className?.toLowerCase().includes('terms');
                                    
                                    // Click if it's privacy/terms related or if answer suggests agreement
                                    if (isPrivacyOrTerms || isYes(answer)) {{
                                        checkbox.scrollIntoView({{ block: 'center' }});
                                        checkbox.click();
                                        selectedOption = 'checked: ' + labelText;
                                        finalAnswer = 'Agreed to ' + labelText;
                                        
                                        // Return special code to indicate checkbox was clicked
                                        return 'LINKEDIN_CHECKBOX_CHECKED|' + JSON.stringify({{
                                            question: qText,
                                            label: labelText,
                                            checked: true
                                        }});
                                    }}
                                }}
                            }}
                            
                            // Log question data if we have a question
                            if (qText) {{
                                questionLogData.push({{
                                    question: qText,
                                    answer: finalAnswer,
                                    inputType: inputType,
                                    options: options,
                                    selectedOption: selectedOption
                                }});
                            }}
                        }}
                        
                        // Also check for standalone inputs not in form groups
                        const standaloneInputs = modal.querySelectorAll('input[type="text"]:not([value]), input[type="number"]:not([value])');
                        for (const input of standaloneInputs) {{
                            if (!input.value && input.offsetParent !== null) {{
                                const label = input.closest('div')?.querySelector('label')?.innerText || '';
                                const answer = fuzzyMatch(label) || '4';
                                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                if (setter) setter.call(input, answer);
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                
                                if (label) {{
                                    questionLogData.push({{
                                        question: label,
                                        answer: answer,
                                        inputType: input.type || 'text',
                                        options: [],
                                        selectedOption: answer
                                    }});
                                }}
                            }}
                        }}
                        
                        nextBtn.click();
                        
                        // Return question data for logging
                        if (questionLogData.length > 0) {{
                            return 'CLICKED_NEXT_OR_SUBMIT|' + JSON.stringify(questionLogData);
                        }}
                        return 'CLICKED_NEXT_OR_SUBMIT';
                    }}
                }}
            }}
            
            // ============================================================
            // NAUKRI LOGIC (Enhanced with proper selectors and tab navigation)
            // ============================================================
            if (isNaukri) {{
                    const TARGET_JOBS = 5;
                    
                    // 0. Dismiss any feedback modals (non-blocking)
                    const feedbackSection = Array.from(document.querySelectorAll('div, section')).find(
                        el => el.innerText && el.innerText.includes('Are these jobs relevant') && 
                              el.innerText.length < 1000 && el.offsetParent !== null
                    );
                        if (feedbackSection) {{
                        const yesBtn = feedbackSection.querySelector('button');
                        if (yesBtn && yesBtn.innerText.toLowerCase().includes('yes')) {{
                            yesBtn.click();
                            // NOTE: await removed - Python handles delays between evaluate calls
                        }} else {{
                            const anyBtn = feedbackSection.querySelector('button');
                            if (anyBtn) {{
                                anyBtn.click();
                                // NOTE: await removed - Python handles delays between evaluate calls
                            }}
                        }}
                        // No early return! Proceed with job application
                    }}
                    
                    // Check for error popup - "There was some error processing your request"
                    // Uses specific Naukri selector: div.ss-snackbar-body
                    const snackbarBody = document.querySelector('div.ss-snackbar-body');
                    if (snackbarBody) {{
                        const snackText = snackbarBody.innerText.toLowerCase();
                        if (snackText.includes('error processing') || snackText.includes('some error')) {{
                            const closeBtn = document.querySelector('button.ss-close');
                            if (closeBtn) closeBtn.click();
                            return 'NAUKRI_RATE_LIMITED: Error popup detected during fallback start';
                        }}
                    }}
                    
                    // 0. Check for success page (URL pattern or message)
                    const isSuccessPage = window.location.href.includes('/myapply/saveApply');
                    const successMsg = document.querySelector('span.apply-message');
                    if (isSuccessPage || (successMsg && successMsg.innerText.includes('successful'))) {{
                        const bodyText = document.body.innerText || '';
                        const match = bodyText.match(/(\d+)\s*out\s*of\s*(\d+)/);
                        if (match) {{
                            const appliedThisRound = parseInt(match[1]);
                            // Get cumulative count from sessionStorage
                            const prevTotal = parseInt(sessionStorage.getItem('naukri_total_applied') || '0');
                            const newTotal = prevTotal + appliedThisRound;
                            sessionStorage.setItem('naukri_total_applied', newTotal.toString());
                            
                            const remaining = TARGET_JOBS - newTotal;
                            
                            if (remaining <= 0) {{
                                sessionStorage.removeItem('naukri_total_applied');
                                sessionStorage.removeItem('naukri_remaining');
                                // Task complete - do NOT navigate, signal done
                                return 'NAUKRI_TASK_DONE: Applied to ' + newTotal + ' jobs total. Task complete.';
                            }}
                            
                            // Need more jobs - store remaining and navigate back to recommended jobs
                            sessionStorage.setItem('naukri_remaining', remaining.toString());
                            window.location.href = 'https://www.naukri.com/mnjuser/recommendedjobs';
                            return 'NAUKRI_SUCCESS_PARTIAL: Applied ' + newTotal + ' total, need ' + remaining + ' more - navigating back';
                        }}
                    }}
                    
                    // 1. Handle chatbot modal if open
                    const chatBotContainer = document.querySelector('[class*="ChatbotContainer"], [class*="chatBotContainer"], ._chatBotContainer');
                    const chatLayer = document.querySelector('.chatbot_DrawerContentWrapper, .chatbot_Drawer');
                    const chatIsVisible = (chatBotContainer && chatBotContainer.offsetParent !== null) || 
                                         (chatLayer && chatLayer.offsetParent !== null) ||
                                         document.querySelector('.chatbot_Overlay.show') !== null;
                    
                    if (chatIsVisible) {{
                        // Find the question
                        const questionEl = document.querySelector('.chatbot_MessageContainer li.botItem:last-of-type .botMsg') ||
                                          document.querySelector('.botMsg.msg') ||
                                          document.querySelector('li.botItem .botMsg');
                        
                        // Find the input - DOM inspection found: div.textArea[contenteditable="true"]
                        // Parent is .textAreaWrapper, placeholder is "Type message here..."
                        const inputDiv = document.querySelector('div.textArea[contenteditable="true"]') ||
                                        document.querySelector('.textAreaWrapper div[contenteditable="true"]') ||
                                        document.querySelector('[id*="userInput"][contenteditable="true"]') ||
                                        document.querySelector('div[contenteditable="true"][data-placeholder*="Type message"]');
                        
                        const qText = questionEl?.innerText || 'Unknown question';
                        const answer = fuzzyMatch(qText) || "3.8 Years"; 
                        
                        // Try contenteditable div (Naukri's actual implementation)
                        if (inputDiv) {{
                            const currentText = inputDiv.textContent || inputDiv.innerText || '';
                            if (!currentText.trim()) {{
                                inputDiv.focus();
                                // Clear and set
                                inputDiv.innerHTML = '';
                                inputDiv.textContent = answer;
                                inputDiv.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                inputDiv.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                inputDiv.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true }}));
                                
                                // CRITICAL: Save button is div.sendMsg, NOT a button element!
                                // Structure: .sendMsgbtn_container > div.send > div.sendMsg
                                const sendBtn = document.querySelector('div.sendMsg') ||
                                               document.querySelector('.sendMsgbtn_container .sendMsg') ||
                                               document.querySelector('[class*="sendMsg"]');
                                
                                console.log('NAUKRI DEBUG: sendBtn found=', !!sendBtn, sendBtn?.outerHTML?.slice(0, 100));
                                
                                if (sendBtn) {{ 
                                    sendBtn.click(); 
                                    return 'NAUKRI_CHAT_ANSWERED_AND_SAVED: ' + qText.slice(0, 40); 
                                }}
                                
                                // Fallback: try pressing Enter to submit
                                inputDiv.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', keyCode: 13, bubbles: true }}));
                                inputDiv.dispatchEvent(new KeyboardEvent('keypress', {{ key: 'Enter', keyCode: 13, bubbles: true }}));
                                return 'NAUKRI_CHAT_ANSWERED: ' + qText.slice(0, 40);
                            }}
                        }}
                        
                        // Try dropdown
                        const select = document.querySelector('select');
                        if (select && select.offsetParent !== null && select.selectedIndex <= 0 && select.options.length > 1) {{
                            select.selectedIndex = 1;
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            const saveBtn = document.querySelector('div.sendMsg') || document.querySelector('.sendMsgbtn_container .sendMsg');
                            if (saveBtn) {{ saveBtn.click(); return 'NAUKRI_CHAT_DROPDOWN_SAVED'; }}
                        }}
                        
                        // Try radio buttons (prefer Yes) - for Yes/No/Skip questions
                        const radios = document.querySelectorAll('input[type="radio"]');
                        if (radios.length > 0) {{
                            let clicked = false;
                            for (const radio of radios) {{
                                const label = radio.closest('label')?.innerText || radio.parentElement?.innerText || '';
                                if (label.toLowerCase().includes('yes') || label.toLowerCase().includes('serving')) {{
                                    if (!radio.checked) {{ radio.click(); clicked = true; }}
                                    break;
                                }}
                            }}
                            // Fallback: click first unselected radio
                            if (!clicked && radios.length > 0 && !radios[0].checked) {{ 
                                radios[0].click(); 
                                clicked = true; 
                            }}
                            if (clicked) {{
                                // Save button is div.sendMsg, not button element!
                                const saveBtn = document.querySelector('div.sendMsg') || document.querySelector('.sendMsgbtn_container .sendMsg');
                                if (saveBtn) {{ saveBtn.click(); return 'NAUKRI_CHAT_RADIO_SAVED'; }}
                            }}
                        }}
                        
                        // Try Checkboxes - Handle both standard checkboxes and Naukri's mcc__checkbox elements
                        // First try the specific mcc__checkbox (used for city selection, etc.)
                        let allCheckboxes = Array.from(document.querySelectorAll('.mcc__checkbox'));
                        
                        // Fallback to standard checkbox selector if mcc not found
                        if (allCheckboxes.length === 0) {{
                            const cbContainer = document.querySelector('.chatbot_MessageContainer li:last-child') || document.body;
                            allCheckboxes = Array.from(cbContainer.querySelectorAll('input[type="checkbox"]'));
                        }}

                        // Debug log 
                        const debugLog = [];

                        if (allCheckboxes.length > 0) {{
                            let clickedCount = 0;
                            
                            // City preference order (check qText to see if it's a city question)
                            const qTextLower = qText.toLowerCase();
                            const isCityQuestion = qTextLower.includes('city') || qTextLower.includes('relocate') || qTextLower.includes('location');
                            const preferredCities = ['bengaluru', 'bangalore', 'hyderabad', 'pune', 'mumbai', 'chennai', 'delhi', 'noida', 'gurgaon'];
                            
                            for (const cb of allCheckboxes) {{
                                // Find Label using mcc__label or standard methods
                                let label = cb.closest('label') || document.querySelector(`label.mcc__label[for="${{cb.id}}"]`);
                                if (!label && cb.id) {{
                                    label = document.querySelector(`label[for="${{cb.id}}"]`);
                                }}
                                if (!label) {{
                                    label = cb.parentElement; 
                                }}
                                
                                const labelText = label ? (label.innerText || cb.id || '') : (cb.id || '');
                                const lowerLabel = labelText.toLowerCase();

                                debugLog.push("CB: " + labelText);
                                
                                // Ignore job list checkboxes
                                if (cb.closest('.naukicon-ot-checkbox')) continue;

                                // ALWAYS ignore "Skip"
                                if (lowerLabel.includes('skip')) continue;
                                
                                // If already checked, count but don't re-click
                                if (cb.checked) {{
                                    clickedCount++;
                                    continue;
                                }}

                                // For city questions, prefer "Both" or "All" option first
                                if (isCityQuestion) {{
                                    if (lowerLabel.includes('both') || lowerLabel.includes('all')) {{
                                        cb.click();
                                        if (!cb.checked) {{
                                            cb.checked = true;
                                            cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        }}
                                        // Click save and return immediately
                                        const saveBtn = document.querySelector('div.sendMsg:not(.disabled)') || document.querySelector('.sendMsgbtn_container .sendMsg');
                                        if (saveBtn) {{ 
                                            saveBtn.click(); 
                                            return 'NAUKRI_CHAT_CHECKBOX_SAVED: Selected Both/All locations'; 
                                        }}
                                    }}
                                    // Continue to select all cities
                                }}

                                // ACTION: Click the checkbox
                                cb.click();
                                
                                // Verification & Fallback
                                if (!cb.checked) {{
                                     cb.checked = true;
                                     cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                }}
                                
                                clickedCount++;
                            }}
                            
                            if (clickedCount > 0) {{
                                const saveBtn = document.querySelector('div.sendMsg:not(.disabled)') || document.querySelector('.sendMsgbtn_container .sendMsg');
                                if (saveBtn) {{ 
                                    saveBtn.click(); 
                                    return 'NAUKRI_CHAT_CHECKBOX_SAVED: ' + clickedCount + ' | DBG: ' + debugLog.join(', '); 
                                }}
                            }}
                        }}

                        // Try option buttons
                        const optionBtns = document.querySelectorAll('.chatbot_OptionContainer button');
                        if (optionBtns.length > 0) {{ optionBtns[0].click(); return 'NAUKRI_CHAT_OPT_CLICKED'; }}
                        
                        // DOM INSPECTION on Wait
                        const activeMsg = document.querySelector('.chatbot_MessageContainer li:last-child') || document.querySelector('.chatbot_MessageContainer');
                        const dump = activeMsg ? activeMsg.innerHTML.slice(0, 800) : 'No active msg';
                        
                        return 'NAUKRI_CHAT_WAITING | DOM: ' + dump + ' | CBs: ' + debugLog.join(', ');
                        
                        return 'NAUKRI_CHAT_WAITING';
                    }}
                    
                    // 2. Check if we're on the recommended jobs page
                    const applyBtn = document.querySelector('button.multi-apply-button');
                    if (applyBtn) {{
                        const remaining = parseInt(sessionStorage.getItem('naukri_remaining') || TARGET_JOBS);
                        let clickedCount = 0;
                        
                        // Use the EXACT Naukri checkbox selector from DOM inspection
                        // Unchecked: i.dspIB.naukicon.naukicon-ot-checkbox (without Checked class)
                        // Checked: i.dspIB.naukicon.naukicon-ot-Checked
                        const uncheckedBoxes = document.querySelectorAll(
                            'i.naukicon.naukicon-ot-checkbox:not(.naukicon-ot-Checked)'
                        );
                        
                        // If no unchecked boxes in current section, navigate to next tab
                        if (uncheckedBoxes.length === 0) {{
                            // Navigate to next tab in order
                            const tabOrder = ['profile', 'apply', 'preference', 'similar_jobs', 'top_candidate'];
                            
                            // Find current active tab using CORRECT class: tab-list-active
                            const activeTab = document.querySelector('.tab-list-active');
                            let currentTabId = '';
                            if (activeTab) {{
                                const wrapper = activeTab.closest('.tab-wrapper');
                                currentTabId = wrapper?.id || '';
                            }}
                            
                            // Get current index (default to 0/profile if not detected)
                            let currentIdx = tabOrder.indexOf(currentTabId);
                            if (currentIdx === -1) {{
                                // Tab not detected - assume first tab (profile) is active
                                currentIdx = 0;
                            }}
                            
                            const nextIdx = currentIdx + 1;
                            if (nextIdx < tabOrder.length) {{
                                const nextTabId = tabOrder[nextIdx];
                                const nextTab = document.querySelector(`#${{nextTabId}} .tab-list-item`) ||
                                               document.getElementById(nextTabId);
                                if (nextTab) {{
                                    nextTab.click();
                                    return 'NAUKRI_NAVIGATING_TO_TAB (0 jobs): ' + nextTabId + ' (from: ' + (currentTabId || 'unknown') + ')';
                                }}
                            }}
                            return 'NAUKRI_NO_JOBS_LEFT: All tabs exhausted';
                        }}
                        
                        // Apply to WHATEVER jobs are available (even if < 5)
                        // The remaining counter will be updated after successful application
                        
                        for (const checkbox of uncheckedBoxes) {{
                            if (clickedCount >= remaining) break;
                            if (checkbox.offsetParent !== null) {{
                                checkbox.scrollIntoView({{ block: 'center' }});
                                checkbox.click();
                                clickedCount++;
                            }}
                        }}
                        
                        // Fallback: Try article-based approach
                        if (clickedCount === 0) {{
                            const articles = document.querySelectorAll('article.jobTuple, .sim-jobs article, .list article');
                            for (const article of articles) {{
                                if (clickedCount >= remaining) break;
                                const checkbox = article.querySelector('i.naukicon-ot-checkbox:not(.naukicon-ot-Checked)') ||
                                                article.querySelector('.tuple-check-box i:not(.checked)') ||
                                                article.querySelector('input[type="checkbox"]:not(:checked)');
                                if (checkbox && checkbox.offsetParent !== null) {{
                                    checkbox.scrollIntoView({{ block: 'center' }});
                                    checkbox.click();
                                    clickedCount++;
                                }}
                            }}
                        }}
                        
                        // If we selected some jobs, click Apply with robustness
                        if (clickedCount > 0) {{
                            applyBtn.scrollIntoView({{ block: 'center', behavior: 'smooth' }});
                            // NOTE: await removed - Python handles delays between evaluate calls
                            
                            // Robust click sequence
                            applyBtn.click();
                            applyBtn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
                            applyBtn.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true, view: window }}));
                            applyBtn.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                            
                            // MONITOR: Check for error snackbar
                            // NOTE: Loop-based await removed - single check only, Python handles polling
                            for (let i = 0; i < 1; i++) {{
                                // NOTE: await sleep(500) removed - Python handles delays between evaluate calls
                                const snackBody = document.querySelector('.ss-snackbar-body');
                                if (snackBody && snackBody.offsetParent !== null) {{
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong')) {{
                                        const closeBtn = document.querySelector('button.ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }}
                                }}
                                // Generic fallback
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"]');
                                if (genericSnack && genericSnack.innerText.toLowerCase().includes('error')) {{
                                    return 'NAUKRI_RATE_LIMITED: Generic error detected';
                                }}
                            }}
                            
                            return 'NAUKRI_APPLY_CLICKED: ' + clickedCount + ' jobs selected';
                        }}
                        
                        // Check if there are already some checked
                        const alreadyChecked = document.querySelectorAll('i.naukicon-ot-Checked, .tuple-check-box i.checked, input[type="checkbox"]:checked').length;
                        if (alreadyChecked > 0) {{
                            applyBtn.scrollIntoView({{ block: 'center', behavior: 'smooth' }});
                            // NOTE: await removed - Python handles delays between evaluate calls
                            
                            applyBtn.click();
                            applyBtn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
                            applyBtn.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true, view: window }}));
                            applyBtn.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                            
                            // MONITOR: Check for error snackbar
                            // NOTE: Loop-based await removed - single check only, Python handles polling
                            for (let i = 0; i < 1; i++) {{
                                // NOTE: await sleep(500) removed - Python handles delays between evaluate calls
                                const snackBody = document.querySelector('.ss-snackbar-body');
                                if (snackBody && snackBody.offsetParent !== null) {{
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong')) {{
                                        const closeBtn = document.querySelector('button.ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }}
                                }}
                                // Generic fallback
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"]');
                                if (genericSnack && genericSnack.innerText.toLowerCase().includes('error')) {{
                                    return 'NAUKRI_RATE_LIMITED: Generic error detected';
                                }}
                            }}
                            
                            return 'NAUKRI_APPLY_CLICKED: ' + alreadyChecked + ' jobs already selected';
                        }}
                        
                        // No checkboxes in current section - navigate to next tab in order
                        // Order: Profile → Applies → Preferences → You might like → Top Candidate
                        const tabOrder = ['profile', 'apply', 'preference', 'similar_jobs', 'top_candidate'];
                        
                        // Find current active tab using CORRECT class: tab-list-active
                        const activeTab = document.querySelector('.tab-list-active');
                        let currentTabId = '';
                        if (activeTab) {{
                            const wrapper = activeTab.closest('.tab-wrapper');
                            currentTabId = wrapper?.id || '';
                        }}
                        
                        // Get current index (default to 0/profile if not detected)
                        let currentIdx = tabOrder.indexOf(currentTabId);
                        if (currentIdx === -1) {{
                            currentIdx = 0;  // Assume profile is active
                        }}
                        
                        const nextIdx = currentIdx + 1;
                        if (nextIdx < tabOrder.length) {{
                            const nextTabId = tabOrder[nextIdx];
                            const nextTab = document.querySelector(`#${{nextTabId}} .tab-list-item`) ||
                                           document.getElementById(nextTabId);
                            if (nextTab) {{
                                nextTab.click();
                                return 'NAUKRI_NAVIGATING_TO_TAB: ' + nextTabId;
                            }}
                        }}
                        
                        return 'NAUKRI_NO_CHECKBOX_IN_SECTION: All tabs exhausted';
                    }}
                }}

                // ============================================================
                // INSTAHYRE LOGIC (Fully Restored & Robust)
                // ============================================================
                if (isInstahyre) {{
                    // Helper function to add items to selectize dropdowns
                    const addSelectizeItem = (containerSelector, inputSelector, itemText) => {{
                        const container = document.querySelector(containerSelector);
                        const input = document.querySelector(inputSelector);
                        if (!container || !input) return false;
                        
                        // Check if item already exists
                        const existingItems = container.querySelectorAll('.item');
                        for (const item of existingItems) {{
                            if (item.textContent && item.textContent.toLowerCase().includes(itemText.toLowerCase())) {{
                                return false; // Already added
                            }}
                        }}
                        
                        // Focus the input to open dropdown
                        input.focus();
                        input.click();
                        
                        // Type the text
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        if (setter) setter.call(input, itemText);
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', keyCode: 13, bubbles: true }}));
                        
                        return true;
                    }};
                    
                    // 1. Navigation: Ensure "Search other jobs" (Filter Panel) is OPEN
                    if (window.location.href.includes('opportunities')) {{
                        
                        // IMPORTANT: If URL has search params, we're already on results - skip filter config
                        const urlParams = new URLSearchParams(window.location.search);
                        const hasSearchParams = urlParams.has('job_functions') || urlParams.has('skills');
                        
                        // Check if filters panel is OPEN using the filters container (more reliable)
                        const filtersPanel = document.querySelector('div.job-search-filters');
                        const expInput = document.querySelector('input#years');
                        const isPanelOpen = (filtersPanel && filtersPanel.offsetParent !== null) || 
                                           (expInput && expInput.offsetParent !== null);
                        
                        // Check for collapsed state indicator (chevron pointing down)
                        const chevronDown = document.querySelector('.job-search-heading .fa-angle-down');
                        const isPanelCollapsed = chevronDown && chevronDown.offsetParent !== null;
                        
                        // Skip filter configuration if we already have search results
                        // If Panel is CLOSED (or collapsed) and NOT on search results, we must Open it
                        if ((!isPanelOpen || isPanelCollapsed) && !hasSearchParams) {{
                            // PRIORITY 1: Target the exact Instahyre class for "Search other jobs"
                            const jobSearchHeading = document.querySelector('.job-search-heading');
                            if (jobSearchHeading) {{
                                console.log('Clicking job-search-heading:', jobSearchHeading.innerText);
                                // Use MouseEvent dispatch for Angular ng-click compatibility
                                const clickEvent = new MouseEvent('click', {{
                                    bubbles: true, cancelable: true, view: window
                                }});
                                jobSearchHeading.dispatchEvent(clickEvent);
                                return 'INSTAHYRE_OPENING_PANEL';
                            }}
                            
                            // PRIORITY 2: Try the sidebar section container
                            const sidebarSection = document.querySelector('.sidebar-section.job-search-section');
                            if (sidebarSection) {{
                                const heading = sidebarSection.querySelector('div[ng-click]');
                                if (heading) {{
                                    console.log('Clicking sidebar section heading');
                                    const clickEvent = new MouseEvent('click', {{
                                        bubbles: true, cancelable: true, view: window
                                    }});
                                    heading.dispatchEvent(clickEvent);
                                    return 'INSTAHYRE_OPENING_PANEL';
                                }}
                            }}
                            
                            // PRIORITY 3: Fallback - text match with MouseEvent
                            const searchTriggers = Array.from(document.querySelectorAll('div, span, h4, h5')).filter(el => 
                                el.innerText && el.innerText.trim().toLowerCase() === 'search other jobs'
                            );
                            for (const trigger of searchTriggers) {{
                                if (trigger && trigger.offsetParent !== null) {{
                                    console.log('Clicking Search Trigger (text match):', trigger);
                                    const clickEvent = new MouseEvent('click', {{
                                        bubbles: true, cancelable: true, view: window
                                    }});
                                    trigger.dispatchEvent(clickEvent);
                                    return 'INSTAHYRE_OPENING_PANEL';
                                }}
                            }}
                        }}
                        
                        // 2. Fill Details (Configuration) - One step at a time for reliability
                        // ORDER: Skills -> Job Functions -> Location -> Experience
                        
                        // Helper function to get selectize instance
                        // NOTE: Instahyre uses custom <selectize> tags, NOT <select> tags
                        const getSelectize = (fieldId) => {{
                            const selectizeEl = document.querySelector('selectize#' + fieldId);
                            return selectizeEl && selectizeEl.selectize ? selectizeEl.selectize : null;
                        }};
                        
                        // Check for pending operations (prevents rapid re-invocations)
                        const pendingOp = sessionStorage.getItem('instahyre_pending');
                        if (pendingOp) {{
                            const [op, timestamp] = pendingOp.split('|');
                            const elapsed = Date.now() - parseInt(timestamp);
                            if (elapsed < 800) {{
                                // Still waiting for previous operation
                                return 'INSTAHYRE_WAITING: ' + op;
                            }} else {{
                                // Timeout expired, clear pending
                                sessionStorage.removeItem('instahyre_pending');
                            }}
                        }}
                        
                        // A. Skills - Add one skill at a time (FIRST)
                        const skillsToAdd = ['Java', 'JavaScript', 'HTML', 'CSS', 'SpringBoot', 'ReactJS', 'AWS'];
                        const skillsSelectize = getSelectize('skills');
                        const skillsInput = document.querySelector('input#skills-selectized');
                        if (skillsInput) {{
                            const skillsControl = skillsInput.closest('.selectize-control');
                            const skillsContainer = skillsControl ? skillsControl.querySelector('.selectize-input') : null;
                            if (skillsContainer) {{
                                // Check existing skills using Selectize API
                                let existingSkills = [];
                                if (skillsSelectize) {{
                                    existingSkills = skillsSelectize.items.map(key => {{
                                        const opt = skillsSelectize.options[key];
                                        return opt ? (opt.text || opt.name || key).toLowerCase() : key.toLowerCase();
                                    }});
                                }} else {{
                                    // Fallback: DOM parsing with × removal
                                    existingSkills = Array.from(skillsContainer.querySelectorAll('.item'))
                                        .map(item => (item.textContent || '').replace(/×/g, '').toLowerCase().trim());
                                }}
                                
                                for (const skill of skillsToAdd) {{
                                    if (!existingSkills.some(s => s.includes(skill.toLowerCase()))) {{
                                        // Try Selectize API first
                                        if (skillsSelectize) {{
                                            // Use addItem if option exists, else createItem
                                            if (skillsSelectize.options[skill]) {{
                                                skillsSelectize.addItem(skill);
                                            }} else {{
                                                skillsSelectize.createItem(skill);
                                            }}
                                            return 'INSTAHYRE_ADDED_SKILL: ' + skill;
                                        }}
                                        // Fallback: Set pending state, trigger input, schedule click
                                        sessionStorage.setItem('instahyre_pending', 'skill_' + skill + '|' + Date.now());
                                        skillsInput.focus();
                                        skillsInput.click();
                                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                        if (setter) setter.call(skillsInput, skill);
                                        skillsInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        // Schedule click with longer delay
                                        setTimeout(() => {{
                                            const dropdown = skillsControl.querySelector('.selectize-dropdown-content');
                                            if (dropdown) {{
                                                const option = dropdown.querySelector('.option.active, .option:first-child');
                                                if (option) {{
                                                    option.click();
                                                    sessionStorage.removeItem('instahyre_pending');
                                                }}
                                            }}
                                        }}, 500);
                                        return 'INSTAHYRE_ADDING_SKILL: ' + skill;
                                    }}
                                }}
                            }}
                        }}
                        
                        // B. Job Functions - Use Selectize API (SECOND)
                        const jobFuncsToAdd = ['Backend Development', 'Frontend Development', 'Full-Stack Development'];
                        const jobFuncSelectize = getSelectize('job-functions');
                        const jobFuncInput = document.querySelector('input#job-functions-selectized');
                        if (jobFuncInput) {{
                            const jobFuncControl = jobFuncInput.closest('.selectize-control');
                            const jobFuncContainer = jobFuncControl ? jobFuncControl.querySelector('.selectize-input') : null;
                            if (jobFuncContainer) {{
                                // Use Selectize API for accurate check of existing items
                                let existingTexts = [];
                                if (jobFuncSelectize) {{
                                    existingTexts = jobFuncSelectize.items.map(key => {{
                                        const opt = jobFuncSelectize.options[key];
                                        return opt ? (opt.text || opt.name || key).toLowerCase() : key.toLowerCase();
                                    }});
                                }} else {{
                                    // Fallback: DOM parsing with × removal
                                    existingTexts = Array.from(jobFuncContainer.querySelectorAll('.item'))
                                        .map(item => (item.textContent || '').replace(/×/g, '').toLowerCase().trim());
                                }}
                                
                                for (const func of jobFuncsToAdd) {{
                                    const funcKeyword = func.split(' ')[0].toLowerCase(); // "backend", "frontend", "full-stack"
                                    if (!existingTexts.some(f => f.includes(funcKeyword))) {{
                                        // Try Selectize API first
                                        if (jobFuncSelectize) {{
                                            // Find the option key by matching text
                                            const options = jobFuncSelectize.options;
                                            let foundKey = null;
                                            for (const key in options) {{
                                                const optText = (options[key].text || options[key].name || '').toLowerCase();
                                                if (optText.includes(funcKeyword)) {{
                                                    foundKey = key;
                                                    break;
                                                }}
                                            }}
                                            if (foundKey) {{
                                                jobFuncSelectize.addItem(foundKey);
                                                return 'INSTAHYRE_ADDED_JOB_FUNC: ' + func;
                                            }}
                                        }}
                                        // Fallback: Set pending state, trigger input, schedule click
                                        sessionStorage.setItem('instahyre_pending', 'jobfunc_' + func + '|' + Date.now());
                                        jobFuncInput.focus();
                                        jobFuncInput.click();
                                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                        if (setter) setter.call(jobFuncInput, funcKeyword);
                                        jobFuncInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        setTimeout(() => {{
                                            const dropdown = jobFuncControl.querySelector('.selectize-dropdown-content');
                                            if (dropdown) {{
                                                const option = dropdown.querySelector('.option.active, .option:first-child');
                                                if (option) {{
                                                    option.click();
                                                    sessionStorage.removeItem('instahyre_pending');
                                                }}
                                            }}
                                        }}, 500);
                                        return 'INSTAHYRE_ADDING_JOB_FUNC: ' + func;
                                    }}
                                }}
                            }}
                        }}
                        
                        // C. Location - Use Selectize API (THIRD)
                        const locationSelectize = getSelectize('locations');
                        const locationInput = document.querySelector('input#locations-selectized');
                        if (locationInput) {{
                            const locControl = locationInput.closest('.selectize-control');
                            const locationContainer = locControl ? locControl.querySelector('.selectize-input') : null;
                            if (locationContainer) {{
                                // Check existing locations using Selectize API
                                let hasAnywhereIndia = false;
                                if (locationSelectize) {{
                                    hasAnywhereIndia = locationSelectize.items.some(key => {{
                                        const opt = locationSelectize.options[key];
                                        const text = opt ? (opt.text || opt.name || key) : key;
                                        return text.toLowerCase().includes('anywhere');
                                    }});
                                }} else {{
                                    // Fallback: DOM parsing with × removal
                                    hasAnywhereIndia = Array.from(locationContainer.querySelectorAll('.item')).some(
                                        item => (item.textContent || '').replace(/×/g, '').toLowerCase().includes('anywhere')
                                    );
                                }}
                                if (!hasAnywhereIndia) {{
                                    // Try Selectize API first
                                    if (locationSelectize) {{
                                        const options = locationSelectize.options;
                                        let foundKey = null;
                                        for (const key in options) {{
                                            const optText = (options[key].text || options[key].name || '').toLowerCase();
                                            if (optText.includes('anywhere')) {{
                                                foundKey = key;
                                                break;
                                            }}
                                        }}
                                        if (foundKey) {{
                                            locationSelectize.addItem(foundKey);
                                            return 'INSTAHYRE_ADDED_LOCATION: Anywhere in India';
                                        }}
                                    }}
                                    // Fallback: Set pending state, trigger input, schedule click
                                    sessionStorage.setItem('instahyre_pending', 'location|' + Date.now());
                                    locationInput.focus();
                                    locationInput.click();
                                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                    if (setter) setter.call(locationInput, 'Anywhere');
                                    locationInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    setTimeout(() => {{
                                        const dropdown = locControl.querySelector('.selectize-dropdown-content');
                                        if (dropdown) {{
                                            const option = Array.from(dropdown.querySelectorAll('.option')).find(
                                                opt => opt.textContent.toLowerCase().includes('anywhere')
                                            );
                                            if (option) {{
                                                option.click();
                                                sessionStorage.removeItem('instahyre_pending');
                                            }}
                                        }}
                                    }}, 500);
                                    return 'INSTAHYRE_ADDING_LOCATION';
                                }}
                            }}
                        }}
                        
                        // D. Experience (LAST - after all selectize fields)
                        if (expInput && expInput.value !== '4') {{
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            if (setter) setter.call(expInput, '4');
                            expInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            expInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return 'INSTAHYRE_SET_EXPERIENCE';
                        }}

                        // 3. Click "Show Results" - Only after ALL fields are configured AND not already on results
                        // Use exact selector from DOM: button#show-results.btn.btn-primary.show-results
                        const showResultsBtn = document.querySelector('button#show-results.btn-primary.show-results') ||
                                              document.querySelector('button#show-results');
                        if (showResultsBtn && showResultsBtn.offsetParent !== null && isPanelOpen && !hasSearchParams) {{
                            // Verify ALL fields are configured before clicking
                            const hasExp = expInput && expInput.value === '4';
                            
                            // Check location - use correct plural selector
                            const locInput = document.querySelector('input#locations-selectized');
                            const locCtrl = locInput ? locInput.closest('.selectize-control') : null;
                            const locContainer = locCtrl ? locCtrl.querySelector('.selectize-input') : null;
                            const hasLocation = locContainer && locContainer.querySelectorAll('.item').length > 0;
                            
                            // Check skills (need at least 3 skills)
                            const skillsInp = document.querySelector('input#skills-selectized');
                            const skillsCtrl = skillsInp ? skillsInp.closest('.selectize-control') : null;
                            const skillsContainerCheck = skillsCtrl ? skillsCtrl.querySelector('.selectize-input') : null;
                            const hasSkills = skillsContainerCheck && skillsContainerCheck.querySelectorAll('.item').length >= 3;
                            
                            // Check job functions (need at least 1)
                            const jobFuncInp = document.querySelector('input#job-functions-selectized');
                            const jobFuncCtrl = jobFuncInp ? jobFuncInp.closest('.selectize-control') : null;
                            const jobFuncContainerCheck = jobFuncCtrl ? jobFuncCtrl.querySelector('.selectize-input') : null;
                            const hasJobFuncs = jobFuncContainerCheck && jobFuncContainerCheck.querySelectorAll('.item').length >= 1;
                            
                            console.log('Config check: Exp=' + hasExp + ', Loc=' + hasLocation + ', Skills=' + hasSkills + ', JobFuncs=' + hasJobFuncs);
                            
                            // Only click Show Results if ALL fields are configured
                            if (hasExp && hasLocation && hasSkills && hasJobFuncs) {{
                                showResultsBtn.scrollIntoView({{ block: 'center' }});
                                showResultsBtn.click();
                                return 'INSTAHYRE_SHOW_RESULTS_CLICKED';
                            }} else {{
                                // Return status indicating which field is pending
                                if (!hasSkills) return 'INSTAHYRE_PENDING_SKILLS';
                                if (!hasJobFuncs) return 'INSTAHYRE_PENDING_JOB_FUNCS';
                                if (!hasLocation) return 'INSTAHYRE_PENDING_LOCATION';
                                if (!hasExp) return 'INSTAHYRE_PENDING_EXPERIENCE';
                            }}
                        }}
                    }}

                    // 4. View & Apply (The Main Loop)
                    
                    // A. Handle Modal - Look for Apply button in any modal
                    const modalApplyBtns = document.querySelectorAll('.modal button.btn-primary, .application-modal button, [class*="modal"] button.btn-primary');
                    for (const btn of modalApplyBtns) {{
                        if (btn && btn.offsetParent !== null && (btn.innerText || '').toLowerCase().includes('apply')) {{
                            btn.click();
                            return 'INSTAHYRE_APPLY_CLICKED';
                        }}
                    }}
                    
                    // B. Close success modals
                    const successIndicators = document.querySelectorAll('.alert-success, .success-message, [class*="success"]');
                    for (const indicator of successIndicators) {{
                        if (indicator && indicator.offsetParent !== null) {{
                            const closeBtn = indicator.querySelector('button.close, .close, [data-dismiss="modal"]') ||
                                            document.querySelector('.modal button.close, .modal .close');
                            if (closeBtn) {{
                                closeBtn.click();
                                return 'INSTAHYRE_MODAL_CLOSED_SUCCESS';
                            }}
                        }}
                    }}
                    
                    // C. Click "View" on Job Cards - prioritized selector patterns from DOM inspection
                    // Primary: Exact selector from user's DOM screenshot
                    const primaryViewBtn = document.querySelector('button#interested-btn.btn-success:not([disabled])');
                    if (primaryViewBtn && primaryViewBtn.offsetParent !== null) {{
                        primaryViewBtn.scrollIntoView({{ block: 'center' }});
                        primaryViewBtn.click();
                        return 'INSTAHYRE_VIEW_CLICKED';
                    }}
                    
                    // Secondary: Multiple fallback patterns
                    const viewBtnSelectors = [
                        'button#interested-btn',
                        'button.button-interested.btn-success',
                        'button[ng-click*="openApplyModal"]',
                        '.opportunity-action-links button.btn-success',
                        'button.button-interested',
                        'button.btn-success',
                        'a.view-job',
                        '[class*="interested"] button'
                    ];
                    for (const sel of viewBtnSelectors) {{
                        const btns = document.querySelectorAll(sel);
                        for (const btn of btns) {{
                            const btnText = (btn.innerText || '').toLowerCase();
                            if ((btnText.includes('view') || btnText.includes('interested')) && !btn.disabled && btn.offsetParent !== null) {{
                                btn.scrollIntoView({{ block: 'center' }});
                                btn.click();
                                return 'INSTAHYRE_VIEW_CLICKED';
                            }}
                        }}
                    }}
                    
                    // D. Check if no more jobs available
                    const noJobsIndicators = [
                        document.querySelector('.no-jobs, .no-results, [class*="empty-state"]'),
                        document.body.innerText.includes('No matching jobs'),
                        document.body.innerText.includes('No jobs found')
                    ];
                    if (noJobsIndicators.some(Boolean)) {{
                        return 'INSTAHYRE_NO_MORE_JOBS';
                    }}
                    
                    // E. Scroll to load more jobs if needed
                    const jobCards = document.querySelectorAll('.job-card, [class*="opportunity-card"], .card');
                    if (jobCards.length > 0) {{
                        const lastCard = jobCards[jobCards.length - 1];
                        lastCard.scrollIntoView({{ block: 'end' }});
                        return 'INSTAHYRE_SCROLLING_FOR_MORE';
                    }}
                }}

                return 'NO_ACTION';
            }})"""
            
            # Playwright automatically invokes the function expression
            result = await self._page.evaluate(js_code)
            return result
            

            
        except Exception as e:
            print(f"Error in scripted fallback: {e}")
            return "ERROR"


def create_agent():
    return SentinelAgent()


