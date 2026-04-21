import asyncio
import json
import random
import os
import hashlib
import re
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
    are_questions_similar,
    SYNONYM_MAP, STOP_WORDS
)
from src.patterns.input_aware_resolver import (
    InputAwareResolver, InputType as ResolverInputType, Option, MatchResult
)
from src.sentinel.self_healing import SelfHealingMatcher
from src.patterns.pattern_learner import PatternLearner


# Known question patterns and their answers for fuzzy matching
KNOWN_QA_PATTERNS = {
    # Experience
    'years of experience': '3.8 Years',
    'months of experience': '46',
    'total experience': '3.8 Years',
    'overall experience': '3.8 Years',
    'year of exp': '3.8 Years',
    # Experience Range Questions - map to appropriate radio button ranges
    'experience': '3.8 Years',
    'years': '3.8 Years',
    'java experience': '3.8 Years',
    'react experience': '4 Years',
    'angular experience': '4 Years',
    'nodejs experience': '3.8 Years',
    'javascript experience': '3.8 Years',
    'ci/cd experience': '3.8 Years',
    'full stack experience': '3.8 Years',
    'backend experience': '3.8 Years',
    'frontend experience': '3.8 Years',
    'software experience': '3.8 Years',
    'web experience': '3.8 Years',
    'python experience': '3.8 Years',
    'programming experience': '3.8 Years',
    'which programming language': 'Python, Node.js / TypeScript, Both',
    'programming language most experienced': 'Python, Node.js / TypeScript, Both',
    'programming language are you most experienced': 'Python, Node.js / TypeScript, Both',
    # Salary (LPA format for Naukri - LinkedIn gets plain numbers via JS override)
    'current salary': '13.5 LPA',
    'what is your current salary?': '13.5 LPA',
    'expected salary': '24 LPA',
    'what is your expected salary?': '24 LPA',
    'gross salary': '13.5 LPA',
    'gross current salary': '13.5 LPA',
    'gross expected salary': '24 LPA',
    'salary expectations': '24 LPA',
    # Current/Expected Annual Salary — common LinkedIn phrasing
    'current annual salary': '1350000',
    'what is your current annual salary': '1350000',
    'what is your current annual salary?': '1350000',
    'expected annual salary': '2400000',
    'what is your expected annual salary': '2400000',
    'what is your expected annual salary?': '2400000',
    'what is your expected annual salary ?': '2400000',
    'current ctc': '1350000',
    'what is your current ctc': '1350000',
    'what is your current ctc?': '1350000',
    # Fixed CTC and Variable Pay - Numeric values
    'fixed ctc': '1350000',
    'fixed ctc numeric': '1350000',
    'fixed ctc numeric input': '1350000',
    'variable pay': '0',
    'variable pay numeric': '0',
    'variable pay numeric input': '0',
    # Expected Annual CTC in INR
    'expected annual ctc in inr': '2400000',
    'expected annual ctc': '2400000',
    'expected ctc in inr': '2400000',
    'expected ctc inr': '2400000',
    # Salary Range Questions - Current: 13.5 LPA, Expected: 24 LPA
    'salary range': '10-15 Lacs',
    'current salary range': '10-15 Lacs',
    'expected salary range': '20-25 Lacs',
    'annual salary': '10-15 Lacs',
    'ctc range': '10-15 Lacs',
    # CTC in Lacs per annum - specific pattern for HighRadius
    'ctc in lacs per annum': '15.3',
    'what is your current ctc in lacs per annum': '15.3',
    'current ctc in lacs per annum': '15.3',
    # Personal
    'phone number': '7905828880',
    'mobile number': '7905828880',
    'email address': 'siddhant3646@gmail.com',
    'current location': 'Noida',
    'current city': 'Noida',
    'preferred location': 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune',
    # Role / Designation
    'current role': 'SDE-2 Full Stack Developer',
    'what is your current role': 'SDE-2 Full Stack Developer',
    'current designation': 'SDE-2 Full Stack Developer',
    'current position': 'SDE-2 Full Stack Developer',
    'current job title': 'SDE-2 Full Stack Developer',
    'job title': 'SDE-2 Full Stack Developer',
    'designation': 'SDE-2 Full Stack Developer',
    'role': 'SDE-2 Full Stack Developer',
    'position': 'SDE-2 Full Stack Developer',
    # Company / Organization
    'current employer': 'Fiserv',
    'current company': 'Fiserv',
    'current company name': 'Fiserv',
    'company name': 'Fiserv',
    'current organization': 'Fiserv',
    'current organization name': 'Fiserv',
    'organization name': 'Fiserv',
    'current organisation': 'Fiserv',
    'current organisation name': 'Fiserv',
    'organisation name': 'Fiserv',
    'what is your current organization': 'Fiserv',
    'what is your current organisation': 'Fiserv',
    'previous company': 'Fiserv',
    # Notice
    'notice period': 'Serving Notice Period',
    'what is your notice period': 'Serving Notice Period',
    'what is your notice period?': 'Serving Notice Period',
    'what is your notice period ?': 'Serving Notice Period',
    'notice period in days': '30',
    'notice period days': '30',
    'notice period for your current company in days': '30',
    'notice period for your current company': '30',
    'current company notice period': '30',
    'notice period of your current company': '30',
    'what is the notice period for your current company': '30',
    'serving notice': 'Serving Notice Period',
    'serving notice period': 'Serving Notice Period',
    'are you serving notice': 'Serving Notice Period',
    'are you serving notice period': 'Yes',
    'are you currently serving notice period': 'Yes',
    'are you currently serving notice': 'Yes',
    'currently serving notice': 'Serving Notice Period',
    'currently serving notice period': 'Yes',
    # LinkedIn specific - "Are You Currently Serving/Served Notice Period?" dropdown
    'are you currently serving/served notice period': 'Yes',
    'currently serving/served notice period': 'Yes',
    'serving/served notice period': 'Yes',
    'are you currently serving or served notice': 'Yes',
    'currently serving or served notice': 'Yes',
    # LinkedIn specific - "Manager wants someone who can join Immediately or within 15-30 days"
    'manager wants someone who can join immediately or within 15-30 days': 'Yes',
    'join immediately or within 15-30 days': 'Yes',
    'can you join immediately or within 15-30 days': 'Yes',
    'join within 15-30 days': 'Yes',
    'can join within 15-30 days': 'Yes',
    'immediately or within 15-30 days': 'Yes',
    # Radio button questions (Yes/No)
    'any offer in hand': 'No',
    'do you have any offer': 'No',
    'offer in hand': 'No',
    'any offers': 'No',
    'currently holding offer': 'No',
    'are you comfortable working during overlapping us hours': 'Yes',
    'comfortable working us hours': 'Yes',
    'overlapping us hours': 'Yes',
    'us hours weekly calls': 'Yes',
    'have you ever been employed by': 'No',
    'previously employed': 'No',
    'worked for navan': 'No',
    'worked for reed': 'No',
    'applied to navan': 'No',
    'affiliated companies': 'No',
    # Education
    'graduation year': '2022',
    'year of graduation': '2022',
    'passing year': '2022',
    'year of passing': '2022',
    'batch': '2022',
    'cgpa': '8.51',
    'percentage': '85',
    'degree': 'B.Tech Computer Science',
    'highest qualification': 'B.Tech CSE',
    'highest degree': 'B.Tech CSE',
    'educational qualification': 'B.Tech CSE',
    'qualification': 'B.Tech CSE',
    'what is your highest qualification': 'B.Tech CSE',
    'what is your educational qualification': 'B.Tech CSE',
    'highest education': 'B.Tech CSE',
    'education': 'B.Tech CSE',
    'specialization': 'Computer Science and Engineering',
    'stream': 'Computer Science and Engineering',
    'branch': 'Computer Science and Engineering',
    'field of study': 'Computer Science and Engineering',
    'course': 'B.Tech',
    'additional months': '0',
    'additional years': '0',
    'additional months of experience': '0',
    'additional years of experience': '0',
    'college name': 'VIT Bhopal University',
    'university': 'VIT Bhopal University',
    'university name': 'VIT Bhopal University',
    'institute': 'VIT Bhopal University',
    'institute name': 'VIT Bhopal University',
    # Compliance - Employment History (All should be "No" unless explicitly true)
    'worked with visa in the past 2 years': 'No',
    'worked with visa in the last 2 years': 'No',
    'worked for visa in the past 2 years': 'No',
    'worked for visa in the last 2 years': 'No',
    'employed by visa in the past 2 years': 'No',
    'employed by visa in the last 2 years': 'No',
    'have you worked with visa': 'No',
    'have you worked for visa': 'No',
    'have you been employed by visa': 'No',
    'have you ever worked for visa': 'No',
    'have you ever worked with visa': 'No',
    'have you ever been employed by visa': 'No',
    'worked at visa': 'No',
    'employed at visa': 'No',
    'previous employment with visa': 'No',
    # Current employer (Fiserv) - should be "Yes"
    'worked with fiserv': 'Yes',
    'worked for fiserv': 'Yes',
    'worked at fiserv': 'Yes',
    'employed by fiserv': 'Yes',
    'employed at fiserv': 'Yes',
    'have you worked with fiserv': 'Yes',
    'have you worked for fiserv': 'Yes',
    'have you worked at fiserv': 'Yes',
    'have you been employed by fiserv': 'Yes',
    'have you ever worked for fiserv': 'Yes',
    'have you ever worked with fiserv': 'Yes',
    'are you currently employed by fiserv': 'Yes',
    'currently employed by fiserv': 'Yes',
    # General Compliance - All "No" by default for safety
    'have you worked with any of the following companies in the past 2 years': 'No',
    'have you worked with any of these companies': 'No',
    'have you been employed by any of the listed companies': 'No',
    'have you previously worked for': 'No',
    'have you ever been employed by any of the': 'No',
    'currently employed by any of the': 'No',
    'currently an employee of any': 'No',
    'do you have any relatives working': 'No',
    'do you have any family members employed': 'No',
    'do any of your relatives work': 'No',
    'conflict of interest': 'No',
    'any conflict of interest': 'No',
    'affiliated with any competitor': 'No',
    'associated with any competing firm': 'No',
    # Third-party/Contractor compliance
    'are you a third party': 'No',
    'are you currently a third party': 'No',
    'are you a temporary employee': 'No',
    'are you currently a temporary employee': 'No',
    # Links
    'linkedin url': 'https://www.linkedin.com/in/siddhant3646',
    'github url': 'https://github.com/siddhant3646',
    # Yes/No common
    'willing to relocate': 'Yes',
    'work authorization': 'Yes',
    'legally authorized': 'Yes',
    'authorized to work': 'Yes',
    'authorized to lawfully work': 'Yes',
    'authorized to lawfully work for': 'Yes',
    'lawfully authorized to work': 'Yes',
    'authorized to work in': 'Yes',
    'are you legally authorized to work in india': 'Yes',
    'are you legally authorized to work': 'Yes',
    'are you authorized to lawfully work': 'Yes',
    'do you have the right to work': 'Yes',
    'eligible to work in india': 'Yes',
    'background check': 'Yes',
    'drug test': 'Yes',
    # Consent / Data Collection Questions (Greenhouse, SmartBear, etc.)
    'consent to collect': 'Yes',
    'consent to collect store and process': 'Yes',
    'collect store and process': 'Yes',
    'data consent': 'Yes',
    'consent to process data': 'Yes',
    'employment consent': 'Yes',
    '1825 days': 'Yes',
    '1825 days thereafter': 'Yes',
    '730 days': 'Yes',
    '730 days thereafter': 'Yes',
    'up to 730 days': 'Yes',
    'for up to 730 days': 'Yes',
    'highradius has my consent': 'Yes',
    'highradius consent': 'Yes',
    'highradius data consent': 'Yes',
    'smartbear has my consent': 'Yes',
    'greenhouse consent': 'Yes',
    'data collection consent': 'Yes',
    'non-compete': 'No',
    'non compete': 'No',
    'noncompete': 'No',
    'non-competition': 'No',
    'do you have a non-compete': 'No',
    'non-compete agreement': 'No',
    'agreement that would prevent you from working': 'No',
    'prevent you from working with onit': 'No',
    'prevent you from working with simplelegal': 'No',
    'process my data': 'Yes',
    'store and process': 'Yes',
    'considering me for employment': 'Yes',
    'employment consideration': 'Yes',
    'remote work': 'Yes',
    'hybrid work': 'Yes',
    'work from office': 'Yes',
    'comfortable to work from office': 'Yes',
    'work from office 6 days': 'Yes',
    'work from office 5 days': 'Yes',
    'wfo': 'Yes',
    'full stack java developer': 'Yes',
    'java developer': 'Yes',
    'visa sponsorship': 'No',
    'require sponsorship': 'No',
    'will you now or in the future require sponsorship': 'No',
    'require visa sponsorship': 'No',
    'need sponsorship': 'No',
    # Gender / Disability / Veteran (LinkedIn EEO questions)
    'gender': 'Male',
    'what is your gender': 'Male',
    'race': 'Decline to self-identify',
    'ethnicity': 'Decline to self-identify',
    'disability': 'No, I don\'t have a disability',
    'disability status': 'No, I don\'t have a disability',
    'veteran': 'I am not a protected veteran',
    'veteran status': 'I am not a protected veteran',
    # Self-identification form fields
    'your name': 'Siddhant Singh',
    'today\'s date': '02/15/2026',
    'todays date': '02/15/2026',
    'sexual orientation': 'Decline to self-identify',
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
    # Mzad Qatar / Technical Experience Questions
    '5+ years of full-stack development experience': 'No',
    '5 plus years of full-stack': 'No',
    '5+ years full-stack': 'No',
    '5 years of full-stack': 'No',
    'backend experience': '4',
    'professional backend experience': '4',
    'ai apis': 'Yes',
    'integrated any ai apis': 'Yes',
    'openai anthropic': 'Yes',
    'ai-based features': '3',
    'ai based features': '3',
    'ai features': '3',
    'artificial intelligence features': '3',
    'designed database architecture': 'Yes',
    'database architecture from scratch': 'Yes',
    'deployed applications to cloud': 'Yes',
    'cloud servers aws': 'Yes',
    'aws vps independently': 'Yes',
    'production applications end-to-end': '5',
    'production applications end to end': '5',
    'built end-to-end': '5',
    'end-to-end full stack projects': 'Yes',
    'end to end full stack': 'Yes',
    'worked on any end-to-end': 'Yes',
    'full stack projects': 'Yes',
    'interested in joining this 6 months contract role': 'Yes',
    'contract role': 'Yes',
    '6 months contract': 'Yes',
    'interested in joining': 'Yes',
    'ci/cd pipelines': 'Yes',
    'cicd pipelines': 'Yes',
    'ci cd pipelines': 'Yes',
    'leading architecture decisions': 'Yes',
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
    # Address fields
    'street': 'Sector 137',
    'street address': 'Sector 137',
    'address line 1': 'Sector 137',
    'address line1': 'Sector 137',
    'state': 'Uttar Pradesh',
    'state/province': 'Uttar Pradesh',
    'province': 'Uttar Pradesh',
    'zip': '201301',
    'zip code': '201301',
    'postal code': '201301',
    'pincode': '201301',
    'pin code': '201301',
    'zip/postal code': '201301',
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
    'current ctc in lacs per annum': '13.5',
    'what is your current ctc in lacs per annum': '13.5',
    'what is your current ctc in lacs per annum?': '13.5',
    'ctc in lacs': '13.5',
    'expected ctc in lakhs': '24',
    'expected ctc in lpa': '24',
    'expected ctc [in lpa]': '24',
    'expected ctc in lacs per annum': '24',
    'what is your expected ctc in lacs per annum': '24',
    'what is your expected ctc in lacs per annum?': '24',
    'ctc in lakhs': '24',
    # CCTC = Current CTC (abbreviation)
    'cctc': '13.5',
    'what is your cctc': '13.5',
    'your cctc': '13.5',
    # ECTC = Expected CTC (abbreviation)
    'ectc': '24',
    'what is your ectc': '24',
    'your ectc': '24',
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
    # Portfolio URL
    'portfolio url': 'https://siddhant3646.github.io/Portfolio/',
    'online portfolio': 'https://siddhant3646.github.io/Portfolio/',
    'portfolio link': 'https://siddhant3646.github.io/Portfolio/',
    'online portfolio url': 'https://siddhant3646.github.io/Portfolio/',
    'website': 'https://siddhant3646.github.io/Portfolio/',
    'personal website': 'https://siddhant3646.github.io/Portfolio/',
    'website url': 'https://siddhant3646.github.io/Portfolio/',
    # How did you hear about us - LinkedIn Easy Apply
    'how did you hear about us': 'LinkedIn Ad (India)',
    'how did you hear about this job': 'LinkedIn Ad (India)',
    'how did you learn about us': 'LinkedIn Ad (India)',
    'where did you learn about miratech': 'LinkedIn Ad (India)',
    'where did you learn about us': 'LinkedIn Ad (India)',
    'source': 'LinkedIn Ad (India)',
    'referral source': 'LinkedIn Ad (India)',
    'where did you hear': 'LinkedIn Ad (India)',
    'how did you find us': 'LinkedIn Ad (India)',
    'how did you come across': 'LinkedIn Ad (India)',
    'heard about': 'LinkedIn Ad (India)',
    # Angular + Microservices Experience
    'exp in angular and microservices': '4 years experience in both Angular and Microservices architecture',
    'exp. in angular': '4 years',
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
    'share your ctc': 'Current CTC: 13.5 LPA, Expected CTC: 24 LPA, Notice Period: 30 Days (Negotiable)',
    'ctc ectc np': 'Current CTC: 13.5 LPA, Expected CTC: 24 LPA, Notice Period: 30 Days (Negotiable)',
    'ctc and np': 'Current CTC: 13.5 LPA, Expected CTC: 24 LPA, Notice Period: 30 Days (Negotiable)',
    'ctc,ectc and np': 'Current CTC: 13.5 LPA, Expected CTC: 24 LPA, Notice Period: 30 Days (Negotiable)',
    # Location-exclusive questions (Mumbai-only, etc.)
    'candidates from mumbai': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    'need candidates from mumbai': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    'from mumbai itself': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    'stay currently in mumbai': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    'andheri mumbai': 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.',
    
    # ========== PHASE 1: MISSING PATTERNS ADDED FOR ROBUSTNESS ==========
    
    # NOTICE PERIOD - Joining Date Variations (20+ patterns)
    'how soon can you join': '30',
    'when can you start': '30',
    'earliest joining date': '30',
    'available from': '30',
    'immediate joining': '30',
    'join by': '30',
    'joining availability': '30',
    'joining date': '30',
    'when are you available': '30',
    'how many days notice': '30',
    'how soon you can join us': '30',
    'how soon can you join us': '30',
    'when can you join': '30',
    'join us': '30',
    'if offered the role, within how many days will you be able to join': '30',
    'within how many days will you be able to join': '30',
    'how many days will you be able to join': '30',
    'able to join': '30',
    'offered the role': '30',
    'how immediate can you join if gets selected': '30',
    'how immediate can you join': '30',
    'immediate can you join': '30',
    'if gets selected': '30',
    'days required for notice': '30 days',
    'notice period buyout': 'Yes, open to buyout discussion',
    'buyout option': 'Yes, can discuss buyout with current employer',
    'negotiable notice': 'Yes, notice period is negotiable',
    'short notice': 'Yes, can negotiate for shorter notice',
    'is your notice period negotiable': 'Yes',
    'can you join earlier': 'Yes, with buyout option',
    'can you join within': 'Yes, can join within 30 days',
    'expected joining date': '30 days from offer acceptance',
    'tentative joining date': '30 days from offer',
    'relieving date': '30 days from resignation',
    'last working day': '30 days from resignation date',
    
    # SALARY - Component Variations (15+ patterns)
    'monthly salary': '112500',
    'monthly ctc': '112500',
    'monthly gross': '1.5',
    'per month salary': '112500',
    'take home': '95000',
    'in hand salary': '95000',
    'take home salary': '95000',
    'fixed component': '1350000',
    'variable component': '0',
    'variable pay': '0',
    'bonus': 'Open to discussion',
    'joining bonus': 'Open to discussion',
    'retention bonus': 'Open to discussion',
    'stock options': 'Open to discussion',
    'esops': 'Open to discussion',
    'equity': 'Open to discussion',
    'benefits': 'Standard benefits as per company policy',
    'gross salary': '13.5 LPA',
    'net salary': '11.5 LPA',
    'remuneration': '13.5 LPA',
    'compensation expectations': '24 LPA',
    'salary bracket': '20-24 LPA',
    'pay range': '20-24 LPA',
    'budget': '20-24 LPA range',
    'ctc breakup': 'Fixed: 13.5 LPA, Variable: 0',
    'salary structure': 'Fixed CTC: 13.5 LPA',
    'currently drawing': '13.5 LPA',
    'current drawn': '13.5 LPA',
    
    # EXPERIENCE - Relevant & Professional Variations (25+ patterns)
    'relevant experience': '3.8 Years',
    'professional experience': '3.8 Years',
    'industry experience': '3.8 Years',
    'corporate experience': '3.8 Years',
    'it experience': '3.8 Years',
    'software development experience': '3.8 Years',
    'hands on experience': '3.8 Years',
    'hands-on experience': '3.8 Years',
    'practical experience': '3.8 Years',
    'exposure': '3.8 Years of hands-on exposure',
    'familiarity': '3.8 Years of familiarity',
    'competency': '3.8 Years of competency',
    'expertise': '3.8 Years of expertise',
    'how long have you been working': '3.8 Years',
    'career span': '3.8 Years',
    'work history': '3.8 Years',
    'employment history': '3.8 Years',
    'total it experience': '3.8 Years',
    'overall it experience': '3.8 Years',
    'relevant years': '3.8 Years',
    'pertinent experience': '3.8 Years',
    'domain experience': '3.8 Years in BFSI domain',
    'field experience': '3.8 Years',
    'sector experience': '3.8 Years',
    
    # Technical Experience - Specific Technologies
    'spring boot experience': '3.8 Years',
    'microservices experience': '3.8 Years',
    'aws experience': '3.8 Years',
    'docker experience': '3.8 Years',
    'kubernetes experience': '3.8 Years',
    'devops experience': '3.8 Years',
    'cloud experience': '3.8 Years',
    'react experience': '4 Years',
    'angular experience': '4 Years',
    'vue experience': '2 Years',
    'node experience': '3.8 Years',
    'python experience': '3.8 Years',
    'java experience': '3.8 Years',
    'javascript experience': '3.8 Years',
    'typescript experience': '3.8 Years',
    
    # LOCATION - Address & Travel Variations (15+ patterns)
    'current address': 'Noida, Uttar Pradesh',
    'permanent address': 'Noida, Uttar Pradesh',
    'residential address': 'Noida, Uttar Pradesh',
    'home town': 'Noida',
    'native place': 'Noida',
    'place of residence': 'Noida',
    'where do you live': 'Noida',
    'base location': 'Noida',
    'onsite': 'Open to onsite opportunities',
    'offshore': 'Yes, can work offshore',
    'client location': 'Open to client location',
    'project location': 'Flexible with project location',
    'site location': 'Flexible',
    'willing to travel': 'Yes',
    'open to travel': 'Yes, open to travel up to 20%',
    'travel': 'Yes, open to travel',
    'relocate to': 'Yes, open to relocation',
    'shift to': 'Yes, can shift to any metro city',
    'move to': 'Yes, willing to move',
    
    # EDUCATION - Academic Background (15+ patterns)
    'highest degree': 'B.Tech Computer Science',
    'academic qualification': 'B.Tech Computer Science',
    'educational background': 'B.Tech in Computer Science from VIT Bhopal University',
    'academic background': 'B.Tech Computer Science',
    'where did you study': 'VIT Bhopal University',
    'institution': 'VIT Bhopal University',
    'completion year': '2022',
    'year of completion': '2022',
    'graduated in': '2022',
    'post graduation': 'Not applicable',
    'pg degree': 'Not applicable',
    'masters': 'Not applicable',
    'bachelors': 'B.Tech Computer Science',
    'undergraduate': 'B.Tech Computer Science',
    '12th percentage': '85',
    '10th percentage': '90',
    'diploma': 'Not applicable',
    'certification': 'AWS Certified, Java Certified',
    'certified in': 'AWS, Java, Spring Boot',
    'course completed': 'B.Tech Computer Science',
    'training': 'Corporate training in Java, React, AWS',
    'internship': 'Completed internships during college',
    
    # SKILLS & PROFICIENCY - Extended (20+ patterns)
    'primary skills': 'Java, Spring Boot, React, AWS',
    'secondary skills': 'Python, Docker, Kubernetes, Node.js',
    'core skills': 'Full Stack Development, Java, React',
    'key expertise': 'Java, Spring Boot, Microservices, React',
    'area of expertise': 'Full Stack Development',
    'specialization': 'Full Stack Development',
    'domain knowledge': 'BFSI, Fintech',
    'primary technology': 'Java, Spring Boot',
    'secondary technology': 'React, Node.js',
    'frameworks known': 'Spring Boot, React, Angular, Express',
    'databases known': 'PostgreSQL, MySQL, MongoDB, Redis',
    'tools familiar': 'Docker, Kubernetes, Jenkins, GitHub Actions',
    'methodologies': 'Agile, Scrum, DevOps',
    'agile experience': 'Yes, 3+ years in Agile environment',
    'scrum experience': 'Yes, experienced with Scrum ceremonies',
    'version control': 'Git, GitHub, GitLab',
    'github experience': 'Yes, 3+ years',
    'git experience': 'Yes, proficient in Git',
    'code review': 'Yes, experienced in code reviews',
    'unit testing': 'Yes, JUnit, Jest, PyTest',
    'integration testing': 'Yes, experienced with integration testing',
    
    # PROFICIENCY RATING - Extended Scales
    'how would you rate yourself': '8 out of 10',
    'self rating': '8',
    'expertise level': 'Advanced',
    'skill level': 'Advanced',
    'competency level': 'Advanced',
    'proficiency level': 'Advanced',
    'mastery': 'Advanced level with 3.8 years experience',
    'comfort level': 'Very comfortable - 8/10',
    'on scale of 1-5': '4',
    'on scale of 1-100': '85',
    'percentage expertise': '85%',
    
    # PERSONAL INFO - Extended (15+ patterns)
    'full name': 'Siddhant Singh',
    'first name': 'Siddhant',
    'last name': 'Singh',
    'middle name': 'Not applicable',
    'emergency contact': '7905828880',
    'alternate number': '7905828880',
    'alternative email': 'siddhant3646@gmail.com',
    'secondary email': 'siddhant3646@gmail.com',
    'personal email': 'siddhant3646@gmail.com',
    'linkedin profile': 'https://www.linkedin.com/in/siddhant3646',
    'github profile': 'https://github.com/siddhant3646',
    'blog': 'https://siddhant3646.github.io/Portfolio/',
    'nationality': 'Indian',
    'country of origin': 'India',
    'visa status': 'Indian citizen - no visa required for India',
    'work permit': 'Not required - Indian citizen',
    'marital status': 'Single',
    'languages known': 'English, Hindi',
    'native language': 'Hindi',
    
    # COMPANY & EMPLOYMENT - Extended (15+ patterns)
    'where do you work': 'Fiserv',
    'where are you working': 'Fiserv',
    'which company': 'Fiserv',
    'present organization': 'Fiserv',
    'reporting to': 'Senior Engineering Manager',
    'reporting manager': 'Senior Engineering Manager',
    'hr contact': 'Will provide upon request',
    'hr name': 'Will provide upon request',
    'manager name': 'Will provide upon request',
    'supervisor': 'Senior Engineering Manager',
    'department': 'Engineering',
    'team': 'Full Stack Development Team',
    'division': 'Technology',
    'business unit': 'Banking Solutions',
    'vertical': 'Banking and Financial Services',
    
    # INTERVIEW & ASSESSMENT - Extended (15+ patterns)
    'available for': 'Any weekday - flexible timing',
    'free for': 'Any weekday - flexible',
    'convenient time': 'Any slot available',
    'suitable time': 'Flexible with timing',
    'good time': 'Any weekday works',
    'when are you free': 'Any weekday - flexible',
    'book slot': 'Any slot available',
    'fix appointment': 'Any weekday works',
    'interview mode': 'Video call or in-person',
    'video call': 'Yes, comfortable with video interviews',
    'phone call': 'Yes, available for phone screening',
    'in person': 'Yes, available for in-person interviews',
    'technical round': 'Yes, available',
    'hr round': 'Yes, available',
    'manager round': 'Yes, available',
    'panel interview': 'Yes, comfortable with panel interviews',
    'group discussion': 'Yes, can participate',
    'assignment': 'Yes, can take assignments',
    'take home': 'Yes, can complete take-home assignments',
    'live coding': 'Yes, comfortable with live coding',
    
    # JOB CHANGE & AVAILABILITY - Extended (10+ patterns)
    'why leaving': 'Seeking new challenges and growth opportunities',
    'why change': 'Career growth and new challenges',
    'motivation': 'Professional growth and skill development',
    'career goal': 'To become a Technical Lead in 2-3 years',
    'aspiration': 'To work on challenging full-stack projects',
    'objective': 'To contribute to innovative products',
    'where do you see yourself': 'Technical Lead/Architect in 3-5 years',
    '5 year plan': 'Grow into Technical Lead/Architect role',
    'short term goal': 'Contribute effectively to the team',
    'long term goal': 'Technical leadership and architecture',
    'immediate joiner': '30',
    'can join immediately': '30',
    'how soon': '30',
    'urgent requirement': '30',
    'immediate opening': '30',
    'immediate requirement': '30',
    'asap': '30',
    'as soon as possible': '30',
    
    # REFERRAL & SOURCE - Extended (12+ patterns)
    'how did you hear': 'LinkedIn',
    'source of application': 'LinkedIn Job Portal',
    'where did you find': 'LinkedIn',
    'who referred you': 'Self-applied via LinkedIn',
    'referral name': 'Self-applied',
    'referral code': 'Not applicable - self applied',
    'reference': 'Will provide upon request',
    'recommended by': 'Self-applied',
    'suggested by': 'Self-applied via LinkedIn',
    'internal referral': 'No',
    'friend referral': 'No',
    'colleague referral': 'No',
    'job portal': 'LinkedIn',
    'consultancy': 'Direct application',
    'recruiter': 'Direct application',
    'agency': 'Direct application',
    'vendor': 'Direct application',
    
    # DIVERSITY & EEO - Extended (10+ patterns)
    'disability accommodation': 'Not required',
    'special needs': 'Not applicable',
    'lgbtq': 'Decline to self-identify',
    'pronouns': 'Decline to self-identify',
    'gender identity': 'Male',
    'ethnic background': 'Decline to self-identify',
    'racial identity': 'Decline to self-identify',
    'minority status': 'Decline to self-identify',
    'protected class': 'Decline to self-identify',
    'equal opportunity': 'Decline to self-identify',
    'affirmative action': 'Decline to self-identify',
    'military service': 'No military service',
    'reserve': 'Not applicable',
    'national guard': 'Not applicable',
    'spouse': 'Not applicable',
    'dependent': 'Not applicable',
    'family status': 'Decline to self-identify',
    
    # CONTRACT & DURATION - Extended (15+ patterns)
    'contract duration': 'Open to both permanent and contract',
    'project duration': 'Flexible with project duration',
    'engagement length': 'Open to long-term engagements',
    'tenure': 'Looking for long-term opportunity',
    'assignment length': 'Flexible',
    'period': 'Open to any period',
    'timeframe': 'Flexible with timeframe',
    '6 months': 'Open to 6 month contracts',
    '1 year': 'Open to 1 year contracts',
    '2 years': 'Open to 2 year contracts',
    'contract type': 'Open to both C2H and permanent',
    'employment type': 'Full-time preferred',
    'full time': 'Yes, looking for full-time',
    'part time': 'No, looking for full-time only',
    'freelance': 'No, looking for full-time employment',
    'consultant': 'Open to consulting roles',
    'third party': 'No',
    'vendor': 'No',
    'payroll': 'Direct payroll preferred',
    'direct hire': 'Yes, preferred',
    'permanent': 'Yes, looking for permanent role',
    'temporary': 'Open to temporary assignments',
    
    # AVAILABILITY & SCHEDULING - Additional
    'flexible with dates': 'Yes, flexible with dates and times',
    'flexible with timing': 'Yes, flexible with timing',
    'weekdays': 'Yes, available on weekdays',
    'weekends': 'If necessary, available on weekends',
    'working days': 'Yes, available on working days',
    'calendar': 'Can schedule anytime as per mutual convenience',
    'schedule interview': 'Yes, please share available slots',
    'interview slot': 'Any slot works - flexible',
    'availability': '30',
    'available immediately': '30',
    'how early can you join': '30',
    'earliest': '30',
    
    # ADDITIONAL LINKEDIN SPECIFIC
    'linkedin specific': 'Applying via LinkedIn Easy Apply',
    'easy apply': 'Yes, via LinkedIn Easy Apply',
    'linkedin job': 'Found on LinkedIn',
    'job id': 'Found via LinkedIn',
    
    # SALARY NEGOTIATION - Only used when explicitly asked about negotiation/flexibility
    'negotiable': 'Yes, open to negotiation within range',
    'open to negotiation': 'Yes, can discuss compensation',
    'salary negotiable': 'Yes, within reasonable range',
    'negotiation': 'Yes, open to discussion',
    'discuss salary': 'Yes, willing to discuss',
    'salary discussion': 'Yes, open to discussion',
    'range': '20-24 LPA',
    'flexible on salary': 'Yes, flexible within reason',
    
    # MISCELLANEOUS - Yes/No Questions
    'ready to relocate': 'Yes',
    'comfortable to relocate': 'Yes',
    'ok to relocate': 'Yes',
    'fine with relocation': 'Yes',
    'accept relocation': 'Yes',
    'willingness to relocate': 'Yes',
    'ready to travel': 'Yes',
    'comfortable to travel': 'Yes',
    'ok to travel': 'Yes',
    'fine with travel': 'Yes',
    'accept travel': 'Yes',
    'willingness to travel': 'Yes',
    
    # ========== COMPREHENSIVE PATTERN EXPANSION - 200+ NEW PATTERNS ==========
    
    # SECTION 1: LINKEDIN "PLEASE SELECT/ENTER..." PATTERNS (30 patterns)
    # LinkedIn Easy Apply specific dropdown and text input patterns
    'please select your notice period with your current employer': '30 days',
    'please select your highest education qualification': 'Bachelor\'s Degree',
    'please select your total years of professional experience': '4',
    'please select your total additional months of experience': '0',
    'please select your current work authorization status': 'Authorized to work in India',
    'please select your preferred location': 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune',
    'please select your current location': 'Noida',
    'please select your notice period': '30 days',
    'please select your experience': '4',
    'please select your salary expectation': '24 LPA',
    
    'please enter your annual current ctc in inr': '1350000',
    'please enter your annual expected ctc in inr': '2400000',
    'please enter your current ctc in inr': '1350000',
    'please enter your expected ctc in inr': '2400000',
    'please enter your online portfolio url': 'https://siddhant3646.github.io/Portfolio/',
    'please enter your notice period in days': '30',
    'please enter your linkedin profile': 'https://www.linkedin.com/in/siddhant3646',
    'please enter your github url': 'https://github.com/siddhant3646',
    'please enter your current salary': '13.5 LPA',
    'please enter your expected salary': '24 LPA',
    'please enter your phone number': '7905828880',
    'please enter your email address': 'siddhant3646@gmail.com',
    'please enter your full name': 'Siddhant Singh',
    'please enter your current company': 'Fiserv',
    'please enter your current designation': 'SDE-2 Full Stack Developer',
    'please enter your total experience': '4',
    'please enter your years of experience': '4',
    'please enter your ctc': '13.5 LPA',
    'please enter your salary': '13.5 LPA',
    
    'please share your ctc ectc and notice period': 'Current CTC: 13.5 LPA, Expected CTC: 24 LPA, Notice Period: 30 Days',
    'please provide your ctc details': 'Current: 13.5 LPA, Expected: 24 LPA',
    'please mention your notice period': '30 days',
    'please specify your experience': '4 years',
    
    # SECTION 2: SHORT FORM QUESTIONS (25 patterns)
    # Concise variations for quick matching
    'current ctc': '13.5 LPA',
    'expected ctc': '24 LPA',
    'current salary': '13.5 LPA',
    'expected salary': '24 LPA',
    'ctc': '13.5 LPA',
    'salary': '13.5 LPA',
    'pay': '13.5 LPA',
    'compensation': '13.5 LPA',
    
    'total years of exp': '3.8 Years',
    'total exp': '3.8 Years',
    'overall exp': '3.8 Years',
    'years of exp': '3.8 Years',
    'exp': '3.8 Years',
    'experience': '3.8 Years',
    'years': '3.8 Years',
    
    'notice': '30 days',
    'np': '30',
    'notice period': '30 days',
    'joining': '30 days',
    'availability': '30 days',
    
    'location': 'Noida',
    'city': 'Noida',
    'current location': 'Noida',
    'preferred location': 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune',
    'current city': 'Noida',
    
    # SECTION 3: TECHNOLOGY EXPERIENCE - ALL TECHNOLOGIES (60 patterns)
    # Format: "How many years of work experience do you have with {tech}"
    # LinkedIn: 4, Naukri: 3.8 Years (handled by platform detection in code)
    'how many years of work experience do you have with docker': '4',
    'how many years of work experience do you have with kubernetes': '4',
    'how many years of work experience do you have with aws': '4',
    'how many years of work experience do you have with amazon web services': '4',
    'how many years of work experience do you have with azure': '4',
    'how many years of work experience do you have with microsoft azure': '4',
    'how many years of work experience do you have with gcp': '4',
    'how many years of work experience do you have with google cloud': '4',
    'how many years of work experience do you have with react': '4',
    'how many years of work experience do you have with reactjs': '4',
    'how many years of work experience do you have with react.js': '4',
    'how many years of work experience do you have with angular': '4',
    'how many years of work experience do you have with angularjs': '4',
    'how many years of work experience do you have with vue': '4',
    'how many years of work experience do you have with vuejs': '4',
    'how many years of work experience do you have with vue.js': '4',
    'how many years of work experience do you have with node': '4',
    'how many years of work experience do you have with nodejs': '4',
    'how many years of work experience do you have with node.js': '4',
    'how many years of work experience do you have with python': '4',
    'how many years of work experience do you have with java': '4',
    'how many years of work experience do you have with spring': '4',
    'how many years of work experience do you have with spring boot': '4',
    'how many years of work experience do you have with springboot': '4',
    'how many years of work experience do you have with hibernate': '4',
    'how many years of work experience do you have with javascript': '4',
    'how many years of work experience do you have with js': '4',
    'how many years of work experience do you have with typescript': '4',
    'how many years of work experience do you have with ts': '4',
    'how many years of work experience do you have with html': '4',
    'how many years of work experience do you have with html5': '4',
    'how many years of work experience do you have with css': '4',
    'how many years of work experience do you have with css3': '4',
    'how many years of work experience do you have with sql': '4',
    'how many years of work experience do you have with postgresql': '4',
    'how many years of work experience do you have with postgres': '4',
    'how many years of work experience do you have with mysql': '4',
    'how many years of work experience do you have with mongodb': '4',
    'how many years of work experience do you have with mongo': '4',
    'how many years of work experience do you have with redis': '4',
    'how many years of work experience do you have with kafka': '4',
    'how many years of work experience do you have with rabbitmq': '4',
    'how many years of work experience do you have with elasticsearch': '4',
    'how many years of work experience do you have with git': '4',
    'how many years of work experience do you have with github': '4',
    'how many years of work experience do you have with gitlab': '4',
    'how many years of work experience do you have with jenkins': '4',
    'how many years of work experience do you have with github actions': '4',
    'how many years of work experience do you have with terraform': '4',
    'how many years of work experience do you have with ansible': '4',
    'how many years of work experience do you have with prometheus': '4',
    'how many years of work experience do you have with grafana': '4',
    'how many years of work experience do you have with microservices': '4',
    'how many years of work experience do you have with rest api': '4',
    'how many years of work experience do you have with restful api': '4',
    'how many years of work experience do you have with graphql': '4',
    'how many years of work experience do you have with websockets': '4',
    'how many years of work experience do you have with web services': '4',
    'how many years of work experience do you have with soap': '4',
    'how many years of work experience do you have with xml': '4',
    'how many years of work experience do you have with json': '4',
    'how many years of work experience do you have with problem solving': '4',
    
    # Format: "How many years into {tech}"
    'how many years into angular': '4',
    'how many years into java': '4',
    'how many years into spring boot': '4',
    'how many years into react': '4',
    'how many years into python': '4',
    'how many years into docker': '4',
    'how many years into aws': '4',
    'how many years into javascript': '4',
    'how many years into node': '4',
    'how many years into full stack': '4',
    
    # SECTION 4: SCREENING & ASSESSMENT (35 patterns)
    'are you ready to take beribot assessment': 'Yes',
    'are you ready to take assessment': 'Yes',
    'are you available for assessment': 'Yes',
    'can you take technical assessment': 'Yes',
    'are you willing to take coding test': 'Yes',
    'are you ready for assessment': 'Yes',
    'ready for assessment': 'Yes',
    'available for assessment': 'Yes',
    'willing to take assessment': 'Yes',
    
    'are you comfortable with wfo setup': 'Yes',
    'are you comfortable working from office': 'Yes',
    'are you comfortable with work from office': 'Yes',
    'are you comfortable commuting to this job location': 'Yes',
    'are you comfortable with hybrid work': 'Yes',
    'are you comfortable with remote work': 'Yes',
    'comfortable with wfo': 'Yes',
    'comfortable with work from office': 'Yes',
    'comfortable commuting': 'Yes',
    'comfortable with hybrid': 'Yes',
    'comfortable with remote': 'Yes',
    
    'are you a full-stack java developer': 'Yes',
    'are you a full stack developer': 'Yes',
    'are you a fullstack developer': 'Yes',
    'are you a java developer': 'Yes',
    'are you a backend developer': 'Yes',
    'are you a frontend developer': 'Yes',
    'are you a software engineer': 'Yes',
    'are you a sde': 'Yes',
    'are you a developer': 'Yes',
    'full-stack developer': 'Yes',
    'full stack developer': 'Yes',
    'java developer': 'Yes',
    'backend developer': 'Yes',
    'frontend developer': 'Yes',
    
    'do you have minimum 3+ years of experience as full stack engineer': 'Yes',
    'do you have minimum 3 years of experience': 'Yes',
    'do you have 3+ years of experience': 'Yes',
    'do you have 3 years of experience': 'Yes',
    'do you have 4 years of experience': 'Yes',
    'do you have experience with the above-mentioned tech stack': 'Yes',
    'do you have experience with the mentioned tech stack': 'Yes',
    'do you have 3+ years of experience in dsa and system design': 'Yes',
    'do you have experience with dsa': 'Yes',
    'do you have experience with system design': 'Yes',
    'do you have experience with data structures': 'Yes',
    'do you have experience with algorithms': 'Yes',
    'minimum 3 years experience': 'Yes',
    'minimum 4 years experience': 'Yes',
    
    'do you have experience with spring boot': 'Yes',
    'do you have experience with microservices': 'Yes',
    'do you have experience with react': 'Yes',
    'do you have experience with angular': 'Yes',
    'do you have experience with aws': 'Yes',
    'do you have experience with docker': 'Yes',
    'do you have experience with kubernetes': 'Yes',
    'do you have experience with java': 'Yes',
    'do you have experience with python': 'Yes',
    'do you have experience with javascript': 'Yes',
    
    # SECTION 5: PRIVACY & LEGAL (20 patterns)
    'you declare that you read and agree to the privacy policy': 'Yes',
    'you declare that you have read and agree to the privacy notice': 'Yes',
    'you declare that you have read and agree to the privacy notice of miratech': 'Yes',
    'privacy notice consent': 'Yes',
    'i have read and agree to the privacy policy': 'Yes',
    'i agree to the privacy policy': 'Yes',
    'do you agree to the privacy policy': 'Yes',
    'privacy policy agreement': 'Yes',
    'agree to privacy policy': 'Yes',
    'read privacy policy': 'Yes',
    'accept privacy policy': 'Yes',
    
    # Job Applicant Data Privacy Notice (dropdown selection - "Acknowledge")
    'job applicant data privacy notice': 'Acknowledge',
    'data privacy notice': 'Acknowledge',
    'applicant data privacy notice': 'Acknowledge',
    'applicant privacy notice': 'Acknowledge',
    
    # Client/Partner/Competitor employment questions → always "No"
    'are you currently employed by a client, partner, or competitor': 'No',
    'currently employed by a client, partner, or competitor': 'No',
    'employed by a client, partner, or competitor': 'No',
    'client, partner, or competitor': 'No',
    'client partner or competitor': 'No',
    'employed by a client or competitor': 'No',
    'work for a competitor': 'No',
    'employed by a competitor': 'No',
    
    # Open to relocate to [city] → always "Yes"
    'are you currently in pune or open to relocate to pune': 'Yes',
    'open to relocate to pune': 'Yes',
    'pune for this role': 'Yes',
    'are you currently in bangalore or open to relocate to bangalore': 'Yes',
    'open to relocate to bangalore': 'Yes',
    'are you currently in mumbai or open to relocate to mumbai': 'Yes',
    'open to relocate to mumbai': 'Yes',
    'are you currently in delhi or open to relocate to delhi': 'Yes',
    'open to relocate to delhi': 'Yes',
    'are you currently in hyderabad or open to relocate to hyderabad': 'Yes',
    'open to relocate to hyderabad': 'Yes',
    'are you currently in noida or open to relocate to noida': 'Yes',
    'open to relocate to noida': 'Yes',
    'are you currently in gurgaon or open to relocate to gurgaon': 'Yes',
    'open to relocate to gurgaon': 'Yes',
    'are you currently in chennai or open to relocate to chennai': 'Yes',
    'open to relocate to chennai': 'Yes',
    'open to relocate': 'Yes',
    'are you open to relocate': 'Yes',
    'willing to relocate for this role': 'Yes',
    'i certify that to the best of my knowledge the information contained in this application is correct': 'Yes',
    'i certify that all information provided is correct': 'Yes',
    'i confirm that all details are accurate': 'Yes',
    'information is correct': 'Yes',
    'all information correct': 'Yes',
    'certify information correct': 'Yes',
    
    'are you willing to undergo background verification': 'Yes',
    'do you consent to background check': 'Yes',
    'are you ok with background verification': 'Yes',
    'background check consent': 'Yes',
    'willing for background check': 'Yes',
    
    'do you consent to data processing': 'Yes',
    'do you agree to data collection': 'Yes',
    'do you consent to storage of personal data': 'Yes',
    'data consent': 'Yes',
    'consent to data processing': 'Yes',
    
    'all applicants are invited to complete this section': 'Yes',
    'i consent to equal opportunity monitoring': 'Yes',
    'equal opportunity consent': 'Yes',
    
    # SECTION 6: OPEN-ENDED / COVER LETTER (15 patterns)
    'what about this role makes it a good fit for you': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team. I am particularly interested in working on challenging projects and contributing to innovative solutions.',
    
    'why do you want to work here': 'I am excited about this opportunity and believe my skills align well with the role requirements. I am looking for a challenging environment where I can grow professionally.',
    
    'why do you want to join our company': 'I am impressed by your company\'s innovative work and believe my skills would be a great fit. I am looking for opportunities to contribute to meaningful projects.',
    
    'why are you interested in this position': 'This position aligns perfectly with my skills and career goals. I am excited about the opportunity to contribute to your team.',
    
    'what interests you about this role': 'The opportunity to work on challenging full-stack projects and contribute to innovative solutions interests me greatly.',
    
    'why should we hire you': 'With 3.8+ years of full-stack development experience in Java, Spring Boot, React, and AWS, I bring strong technical skills and a track record of delivering quality solutions.',
    
    'tell us about yourself': 'I am a Full Stack Developer with 3.8+ years of experience in Java, Spring Boot, React, and AWS. I am passionate about building scalable applications and continuously improving my skills.',
    
    'describe your experience': 'I have 3.8+ years of experience as a Full Stack Developer, working with Java, Spring Boot, React, and AWS. I have built scalable applications and microservices architectures.',
    
    'what are your strengths': 'My strengths include strong problem-solving abilities, proficiency in full-stack development, and experience with modern technologies like Java, React, and AWS.',
    
    'what are your career goals': 'My career goal is to grow into a Technical Lead role where I can mentor junior developers and architect scalable solutions.',
    
    'where do you see yourself in 5 years': 'In 5 years, I see myself as a Technical Lead, architecting solutions and mentoring a team of developers.',
    
    'what motivates you': 'I am motivated by challenging problems, continuous learning, and the opportunity to build products that make a difference.',
    
    'what are you passionate about': 'I am passionate about building scalable applications, learning new technologies, and solving complex technical challenges.',
    
    'cover letter': 'I am excited about this opportunity and believe my 3.8+ years of full-stack development experience with Java, Spring Boot, React, and AWS would be valuable to your team.',
    
    'additional comments': 'I am excited about this opportunity and believe my skills align well with the role requirements.',
    
    # SECTION 7: SALARY VARIATIONS (25 patterns)
    'what is your current monthly salary': '112500',
    'current monthly salary': '112500',
    'expected monthly salary': '166667',
    'monthly pay': '112500',
    'monthly income': '112500',
    'monthly compensation': '112500',
    
    'what is your fixed ctc': '1350000',
    'what is your variable pay': '0',
    'what is your bonus': '0',
    'fixed pay': '1350000',
    'variable component': '0',
    'bonus component': '0',
    
    'please enter your salary': '13.5 LPA',
    'please share your salary details': 'Current: 13.5 LPA, Expected: 24 LPA',
    'salary requirements': '24 LPA',
    'compensation requirements': '24 LPA',
    'pay expectations': '24 LPA',
    'expected remuneration': '24 LPA',
    'salary expectation': '24 LPA',
    'compensation expectation': '24 LPA',
    
    'ctc details': 'Current: 13.5 LPA, Expected: 24 LPA',
    'salary details': 'Current: 13.5 LPA, Expected: 24 LPA',
    'compensation details': 'Current: 13.5 LPA, Expected: 24 LPA',
    'provide salary details': 'Current: 13.5 LPA, Expected: 24 LPA',
    'share compensation details': 'Current: 13.5 LPA, Expected: 24 LPA',
    
    # SECTION 8: EXPERIENCE VARIATIONS (20 patterns)
    'years into java': '4',
    'years into spring boot': '4',
    'years into react': '4',
    'years into angular': '4',
    'years into python': '4',
    'years into docker': '4',
    'years into aws': '4',
    'years into javascript': '4',
    'years into node': '4',
    'years into full stack': '4',
    
    'total years': '3.8 Years',
    'total years of experience': '3.8 Years',
    'total professional experience': '3.8 Years',
    'overall years of experience': '3.8 Years',
    'overall professional experience': '3.8 Years',
    
    'overall how many years of working experience do you have': '3.8 Years',
    'how many years of working experience do you have': '3.8 Years',
    'years of working experience': '3.8 Years',
    'working experience': '3.8 Years',
    'professional working experience': '3.8 Years',
    
    'relevant years of experience': '3.8 Years',
    'professional years of experience': '3.8 Years',
    'years of professional experience': '3.8 Years',
    'years of relevant experience': '3.8 Years',
    'relevant professional experience': '3.8 Years',
    
    # SECTION 9: ADDITIONAL LINKEDIN SPECIFIC (25 patterns)
    'linkedin profile': 'https://www.linkedin.com/in/siddhant3646',
    'github profile': 'https://github.com/siddhant3646',
    'portfolio url': 'https://siddhant3646.github.io/Portfolio/',
    'website': 'https://siddhant3646.github.io/Portfolio/',
    'personal website': 'https://siddhant3646.github.io/Portfolio/',
    'online portfolio': 'https://siddhant3646.github.io/Portfolio/',
    'portfolio link': 'https://siddhant3646.github.io/Portfolio/',
    
    'how did you hear about us': 'LinkedIn',
    'source': 'LinkedIn',
    'referral source': 'LinkedIn',
    'how did you find us': 'LinkedIn',
    'where did you hear': 'LinkedIn',
    
    'have you worked with nielsen in the past': 'No',
    'worked with nielsen': 'No',
    'previous nielsen employee': 'No',
    'nielsen experience': 'No',
    
    'are you legally authorized to work in the country': 'Yes',
    'authorized to work in country': 'Yes',
    'work authorization status': 'Authorized to work in India',
    'legally authorized to work': 'Yes',
    
    'willing to relocate': 'Yes',
    'open to relocate': 'Yes',
    'ready to relocate': 'Yes',
    'comfortable relocating': 'Yes',
    'ok with relocation': 'Yes',
    
    # SECTION 10: MISSING TECH STACK PATTERNS (15 patterns)
    'java spring boot angular sql rest git maven': '4',
    'spring boot angular sql rest git': '4',
    'java spring boot react': '4',
    'full stack java react': '4',
    'java python javascript': '4',
    'spring boot microservices': '4',
    'react angular vue': '4',
    'docker kubernetes aws': '4',
    'frontend backend database': '4',
    'html css javascript': '4',
    'rest api graphql': '4',
    'sql nosql': '4',
    'mysql postgresql mongodb': '4',
    'jenkins github actions': '4',
    'terraform ansible': '4',
}

FUZZY_MATCH_THRESHOLD = 0.7  # Increased from 0.6 for better accuracy
FUZZY_MATCH_THRESHOLD_FALLBACK = 0.6  # For category fallback only


class SentinelAgent:
    """
    Sentinel Agent - 100% Scripted Browser Automation.
    Operates on DOM to control a browser without LLM calls.
    """
    
    MAX_STEPS_LINKEDIN = 120  # LinkedIn tasks get more steps
    MAX_STEPS_DEFAULT = 120   # All other tasks (Naukri, etc.)
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
        self._linkedin_scroll_attempted = False  # Track if we tried scrolling for null cards
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
        
        # NEW: Input-aware resolver and self-healing components
        self._input_resolver = InputAwareResolver()
        self._self_healing = SelfHealingMatcher()
        self._pattern_learner = PatternLearner()
        self._error_detector = None  # Initialized when page is available
        self._error_recovery = None
        
        # Ensure screenshot directory exists
        os.makedirs(self.SCREENSHOT_DIR, exist_ok=True)
    
    def _init_error_detection(self):
        """Initialize error detection components when page is available."""
        if self._page:
            from src.sentinel.ui_error_detector import UIErrorDetector, UIErrorRecovery
            self._error_detector = UIErrorDetector(
                page=self._page,
                screenshot_dir=self.SCREENSHOT_DIR
            )
            self._error_recovery = UIErrorRecovery(
                detector=self._error_detector,
                self_healing_matcher=self._self_healing,
                input_resolver=self._input_resolver
            )
    
    def _format_answer_for_field(self, answer: str, question: str, field_type: str = "text") -> str:
        """
        Format answer appropriately for the field type.
        
        Args:
            answer: The raw answer
            question: The question text
            field_type: Type of form field (text, number, email, etc.)
            
        Returns:
            Formatted answer
        """
        import re
        
        question_lower = question.lower()
        
        # Check if field expects numeric input
        expects_number = (
            field_type == "number" or
            "number" in question_lower or
            "decimal" in question_lower or
            "how many" in question_lower or
            "rate your" in question_lower or
            "proficiency" in question_lower or
            "confidence" in question_lower or
            "years of" in question_lower or
            "experience" in question_lower
        )
        
        if expects_number:
            # Extract numeric value from answer
            # Handle cases like "3.8 Years" -> "3.8", "8 out of 10" -> "8"
            match = re.search(r'(\d+\.?\d*)', answer)
            if match:
                numeric = match.group(1)
                # Validate it's a reasonable number
                try:
                    val = float(numeric)
                    if val > 0:
                        return numeric
                except:
                    pass
        
        # Check if field expects yes/no
        if "yes" in answer.lower() or "no" in answer.lower():
            # Check if this is actually a yes/no question
            is_yes_no_question = any(kw in question_lower for kw in [
                "would you", "are you", "do you", "can you", "will you",
                "is this", "have you", "agree", "accept", "confirm"
            ])
            
            if not is_yes_no_question and expects_number:
                # This shouldn't be yes/no, extract number instead
                # Default to 8 for ratings/confidence
                if "proficiency" in question_lower or "confidence" in question_lower or "rate" in question_lower:
                    return "8"
        
        return answer

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

    def _detect_negation(self, question: str) -> bool:
        """Detect if question contains negation words."""
        negation_words = ['not', 'no', "n't", 'never', 'without', 'except', 'apart from', 'cannot', "can't", "won't", 'refuse', 'decline']
        question_lower = question.lower()
        return any(word in question_lower for word in negation_words)
    
    def _word_set_similarity(self, q1: str, q2: str) -> float:
        """Calculate Jaccard similarity between word sets."""
        words1 = set(q1.lower().split())
        words2 = set(q2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)
    
    def _position_similarity(self, q1: str, q2: str) -> float:
        """Calculate position-aware similarity combining sequence and word-set matching."""
        seq_sim = SequenceMatcher(None, q1, q2).ratio()
        word_sim = self._word_set_similarity(q1, q2)
        return 0.6 * seq_sim + 0.4 * word_sim
    
    def _same_keyword_category(self, q1: str, q2: str) -> bool:
        """Check if two questions belong to the same keyword category."""
        salary_keywords = ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc']
        experience_keywords = ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp']
        notice_keywords = ['notice', 'serving', 'join', 'availability']
        location_keywords = ['location', 'city', 'relocate', 'preferred location']
        
        q1_lower = q1.lower()
        q2_lower = q2.lower()
        
        categories = [salary_keywords, experience_keywords, notice_keywords, location_keywords]
        for category in categories:
            q1_in_cat = any(kw in q1_lower for kw in category)
            q2_in_cat = any(kw in q2_lower for kw in category)
            if q1_in_cat and q2_in_cat:
                return True
        return False

    def _fuzzy_match_question(self, question: str) -> Tuple[Optional[str], float]:
        """Find closest known question pattern using improved keyword + fuzzy matching."""
        # Update platform detection before processing
        self._current_platform = self._detect_platform()
        
        question_lower = question.lower().strip()
        question_negated = self._detect_negation(question_lower)
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
        # PHASE 0.6: Learned Pattern Matching
        # Check self-healing and pattern learner
        # ==========================================
        learned = self._get_learned_answer(question)
        if learned and learned[1] >= 0.5:
            print(f"   📚 Learned pattern match (conf: {learned[1]:.2f}): {learned[0][:50]}...")
            return learned
        
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
        
        # ==========================================
        # COMPLIANCE & EMPLOYMENT HISTORY DETECTION
        # These questions MUST return "No" for compliance safety
        # ==========================================
        
        # Pattern 1: "Have you worked with/at/for [Company]" - Most common Workday pattern
        worked_with_company_pattern = r"have\s+you\s+(?:worked|been\s+employed)\s+(?:with|for|at|in)\s+(?:the\s+)?(?:past\s+)?(?:\d+\s+years?\s+)?at\s+(\w+)"
        worked_with_match = re.search(worked_with_company_pattern, question_lower)
        if worked_with_match:
            company = worked_with_match.group(1).lower()
            # Only answer "Yes" for current employer, "No" for all others
            if company == 'fiserv':
                return 'Yes', 0.98
            return 'No', 0.98
        
        # Pattern 2: "Have you worked with [Company] in the past X years"
        past_years_pattern = r"have\s+you\s+(?:worked|been\s+employed)\s+(?:with|for|at)\s+(\w+)\s+(?:in\s+the\s+)?(?:past|last)\s+(\d+)"
        past_years_match = re.search(past_years_pattern, question_lower)
        if past_years_match:
            company = past_years_match.group(1).lower()
            if company == 'fiserv':
                return 'Yes', 0.98
            return 'No', 0.98
        
        # Pattern 3: "Have you worked with Visa" or similar specific company questions
        specific_company_pattern = r"have\s+you\s+(?:worked|been\s+employed)\s+(?:with|for|at)\s+(\w+)(?:\s+in\s+the\s+)?"
        specific_company_match = re.search(specific_company_pattern, question_lower)
        if specific_company_match:
            company = specific_company_match.group(1).lower()
            if company == 'fiserv':
                return 'Yes', 0.98
            # For Visa and other companies, return "No"
            return 'No', 0.98
        
        # Pattern 4: "Currently employed by any of the" - blanket No
        currently_employed_pattern = r"currently\s+(?:employed|an\s+employee)\s+(?:by|at|of)\s+(?:any|any\s+of\s+the)"
        if re.search(currently_employed_pattern, question_lower):
            return 'No', 0.98
        
        # Pattern 5: "Ever been employed by" or "Previously employed by"
        ever_employed_pattern = r"(?:ever\s+been\s+employed|previously\s+employed)\s+(?:by|at|with)"
        if re.search(ever_employed_pattern, question_lower):
            # Check if it's asking about Fiserv specifically
            if 'fiserv' in question_lower:
                return 'Yes', 0.98
            return 'No', 0.98
        
        # Pattern 6: "Conflict of interest" or "Family member" questions
        conflict_keywords = ['conflict of interest', 'close relative', 'family member', 
                            'relative working', 'family in company', 'relatives in company']
        is_conflict_question = any(kw in question_lower for kw in conflict_keywords)
        if is_conflict_question:
            return 'No', 0.98
        
        # Pattern 7: "Worked with" + any company name not in whitelist
        # This catches variations like "worked with Navan", "worked for Reed", etc.
        generic_worked_pattern = r"worked\s+(?:with|for|at)\s+(visa|navan|reed|nielsen|mastercard|amex|american\s+express|paypal|stripe)"
        if re.search(generic_worked_pattern, question_lower):
            return 'No', 0.98
        
        # Pattern 8: Company list questions like "Have you worked with any of the following"
        company_list_pattern = r"(?:have\s+you|do\s+you)\s+(?:worked|been)\s+(?:with|for|at|employed)\s+(?:with|for|at)?\s+(?:any\s+of\s+the|any\s+of\s+these|any\s+of\s+the\s+following)"
        if re.search(company_list_pattern, question_lower):
            return 'No', 0.98
        
        # Notice period for current company in days - HIGH PRIORITY to avoid matching company name
        if 'notice period' in question_lower and 'company' in question_lower and ('days' in question_lower or 'in days' in question_lower):
            return '30', 0.99
        
        # Handle high-priority question types FIRST
        
        # Composite HR question (must check BEFORE individual NP/salary)
        if is_composite_hr:
            return 'Current CTC: 13.5 LPA, Expected CTC: 24 LPA, Notice Period: 30 Days (Negotiable)', 0.98
        
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
                return '13.5', 0.98
            if 'ectc' in question_lower:
                return '24', 0.98
            
            # Check for expected vs current - use plain numbers
            if 'expected' in question_lower or 'expect' in question_lower:
                return '24', 0.95
            elif 'current' in question_lower or 'present' in question_lower:
                return '13.5', 0.95
            # Default to expected if unclear
            return '24', 0.90
        
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
            # Platform-specific experience format
            if self._current_platform == 'linkedin':
                return '4', 0.95
            else:
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
            else:
                # Generic notice period question
                # LinkedIn: just number, Naukri: include LWD and full text
                if self._current_platform == 'linkedin':
                    return '30', 0.95
                elif self._current_platform == 'naukri':
                    lwd_date = datetime.now() + timedelta(days=30)
                    lwd_formatted = lwd_date.strftime('%d %B %Y')
                    return f'30 days (LWD: {lwd_formatted})', 0.95
                else:
                    return '30 days', 0.95
        
        if is_location_question:
            if 'preferred' in question_lower:
                return KNOWN_QA_PATTERNS.get('preferred location', 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune'), 0.95
            return KNOWN_QA_PATTERNS.get('current location', 'Noida'), 0.95
        
        # ==========================================
        # PHASE 2: Fuzzy Matching for Other Questions
        # Enhanced with negation detection, word-set similarity, and position-aware scoring
        # ==========================================
        for pattern, answer in KNOWN_QA_PATTERNS.items():
            pattern_lower = pattern.lower()
            
            # Check for negation mismatch - penalize if one is negated and other is not
            pattern_negated = self._detect_negation(pattern_lower)
            negation_penalty = 0.2 if (question_negated != pattern_negated) else 0.0
            
            # Calculate position-aware similarity (combines sequence and word-set matching)
            score = self._position_similarity(question_lower, pattern_lower)
            
            # Boost score if pattern is contained in question (strong signal)
            if pattern_lower in question_lower:
                score = max(score, 0.95)
            
            # Boost if all words in pattern are found in question (order-independent)
            pattern_words = pattern_lower.split()
            if len(pattern_words) > 1 and all(word in question_lower for word in pattern_words):
                score = max(score, 0.90)
            
            # Boost for same keyword category (salary, experience, etc.)
            if self._same_keyword_category(question_lower, pattern_lower):
                score = min(score + 0.05, 1.0)
            
            # Apply negation penalty
            score = max(score - negation_penalty, 0.0)
            
            if score > best_score:
                best_score = score
                best_match = answer
        
        # Use higher threshold for direct fuzzy matches
        if best_score >= FUZZY_MATCH_THRESHOLD and best_match is not None:
            # Validate and potentially fix the answer
            validated_answer, final_confidence = self._validate_and_retry(
                question, best_match, []
            )
            return validated_answer, final_confidence
        
        # ==========================================
        # PHASE 3: Smart Category Fallback
        # Use question classifier for intelligent defaults
        # ==========================================
        if self._question_classifier is None:
            self._question_classifier = QuestionClassifier(self._current_platform)
        
        category, cat_confidence = self._question_classifier.classify(question)
        
        # Use lower threshold for category fallback
        if category != QuestionCategory.UNKNOWN and cat_confidence >= 0.4:
            # Get platform-specific answer
            answer, ans_confidence = self._question_classifier.get_answer(question, category)
            if answer:
                combined_confidence = max(best_score, cat_confidence * 0.8)  # Slightly lower confidence for fallback
                print(f"   🤖 Smart fallback [{category.value}]: {answer[:50]}...")
                return answer, combined_confidence
        
        return None, best_score

    def _validate_and_retry(self, question: str, answer: str, 
                           validation_errors: List[str] = None) -> Tuple[str, float]:
        """
        Validate an answer and attempt to fix it if validation fails.
        
        Args:
            question: The original question
            answer: The proposed answer
            validation_errors: List of validation error messages
            
        Returns:
            Tuple of (fixed_answer, confidence_score)
        """
        if validation_errors is None:
            validation_errors = []
        
        try:
            # Detect expected format from question
            format_type = detect_expected_format(question)
            if not format_type:
                return answer, 0.95  # No validation needed
            
            # Validate the answer
            is_valid, error_msg = validate_answer(answer, format_type)
            if is_valid:
                return answer, 0.95
            
            # Attempt to fix the answer based on format type
            fixed_answer = answer
            confidence = 0.85  # Lower confidence for fixed answers
            
            if format_type == 'numeric':
                # Extract numbers from answer
                import re
                numbers = re.findall(r'\d+\.?\d*', answer.replace(',', ''))
                if numbers:
                    fixed_answer = numbers[0]
                    print(f"   🔧 Fixed numeric answer: {answer} -> {fixed_answer}")
            
            elif format_type == 'salary_lpa':
                # Extract numeric part only (no LPA suffix for LinkedIn)
                import re
                match = re.search(r'(\d+\.?\d*)', answer)
                if match:
                    fixed_answer = match.group(1)
                    print(f"   🔧 Fixed salary answer: {answer} -> {fixed_answer}")
            
            elif format_type == 'salary_inr':
                # Convert to INR format (remove decimals, ensure numeric)
                import re
                numbers = re.findall(r'\d+', answer.replace(',', ''))
                if numbers:
                    fixed_answer = ''.join(numbers)
                    print(f"   🔧 Fixed INR salary: {answer} -> {fixed_answer}")
            
            elif format_type == 'experience_years':
                # Extract years, add "Years" suffix if missing
                import re
                match = re.search(r'(\d+\.?\d*)', answer)
                if match:
                    years = float(match.group(1))
                    if 'month' in question.lower():
                        fixed_answer = str(int(years * 12))
                    else:
                        fixed_answer = f"{years} Years"
                    print(f"   🔧 Fixed experience: {answer} -> {fixed_answer}")
            
            elif format_type == 'date':
                # Try to parse and format date
                from datetime import datetime
                try:
                    # Try various date formats
                    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d %B %Y']:
                        try:
                            dt = datetime.strptime(answer, fmt)
                            fixed_answer = dt.strftime('%d/%m/%Y')
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            elif format_type == 'yes_no':
                # Normalize yes/no answers
                answer_lower = answer.lower().strip()
                if any(word in answer_lower for word in ['yes', 'yeah', 'yep', 'sure', 'ok', 'agree']):
                    fixed_answer = 'Yes'
                elif any(word in answer_lower for word in ['no', 'nope', 'nah', 'not']):
                    fixed_answer = 'No'
                print(f"   🔧 Fixed yes/no: {answer} -> {fixed_answer}")
            
            # Re-validate the fixed answer
            is_valid, error_msg = validate_answer(fixed_answer, format_type)
            if is_valid:
                return fixed_answer, confidence
            else:
                # Return original with lower confidence if we can't fix it
                return answer, 0.6
                
        except Exception as e:
            print(f"   ⚠️ Error in validation retry: {e}")
            return answer, 0.6

    def _match_answer_to_options(
        self,
        answer: str,
        options: List[str],
        question: str = ""
    ) -> Tuple[str, float]:
        """
        Match an answer to available options using the input-aware resolver.
        
        Args:
            answer: The intended answer value
            options: List of available options for select/radio
            question: Question text for context
            
        Returns:
            Tuple of (matched_option, confidence)
        """
        if not options:
            return answer, 0.5
        
        opt_objects = [Option(value=o, label=o, index=i) for i, o in enumerate(options)]
        
        result = self._input_resolver.resolve(
            answer=answer,
            input_type=ResolverInputType.SELECT,
            options=opt_objects,
            question=question
        )
        
        if result.matched_option:
            return result.matched_option.label, result.confidence
        
        return answer, 0.3
    
    def _get_learned_answer(self, question: str) -> Optional[Tuple[str, float]]:
        """
        Get a learned answer for a question.
        
        Checks both self-healing patterns and pattern learner.
        
        Returns:
            Tuple of (answer, confidence) or None
        """
        # Check self-healing learned patterns first
        healed = self._self_healing.get_learned_answer(question)
        if healed and healed[1] >= 0.5:
            return healed
        
        # Check pattern learner
        learned = self._pattern_learner.find_answer(question)
        if learned and learned[1] >= 0.5:
            return learned
        
        return None
    
    async def _attempt_form_recovery(self) -> bool:
        """
        Attempt to recover from form errors using self-healing.
        Called AFTER existing JS error detection has found issues.
        
        Returns:
            True if recovery was successful
        """
        if not self._error_detector:
            self._init_error_detection()
        
        if not self._error_detector:
            return False
        
        # Detect current errors using Python layer
        errors = await self._error_detector.detect_errors()
        
        if not errors:
            return False
        
        for error in errors:
            healed_value = None
            
            # Try learned patterns for this field
            if error.field_label:
                learned = self._get_learned_answer(error.field_label)
                if learned and learned[1] >= 0.5:
                    print(f"   🔧 Using learned answer for '{error.field_label[:30]}...': {learned[0]}")
                    # Record success pattern
                    pattern = self._self_healing.learning_store.find_pattern_for_question(error.field_label)
                    if pattern:
                        self._self_healing.learning_store.record_success(pattern.pattern_id)
                    healed_value = learned[0]
            
            # Try option matching if options available
            if not healed_value and error.available_options and error.field_value:
                matched, confidence = self._match_answer_to_options(
                    error.field_value,
                    error.available_options,
                    error.field_label or ""
                )
                if confidence >= 0.7:
                    print(f"   🔧 Option matched: '{matched}' (conf: {confidence:.0%})")
                    healed_value = matched

            if healed_value:
                # Inject the healed value back into the DOM using the label text to find the input
                try:
                    js_inject = f"""() => {{
                        const labels = Array.from(document.querySelectorAll('label'));
                        const targetLabel = labels.find(l => l.innerText.trim().includes(`{error.field_label}`));
                        if (!targetLabel) return false;
                        
                        const container = targetLabel.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question') || targetLabel.parentElement;
                        
                        // Handle Select Dropdowns
                        const select = container.querySelector('select');
                        if (select) {{
                            const options = Array.from(select.options);
                            const targetOpt = options.find(o => o.text.trim() === `{healed_value}`);
                            if (targetOpt) {{
                                select.value = targetOpt.value;
                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                        
                        // Handle Text/Number Inputs
                        const input = container.querySelector('input:not([type="radio"]):not([type="checkbox"]), textarea');
                        if (input) {{
                            const prevVal = input.value;
                            const fill = (val) => {{
                                try {{
                                    const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                                    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                                    if (nativeSetter) nativeSetter.call(input, val);
                                    else input.value = val;
                                }} catch(e) {{ input.value = val; }}
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                            }};
                            
                            // Clear first, then set healed value
                            fill('');
                            fill(`{healed_value}`);
                            
                            // Fallback
                            if (input.value !== `{healed_value}` && Reflect.has(input, 'value')) {{
                                Reflect.set(input, 'value', `{healed_value}`);
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            }}
                            
                            return true;
                        }}
                        
                        // Handle Radio buttons (like Yes/No)
                        const radios = container.querySelectorAll('input[type="radio"]');
                        if (radios.length > 0) {{
                            for (const r of radios) {{
                                const rLabel = container.querySelector(`label[for="${{r.id}}"]`)?.innerText || r.value;
                                if (rLabel.toLowerCase().includes(`{healed_value}`.toLowerCase())) {{
                                    r.click();
                                    r.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    return true;
                                }}
                            }}
                        }}
                        
                        return false;
                    }}"""
                    success = await self._page.evaluate(js_inject)
                    if success:
                        print(f"   ✅ Successfully injected healed value '{healed_value}'")
                        return True
                    else:
                        print(f"   ⚠️ Failed to inject healed value '{healed_value}' into DOM")
                except Exception as e:
                    print(f"   ⚠️ Error during DOM injection: {{e}}")
                    
        return False

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
                    // 1. Check for explicit login forms/containers
                    const loginForm = document.querySelector('#login-form, .login-container');
                    if (loginForm) return true;

                    // 2. Check for "Login" button specifically in the main header (avoiding footers/hidden menus)
                    // Naukri's top bar usually has 'naukri-header' or similar structure
                    const header = document.querySelector('.naukri-header, #naukri-header, .naukri-header-container');
                    const loginBtnInHeader = header ? header.querySelector('a[href*="login"], .login-btn') : null;
                    
                    // 3. Verify if we see profile-specific elements (e.g., 'My Naukri', 'Profile', or logout link)
                    const profileIcon = document.querySelector('.icon-profile, .nC_user-img, a[href*="logout"]');
                    const myNaukriText = document.body.innerText.includes('My Naukri') || 
                                       document.body.innerText.includes('View Profile');

                    // If profile elements exist, we are definitely logged in
                    if (profileIcon || myNaukriText) return false;

                    // If we find a login button in the header and NO profile elements, we might be logged out
                    // But common "ghost" login buttons can still exist. 
                    // Let's only trigger if we are on a page that actually REQUIRES login but shows a login prompt.
                    const bodyText = document.body.innerText;
                    const restrictedPage = bodyText.includes('Login to continue') || 
                                         bodyText.includes('Please login');

                    return !!(loginBtnInHeader && restrictedPage);
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
        """Helper to log JS console messages with filtering for noisy errors."""
        text = msg.text
        
        # Filter out noisy resource loading errors
        noisy_patterns = [
            'ERR_FAILED',
            'Failed to load resource',
            'the server responded with a status of',
            'visitor.publishDestinations',
            'destination publishing iframe',
            'External tag load event',
            'net::ERR_BLOCKED_BY_CLIENT',
            'net::ERR_CONNECTION_REFUSED',
        ]
        
        # Skip if message contains any noisy pattern
        if any(pattern in text for pattern in noisy_patterns):
            return
        
        # Skip tracking/analytics domains
        noisy_domains = [
            'ads.linkedin.com',
            'analytics',
            'tracking',
            'pixel',
            'google-analytics',
            'doubleclick',
            'facebook.com/tr',
        ]
        
        if any(domain in text.lower() for domain in noisy_domains):
            return
        
        # Print important messages
        print(f"   🖥️ JS: {text[:200]}")  # Limit length to prevent spam

    def _get_max_steps(self) -> int:
        """Determine max steps based on task type - LinkedIn gets 120, others get 50."""
        # Use a more specific check for LinkedIn to avoid false positives from common context
        task_desc = getattr(self, '_task_description', '')
        current_url = self._page.url.lower() if self._page else ''
        
        # Check if the task is explicitly for LinkedIn based on URL or specific LinkedIn keywords
        is_linkedin_task = (
            'linkedin.com/jobs' in current_url or 
            'linkedin.com/search' in current_url or
            ('LINKEDIN_JOB_APPLY_TASK' in task_desc and 'linkedin' in current_url)
        )
        
        if is_linkedin_task:
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
                    self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
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
                
                # Naukri: Partial success - applied some jobs but need more
                if 'NAUKRI_SUCCESS_PARTIAL' in result:
                    print(f"📜 {result}")
                    print("🔄 Continuing to apply for more jobs...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # LinkedIn: Success detected but need to navigate to next job
                if 'LINKEDIN_SUCCESS_NEED_NAV' in result:
                    self.metrics['applications_submitted'] += 1
                    print(f"✅ LinkedIn success! Total: {self.metrics['applications_submitted']}")
                    
                    if 'LinkedIn' in self._task_description and self.metrics['applications_submitted'] >= 5:
                        print("🎉 LinkedIn limit reached (5 jobs). Stopping task.")
                        self.state.task_complete = True
                        break

                    print("   Need to navigate to next job...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # LinkedIn: Success modal was closed, need to navigate to next job
                if 'LINKEDIN_SUCCESS_MODAL_CLOSED' in result:
                    self.metrics['applications_submitted'] += 1
                    print(f"✅ Success modal dismissed. Total: {self.metrics['applications_submitted']}")
                    
                    if 'LinkedIn' in self._task_description and self.metrics['applications_submitted'] >= 5:
                        print("🎉 LinkedIn limit reached (5 jobs). Stopping task.")
                        self.state.task_complete = True
                        break

                    print("   Looking for next job...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # LinkedIn: Safety modal "Continue applying" button clicked
                if 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED' in result:
                    print("✅ LinkedIn safety modal dismissed, continuing application...")
                    await asyncio.sleep(random.uniform(4, 6))
                    continue
                
                # LinkedIn: Location autocomplete dropdown needs to be clicked
                if result in ('LINKEDIN_LOCATION_RETRIGGERED', 'LINKEDIN_LOCATION_FILLED_WAITING_DROPDOWN'):
                    retrigger_count = getattr(self, '_location_retrigger_count', 0) + 1
                    self._location_retrigger_count = retrigger_count
                    
                    if retrigger_count > 2:
                        print(f"⚠️ Location dropdown not appearing after {retrigger_count} attempts. Trying fallback strategies...")
                        self._location_retrigger_count = 0
                        
                        # Strategy 1: Try clearing the location field entirely and see if that allows progress
                        print("   📝 Strategy 1: Clearing location field...")
                        try:
                            clear_result = await self._page.evaluate("""() => {
                                const inputs = document.querySelectorAll('input[type="text"], input[type="search"], textarea, input:not([type="hidden"])');
                                let locationInput = null;
                                for (const inp of inputs) {
                                    const val = inp.value || '';
                                    if (val.toLowerCase().includes('noida')) {
                                        locationInput = inp;
                                        break;
                                    }
                                }
                                
                                if (locationInput) {
                                    // Clear the field completely
                                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                    nativeInputValueSetter.call(locationInput, '');
                                    locationInput.dispatchEvent(new Event('input', { bubbles: true }));
                                    locationInput.dispatchEvent(new Event('change', { bubbles: true }));
                                    locationInput.dispatchEvent(new Event('blur', { bubbles: true }));
                                    console.log('Location field cleared');
                                    return 'CLEARED';
                                }
                                return 'NOT_FOUND';
                            }""")
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            print(f"   ⚠️ Clear failed: {e}")
                        
                        # Strategy 2: Force click the Next button even with empty/invalid location
                        print("   🔘 Strategy 2: Force-clicking Next button...")
                        try:
                            # Use Playwright's click which is more reliable
                            next_buttons = await self._page.locator('button:has-text("Next"), button:has-text("Continue"), button[aria-label*="Next"]').all()
                            clicked = False
                            for btn in next_buttons:
                                try:
                                    await btn.click(timeout=1000)
                                    print("   ✅ Next button clicked via locator")
                                    clicked = True
                                    break
                                except:
                                    pass
                            
                            if not clicked:
                                # Fallback to JavaScript click
                                await self._page.evaluate("""() => {
                                    const buttons = document.querySelectorAll('button');
                                    for (const btn of buttons) {
                                        const text = btn.innerText.toLowerCase();
                                        if ((text.includes('next') || text.includes('continue')) && btn.offsetParent !== null) {
                                            console.log('Force clicking button:', btn.innerText);
                                            btn.click();
                                            btn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                            btn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                            btn.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                            return 'CLICKED';
                                        }
                                    }
                                    return 'NOT_FOUND';
                                }""")
                                print("   ✅ Next button clicked via JavaScript")
                            
                            await asyncio.sleep(1)
                        except Exception as e:
                            print(f"   ⚠️ Force click failed: {e}")
                        
                        continue
                    
                    print(f"   🔍 Selecting location from dropdown (attempt {retrigger_count}/3)...")
                    try:
                        # Get diagnostic info about what's in the DOM
                        diagnostics = await self._page.evaluate("""() => {
                            const modal = document.querySelector('.jobs-easy-apply-modal, .artdeco-modal--is-open');
                            if (!modal) return { error: 'No modal found' };
                            
                            // Find the Noida input
                            const inputs = modal.querySelectorAll('input[type="text"], input[type="search"], textarea');
                            let noIdaInput = null;
                            for (const inp of inputs) {
                                if ((inp.value || '').includes('Noida')) {
                                    noIdaInput = inp;
                                    break;
                                }
                            }
                            
                            if (!noIdaInput) return { error: 'Noida input not found' };
                            
                            // Look for dropdown-related elements
                            const dropdownLists = modal.querySelectorAll('[role="listbox"], .typeahead-input__dropdown-list, .artdeco-typeahead__results-list, [data-test-typeahead-results]');
                            const dropdownItems = modal.querySelectorAll('[role="option"], .typeahead-input__dropdown-item, .artdeco-typeahead__result');
                            
                            // Look for any select elements
                            const selects = modal.querySelectorAll('select');
                            const selectOptions = selects.length > 0 ? Array.from(selects[0].querySelectorAll('option')).map(o => o.text) : [];
                            
                            // Look for buttons near the input
                            const inputContainer = noIdaInput.closest('.fb-dash-form-element') || noIdaInput.parentElement;
                            const buttonsNear = inputContainer ? inputContainer.querySelectorAll('button') : [];
                            
                            return {
                                inputId: noIdaInput.id,
                                inputValue: noIdaInput.value,
                                dropdownListsFound: dropdownLists.length,
                                dropdownItemsFound: dropdownItems.length,
                                selectsFound: selects.length,
                                selectOptions: selectOptions,
                                buttonsNear: Array.from(buttonsNear).map(b => b.innerText),
                                inputParentClass: inputContainer?.className
                            };
                        }""")
                        
                        print(f"   📋 Diagnostics: {diagnostics}")
                        
                        if diagnostics.get('error'):
                            print(f"   ⚠️ {diagnostics['error']}")
                        
                        # Try strategy 1: Keyboard navigation (ArrowDown to select first option)
                        print("   ↓ Trying keyboard navigation...")
                        keyboard_result = await self._page.evaluate("""() => {
                            const inputs = document.querySelectorAll('input[type="text"], input[type="search"], textarea, input:not([type="hidden"])');
                            let locationInput = null;
                            for (const inp of inputs) {
                                const val = inp.value || '';
                                if (val.toLowerCase().includes('noida')) {
                                    locationInput = inp;
                                    break;
                                }
                            }
                            
                            if (locationInput) {
                                locationInput.focus();
                                // Try ArrowDown to open dropdown
                                locationInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }));
                                locationInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }));
                                // Wait briefly then try another ArrowDown to select first option
                                return 'ARROW_DOWN_SENT';
                            }
                            return 'NOT_FOUND';
                        }""")
                        
                        # Wait for potential dropdown to open
                        await asyncio.sleep(0.4)
                        
                        # Step 2: Try to find and click dropdown option
                        click_result = await self._page.evaluate("""() => {
                            // First check if there are ANY visible elements that might be dropdown items
                            const allDivs = document.querySelectorAll('[role="option"], li, div[class*="dropdown"], div[class*="option"], span[class*="option"]');
                            console.log('Total potential dropdown elements:', allDivs.length);
                            
                            // Try all dropdown selectors with aggressive clicking
                            const dropdownSelectors = [
                                // Pismo-specific selectors (what we see in your form)
                                'div[class*="typeahead"] [role="option"]',
                                'div[class*="search-vertical"] [role="option"]',
                                '.gqueried-content [role="option"]',
                                '[role="option"]',
                                
                                // LinkedIn-specific selectors
                                '.typeahead-input__dropdown-item',
                                '.typeahead-input__dropdown-list li',
                                '[role="listbox"] [role="option"]',
                                '.artdeco-typeahead__result',
                                'li[class*="typeahead"]',
                                'div[class*="dropdown"] li',
                                'div[class*="option"] li'
                            ];
                            
                            let clickedAny = false;
                            for (const selector of dropdownSelectors) {
                                const options = document.querySelectorAll(selector);
                                console.log('Checking selector:', selector, '- found:', options.length);
                                for (const option of options) {
                                    // Check if option is visible and has content
                                    if (option.offsetParent !== null) {
                                        const text = (option.innerText || option.textContent || '').trim();
                                        if (text && text.toLowerCase().includes('noida')) {
                                            console.log('Found Noida option, clicking:', text);
                                            option.scrollIntoView({block: 'nearest'});
                                            option.click();
                                            option.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                            option.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                            option.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                            option.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                            clickedAny = true;
                                            break;
                                        }
                                    }
                                }
                                if (clickedAny) break;
                            }
                            
                            if (!clickedAny) {
                                // Try clicking any visible option as fallback
                                for (const selector of dropdownSelectors) {
                                    const options = document.querySelectorAll(selector);
                                    for (const option of options) {
                                        if (option.offsetParent !== null) {
                                            const text = (option.innerText || option.textContent || '').trim();
                                            if (text && text.length > 0 && !text.includes('select') && !text.includes('choose')) {
                                                console.log('Fallback: clicking first visible option:', text);
                                                option.scrollIntoView({block: 'nearest'});
                                                option.click();
                                                option.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                                option.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                                option.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                                option.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                                clickedAny = true;
                                                break;
                                            }
                                        }
                                    }
                                    if (clickedAny) break;
                                }
                            }
                            
                            return clickedAny ? 'CLICKED' : 'NOT_FOUND';
                        }""")
                        
                        if click_result == 'CLICKED':
                            print(f"   ✅ Dropdown option clicked")
                            self._location_retrigger_count = 0
                            await asyncio.sleep(1)
                        else:
                            # Fallback: Try using Playwright's locator to find and click the option
                            print("   📍 JavaScript click didn't work, trying Playwright locator...")
                            try:
                                # Try to find and click any option containing "Noida"
                                option_locator = self._page.locator('[role="option"]:has-text("Noida")')
                                if await option_locator.count() > 0:
                                    await option_locator.first.click(timeout=2000)
                                    print("   ✅ Clicked option via Playwright locator")
                                    self._location_retrigger_count = 0
                                    await asyncio.sleep(1)
                                else:
                                    # Try clicking any visible option
                                    any_option = self._page.locator('[role="option"]')
                                    if await any_option.count() > 0:
                                        await any_option.first.click(timeout=2000)
                                        print("   ✅ Clicked first option via Playwright")
                                        self._location_retrigger_count = 0
                                        await asyncio.sleep(1)
                                    else:
                                        print("   ⏳ No options found via Playwright either, will retry...")
                                        await asyncio.sleep(0.5)
                            except Exception as e:
                                print(f"   ⚠️ Playwright click failed: {e}")
                                await asyncio.sleep(0.5)
                    except Exception as e:
                        print(f"   ⚠️ Error during selection: {e}")
                        await asyncio.sleep(0.5)
                    continue
                
                # LinkedIn: First job opened (when no currentJobId in URL)
                if 'LINKEDIN_FIRST_JOB' in result:
                    print(f"✅ {result}")
                    await asyncio.sleep(random.uniform(4, 6))
                    continue
                
                # LinkedIn: Navigation results
                if 'LINKEDIN_NAVIGATED' in result:
                    print(f"✅ {result}")
                    if 'card null' in result.lower() or 'card None' in result:
                        if not self._linkedin_scroll_attempted:
                            print("⚠️  Null card detected - trying to scroll down first...")
                            self._linkedin_scroll_attempted = True
                            try:
                                # Scroll the job list to load more jobs
                                await self._page.evaluate("""() => {
                                    const sidebar = document.querySelector('.scaffold-layout__list') || 
                                                   document.querySelector('.jobs-search-results-list');
                                    if (sidebar) {
                                        sidebar.scrollTop += 800;
                                        return 'Scrolled job list';
                                    }
                                    window.scrollTo(0, window.scrollY + 800);
                                    return 'Scrolled window';
                                }""")
                                await asyncio.sleep(random.uniform(3, 5))
                            except Exception as e:
                                print(f"⚠️  Scroll failed: {e}")
                        else:
                            print("⚠️  Null card still detected after scroll - refreshing page...")
                            self._linkedin_scroll_attempted = False  # Reset for next time
                            try:
                                await self._page.reload(wait_until='domcontentloaded', timeout=15000)
                                await asyncio.sleep(random.uniform(5, 8))
                            except Exception as e:
                                print(f"⚠️  Refresh failed: {e}")
                    else:
                        self._linkedin_scroll_attempted = False  # Reset on successful navigation
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
                            self.linkedin_rate_limit_until = datetime.now() + timedelta(hours=9)
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
                            self.linkedin_rate_limit_until = datetime.now() + timedelta(hours=9)
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
                        elif 'LINKEDIN_AUTOCOMPLETE_OPTION_SELECTED' in next_result:
                            print("🎯 Selected autocomplete option")
                            await asyncio.sleep(0.5)  # Brief pause for selection to register
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
                            print("⚠️ Autopilot stuck, checking for form errors...")
                            recovered = await self._attempt_form_recovery()
                            if recovered:
                                print("🛠️ Self-healing resolved form errors, resuming...")
                                continue
                                
                            print("⚠️ Exiting Autopilot...")
                            break
                        elif 'LINKEDIN_JOB_SKIPPED' in next_result:
                            print("⏭️ Job skipped, moving to next...")
                            break
                
                # Naukri Profile Update - Resume Headline Toggle
                # NOTE: Only run if NOT an Employment LWD task (same URL, different task)
                # NOTE: Skip if coming from a failed application attempt (error page)
                if ('profile' in current_url and 'naukri.com' in current_url and 
                    'Employment' not in self._task_description and 
                    'myapply' not in current_url and 'saveApply' not in current_url):
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
                            self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
                            print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                            self.state.task_complete = True
                            break
                        elif chatbot_done:
                            print("🎉 Naukri Application Completed!")
                            self.state.task_complete = True
                            break
                        else:
                            # Chatbot loop exhausted - navigate back to recommended jobs to try different jobs
                            print("🔄 Chatbot exhausted - navigating back to recommended jobs...")
                            try:
                                await self._page.goto('https://www.naukri.com/mnjuser/recommendedjobs', timeout=30000)
                                await asyncio.sleep(random.uniform(4, 6))
                                continue
                            except Exception as e:
                                print(f"   ⚠️ Navigation error: {e}")
                
                # Naukri Chatbot handling (for direct APPLY_CLICKED)
                if 'APPLY_CLICKED' in result and 'LINKEDIN' not in result and 'naukri.com' in current_url:
                    print("⏳ Waiting for Naukri chatbot...")
                    await asyncio.sleep(random.uniform(4, 8))
                    chatbot_done = await self._handle_chatbot_loop()
                    if chatbot_done == 'CONTINUE':
                        continue
                    elif isinstance(chatbot_done, str) and 'NAUKRI_RATE_LIMITED' in chatbot_done:
                        # Error popup detected - set rate limit and exit
                        self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
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
                    else:
                        # Chatbot loop exhausted - navigate back to recommended jobs to try different jobs
                        print("🔄 Chatbot exhausted - navigating back to recommended jobs...")
                        try:
                            await self._page.goto('https://www.naukri.com/mnjuser/recommendedjobs', timeout=30000)
                            await asyncio.sleep(random.uniform(4, 6))
                            continue
                        except Exception as e:
                            print(f"   ⚠️ Navigation error: {e}")
                
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
                        if 'linkedin.com' in current_url:
                            if not self._linkedin_scroll_attempted:
                                print("❌ No job cards found on LinkedIn - trying to scroll down first...")
                                self._linkedin_scroll_attempted = True
                                try:
                                    # Scroll the job list to load more jobs
                                    await self._page.evaluate("""() => {
                                        const sidebar = document.querySelector('.scaffold-layout__list') || 
                                                       document.querySelector('.jobs-search-results-list');
                                        if (sidebar) {
                                            sidebar.scrollTop += 800;
                                            return 'Scrolled job list';
                                        }
                                        window.scrollTo(0, window.scrollY + 800);
                                        return 'Scrolled window';
                                    }""")
                                    await asyncio.sleep(random.uniform(3, 5))
                                    continue  # Continue loop to try again after scroll
                                except Exception as e:
                                    print(f"⚠️  Scroll failed: {e}")
                            else:
                                print("❌ Still no job cards after scroll - refreshing page...")
                                self._linkedin_scroll_attempted = False
                                try:
                                    await self._page.reload(wait_until='domcontentloaded', timeout=15000)
                                    await asyncio.sleep(random.uniform(5, 8))
                                    continue  # Continue loop to try again after refresh
                                except Exception as e:
                                    print(f"⚠️  Refresh failed: {e}")
                        else:
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
        previous_questions = []
        same_question_count = 0
        
        for iteration in range(max_iterations):
            await asyncio.sleep(random.uniform(2, 3.5))
            
            result = await self._page.evaluate(f"""async () => {{
                const KNOWN_PATTERNS = {patterns_json};
                
                const fuzzyMatch = (question) => {{
                    if (!question) return null;
                    const qLower = question.toLowerCase().trim();
                    let bestMatch = null;
                    let bestKeyLen = 0;
                    
                    const sortedPatterns = Object.entries(KNOWN_PATTERNS).sort((a, b) => b[0].length - a[0].length);
                    
                    for (const [key, val] of sortedPatterns) {{
                        const keyLower = key.toLowerCase();
                        if (qLower === keyLower) {{
                            return val;
                        }}
                        if (qLower.includes(keyLower) && key.length > bestKeyLen) {{
                            if (keyLower === 'years' && (qLower.includes('salary') || qLower.includes('ctc') || qLower.includes('pay') || qLower.includes('inr'))) {{
                                continue;
                            }}
                            bestMatch = val;
                            bestKeyLen = key.length;
                        }}
                    }}
                    return bestMatch;
                }};
                
                const snackBody = document.querySelector('.ss-snackbar-body');
                if (snackBody && snackBody.offsetParent !== null) {{
                    const snackText = snackBody.innerText.toLowerCase();
                    if (snackText.includes('error') || snackText.includes('limit') || snackText.includes('reached') || snackText.includes('something went wrong')) {{
                        const closeBtn = document.querySelector('button.ss-close');
                        if (closeBtn) closeBtn.click();
                        return 'NAUKRI_RATE_LIMITED: Error popup detected at loop start';
                    }}
                }}
                
                const mccPopup = document.querySelector('.mcc-popup, [class*="update-popup"], [class*="confirmation-modal"]');
                if (mccPopup && mccPopup.offsetParent !== null) {{
                    return 'MCC_POPUP_DETECTED';
                }}
                
                const successIndicators = [
                    document.querySelector('.chatbot_SuccessMsg'),
                    document.querySelector('[class*="success"]'),
                    document.body.innerText.includes('Application submitted'),
                    document.body.innerText.includes('Successfully applied')
                ];
                if (successIndicators.some(Boolean)) {{
                    return 'CHATBOT_COMPLETE';
                }}
                
                let chatLayer = document.querySelector('.chatbot_DrawerContentWrapper');
                if (!chatLayer) {{
                    chatLayer = document.querySelector('[class*="drawer"], [class*="modal"], [role="dialog"]');
                }}
                const isVisible = (el) => {{
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && rect.top >= 0;
                }};
                if (!chatLayer || !isVisible(chatLayer)) {{
                    if (document.body.innerText.includes('applied')) {{
                        return 'CHATBOT_COMPLETE';
                    }}
                    return 'NO_CHATBOT';
                }}
                
                let questionEl = chatLayer.querySelector('.chatbot_QuestionContainer, .botMsg, [class*="question"]');
                let qText = '';
                if (questionEl) {{
                    qText = questionEl.innerText || '';
                }} else {{
                    qText = chatLayer.innerText || '';
                }}
                
                let answer = fuzzyMatch(qText) || '3.8';
                
                // Special handling for Naukri salary questions - extract numeric value
                const isNaukri = window.location.hostname.includes('naukri');
                const isSalaryQuestion = qText.toLowerCase().includes('salary') || 
                    qText.toLowerCase().includes('ctc') || 
                    qText.toLowerCase().includes('compensation') ||
                    qText.toLowerCase().includes('pay');
                
                if (isNaukri && isSalaryQuestion && answer) {{
                    const numericMatch = answer.match(/(\\d+\\.?\\d*)/);
                    if (numericMatch) {{
                        answer = numericMatch[1];
                    }}
                }}
                
                // DEBUG: Log what we detected
                console.log('Chatbot Debug - Question:', qText.substring(0, 100), '| Answer:', answer);
                
                // DEBUG: Log all inputs found in chatLayer
                if (chatLayer) {{
                    const debugInputs = chatLayer.querySelectorAll('input:not([type="hidden"]), textarea');
                    console.log('Chatbot Debug - Inputs in chatLayer:', debugInputs.length);
                    debugInputs.forEach((inp, i) => {{
                        console.log('  Input[' + i + ']:', inp.type, inp.placeholder || inp.name || inp.id, 'visible:', inp.offsetParent !== null);
                    }});
                }}
                
                // STEP 1: DETECT all available input types on the page
                const hasSelect = chatLayer.querySelector('select') !== null;
                const hasRadio = chatLayer.querySelectorAll('input[type="radio"]').length > 0;
                const hasCheckbox = chatLayer.querySelectorAll('input[type="checkbox"]').length > 0;
                let textInput = chatLayer.querySelector('input[type="text"]:not([type="hidden"]):not([type="file"]), textarea');
                let contentEditable = chatLayer.querySelector('div[contenteditable="true"]') || 
                                     document.querySelector('div[contenteditable="true"]');
                
                console.log('Chatbot Debug - Available inputs:', {{select: hasSelect, radio: hasRadio, checkbox: hasCheckbox, text: !!textInput, editable: !!contentEditable}});
                
                // STEP 2: USE the first available input type (sequential detection)
                // Order: Dropdown -> Radio -> Checkbox -> Text Input -> Contenteditable
                
                // HANDLE DROPDOWN
                if (hasSelect) {{
                    const select = chatLayer.querySelector('select');
                    if (select && select.offsetParent !== null) {{
                        const selectOptions = Array.from(select.options);
                        console.log('Chatbot Debug - Found dropdown with', selectOptions.length, 'options');
                        
                        // For salary questions, look for option containing the number
                        for (const opt of selectOptions) {{
                            const optText = opt.text.toLowerCase();
                            if (isSalaryQuestion) {{
                                // Match if option contains our numeric answer
                                if (optText.includes(answer) || 
                                    (answer === '24' && (optText.includes('24') || optText.includes('20-25') || optText.includes('20-24')))) {{
                                    select.value = opt.value;
                                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    const saveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                                    if (saveDiv && saveDiv.offsetParent !== null) {{
                                        saveDiv.click();
                                    }}
                                    return 'CHATBOT_DROPDOWN_SELECTED: ' + opt.text;
                                }}
                            }} else {{
                                // Non-salary: try to match by answer text
                                if (optText.includes(answer.toLowerCase())) {{
                                    select.value = opt.value;
                                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    const saveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                                    if (saveDiv && saveDiv.offsetParent !== null) {{
                                        saveDiv.click();
                                    }}
                                    return 'CHATBOT_SELECTED: ' + opt.text;
                                }}
                            }}
                        }}
                        
                        // Default: select second option if available
                        if (selectOptions.length > 1) {{
                            select.selectedIndex = 1;
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            const saveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                            if (saveDiv && saveDiv.offsetParent !== null) {{
                                saveDiv.click();
                                return 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE: ' + selectOptions[1].text;
                            }}
                            return 'CHATBOT_SELECTED_DEFAULT: ' + selectOptions[1].text;
                        }}
                    }}
                }}
                
                // HANDLE RADIO BUTTONS
                if (hasRadio) {{
                    const radios = chatLayer.querySelectorAll('input[type="radio"]');
                    console.log('Chatbot Debug - Processing radio buttons:', radios.length);
                    
                    let clickedRadio = false;
                    const answerLower = answer.toLowerCase();
                    
                    // Try to match answer to radio label
                    for (const radio of radios) {{
                        const label = radio.parentElement?.innerText || radio.nextSibling?.textContent || '';
                        const labelLower = label.toLowerCase();
                        
                        // Match Yes/Serving for positive answers
                        if ((answerLower.includes('yes') || answerLower.includes('true')) && 
                            (labelLower.includes('yes') || labelLower.includes('serving'))) {{
                            if (!radio.checked) {{
                                radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked Yes radio:', label);
                            }}
                            break;
                        }}
                        // Match No for negative answers
                        if ((answerLower.includes('no') || answerLower.includes('false')) && 
                            labelLower.includes('no')) {{
                            if (!radio.checked) {{
                                radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked No radio:', label);
                            }}
                            break;
                        }}
                    }}
                    
                    // If no match found, click first unchecked radio
                    if (!clickedRadio) {{
                        for (const radio of radios) {{
                            if (!radio.checked) {{
                                radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked default radio');
                                break;
                            }}
                        }}
                    }}
                    
                    // After selecting radio, click Save/Submit button
                    if (clickedRadio) {{
                        await new Promise(r => setTimeout(r, 300));
                        
                        const naukSaveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg, #sendMsg__vjhkrpzhhInputBox .sendMsg');
                        if (naukSaveDiv && naukSaveDiv.offsetParent !== null) {{
                            naukSaveDiv.click();
                            console.log('Chatbot Debug - Save clicked after radio');
                            return 'CHATBOT_RADIO_AND_SAVE: ' + qText.slice(0, 50);
                        }}
                        
                        const allButtons = chatLayer ? 
                            Array.from(chatLayer.querySelectorAll('button, div[tabindex], span[tabindex]')) : 
                            Array.from(document.querySelectorAll('[role="dialog"] button, [class*="modal"] button'));
                        
                        for (const btn of allButtons) {{
                            const btnText = btn.innerText.toLowerCase().trim();
                            if ((btnText === 'save' || btnText === 'submit' || btnText === 'next') 
                                && btn.offsetParent !== null) {{
                                btn.click();
                                console.log('Chatbot Debug - Save clicked after radio (fallback)');
                                return 'CHATBOT_RADIO_AND_SAVE: ' + qText.slice(0, 50);
                            }}
                        }}
                        
                        return 'CHATBOT_RADIO_CLICKED: ' + qText.slice(0, 50);
                    }}
                }}
                
                // HANDLE CHECKBOXES
                if (hasCheckbox) {{
                    const checkboxes = chatLayer.querySelectorAll('input[type="checkbox"]');
                    console.log('Chatbot Debug - Processing checkboxes:', checkboxes.length);
                    
                    let clickedCheckbox = false;
                    const answerLower = answer.toLowerCase();
                    
                    // Try to match answer to checkbox label
                    for (const checkbox of checkboxes) {{
                        const label = checkbox.parentElement?.innerText || checkbox.nextSibling?.textContent || '';
                        const labelLower = label.toLowerCase();
                        
                        // Check if answer matches this option
                        if (answerLower.includes(labelLower) || labelLower.includes(answerLower)) {{
                            if (!checkbox.checked) {{
                                checkbox.click();
                                clickedCheckbox = true;
                                console.log('Chatbot Debug - Clicked checkbox:', label);
                            }}
                        }}
                    }}
                    
                    // If no specific match but answer is "Yes" or positive, check first option
                    if (!clickedCheckbox && (answerLower.includes('yes') || answerLower.includes('true'))) {{
                        for (const checkbox of checkboxes) {{
                            if (!checkbox.checked) {{
                                checkbox.click();
                                clickedCheckbox = true;
                                console.log('Chatbot Debug - Clicked default checkbox');
                                break;
                            }}
                        }}
                    }}
                    
                    // After selecting checkbox(es), click Save/Submit button
                    if (clickedCheckbox) {{
                        // Wait for UI to update
                        await new Promise(r => setTimeout(r, 300));
                        
                        // Find and click Save button
                        const saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg') ||
                                       Array.from(document.querySelectorAll('button')).find(el => 
                                           el.innerText.toLowerCase().includes('save'));
                        
                        if (saveBtn && saveBtn.offsetParent !== null) {{
                            saveBtn.click();
                            console.log('Chatbot Debug - Save clicked after checkbox');
                            return 'CHATBOT_CHECKBOX_AND_SAVE: ' + qText.slice(0, 50);
                        }}
                        
                        return 'CHATBOT_CHECKBOX_CLICKED: ' + qText.slice(0, 50);
                    }}
                }}
                
                // HANDLE TRADITIONAL TEXT INPUTS
                let input = null;
                if (chatLayer) {{
                    input = chatLayer.querySelector('input[type="text"][placeholder*="Type"], input[placeholder*="type"], input[placeholder*="Enter"]');
                    if (!input) {{
                        input = chatLayer.querySelector('input[type="text"]:not([type="hidden"]):not([type="file"])');
                    }}
                    if (!input) {{
                        input = chatLayer.querySelector('textarea');
                    }}
                    if (!input) {{
                        const chatInputs = chatLayer.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="file"]), textarea');
                        for (const inp of chatInputs) {{
                            const rect = inp.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0 && chatLayer.contains(inp)) {{
                                input = inp;
                                break;
                            }}
                        }}
                    }}
                }}
                
                if (!input) {{
                    input = document.querySelector('[role="dialog"] input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="file"]), [class*="modal"] input:not([type="hidden"]):not([type="file"]), textarea');
                }}
                
                // HANDLE CONTENTEDITABLE (Naukri chat-style inputs)
                let contentEditable = null;
                if (!input) {{
                    contentEditable = chatLayer.querySelector('div[contenteditable="true"]') || 
                                     document.querySelector('div[contenteditable="true"]');
                }}
                
                if (contentEditable) {{
                    console.log('Chatbot Debug - Found contenteditable div:', contentEditable.className);
                    
                    // Clear existing content
                    contentEditable.innerHTML = '';
                    
                    // Insert text as text node
                    const textNode = document.createTextNode(answer);
                    contentEditable.appendChild(textNode);
                    
                    // Trigger input event
                    contentEditable.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    contentEditable.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    
                    // Focus the element
                    contentEditable.focus();
                    
                    // Place cursor at end
                    const range = document.createRange();
                    range.selectNodeContents(contentEditable);
                    range.collapse(false);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    
                    console.log('Chatbot Debug - Contenteditable set to:', contentEditable.innerText);
                    
                    // Wait for UI to update
                    await new Promise(r => setTimeout(r, 500));
                    
                    let saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                        el.innerText.toLowerCase().trim() === 'save');
                    if (!saveBtn) {{
                        saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                    }}
                    if (!saveBtn) {{
                        saveBtn = document.querySelector('[id^="sendMsgbtn_container"]');
                    }}
                    if (!saveBtn && chatLayer) {{
                        saveBtn = chatLayer.querySelector('button');
                    }}
                    if (!saveBtn) {{
                        saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                            el.innerText.toLowerCase().includes('save'));
                    }}
                    
                    console.log('Chatbot Debug - Save button found:', !!saveBtn, saveBtn ? saveBtn.innerText : 'none');
                    
                    if (saveBtn) {{
                        if (saveBtn.disabled) {{
                            console.log('Chatbot Debug - Save button is disabled');
                            return 'CHATBOT_SAVE_DISABLED: ' + qText.slice(0, 50);
                        }}
                        
                        // ROBUST CLICK: Dispatch multiple events
                        saveBtn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.click();
                        
                        console.log('Chatbot Debug - Save button clicked');
                        
                        // Wait for UI to process
                        await new Promise(r => setTimeout(r, 300));
                        
                        // Check for error text after click (validation error)
                        const errorSelectors = [
                            '.error', '.err', '[class*="error"]',
                            '.chatbot_error', '.errorMsg', '.validation-error',
                            '[class*="invalid"]', '.red-text', '.warning'
                        ];
                        for (const sel of errorSelectors) {{
                            const errorMsg = document.querySelector(sel);
                            if (errorMsg && errorMsg.offsetParent !== null && errorMsg.innerText.trim()) {{
                                const errText = errorMsg.innerText.trim();
                                if (errText.length > 0 && errText.length < 200) {{
                                    console.log('Chatbot Debug - Error found:', errText);
                                    return 'CHATBOT_SUBMISSION_ERROR: ' + errText;
                                }}
                            }}
                        }}
                        
                        return 'CHATBOT_ANSWERED_AND_SAVE: ' + qText.slice(0, 50);
                    }}
                    return 'CHATBOT_ANSWERED: ' + qText.slice(0, 50);
                }}
                
                if (input && input.type !== 'file') {{
                    const isNumericInput = input.type === 'number' || 
                        input.getAttribute('inputmode') === 'numeric' ||
                        input.getAttribute('inputmode') === 'decimal' ||
                        (input.className && (
                            input.className.toLowerCase().includes('number') ||
                            input.className.toLowerCase().includes('decimal') ||
                            input.className.toLowerCase().includes('numeric')
                        )) ||
                        qText.toLowerCase().includes('in lakhs') ||
                        qText.toLowerCase().includes('in lacs');
                    
                    console.log('Chatbot Debug - Found input:', input.type, input.placeholder, 'Numeric:', isNumericInput);
                    
                    if (isNumericInput && answer) {{
                        const numericMatch = answer.match(/(\\d+\\.?\\d*)/);
                        if (numericMatch) {{
                            answer = numericMatch[1];
                            console.log('Chatbot Debug - Extracted numeric:', answer);
                        }}
                    }}
                    
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    if (setter) setter.call(input, answer);
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    
                    console.log('Chatbot Debug - Input value set to:', input.value);
                    
                    // Verify the value was set correctly
                    if (input.value !== answer) {{
                        // Try again with focus and blur
                        input.focus();
                        if (setter) setter.call(input, answer);
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.blur();
                    }}
                    
                    // FALLBACK: Try hitting Enter on the input
                    input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                    input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                    
                    // Wait a moment for UI to respond
                    await new Promise(r => setTimeout(r, 500));
                    
                    let saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                        el.innerText.toLowerCase().trim() === 'save');
                    if (!saveBtn) {{
                        saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                    }}
                    if (!saveBtn) {{
                        saveBtn = document.querySelector('[id^="sendMsgbtn_container"]');
                    }}
                    if (!saveBtn && chatLayer) {{
                        saveBtn = chatLayer.querySelector('button');
                    }}
                    if (!saveBtn) {{
                        saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                            el.innerText.toLowerCase().includes('save'));
                    }}
                    
                    console.log('Chatbot Debug - Save button found:', !!saveBtn, saveBtn ? saveBtn.innerText : 'none');
                    
                    if (saveBtn) {{
                        if (saveBtn.disabled) {{
                            console.log('Chatbot Debug - Save button is disabled');
                            return 'CHATBOT_SAVE_DISABLED: ' + qText.slice(0, 50);
                        }}
                        
                        // ROBUST CLICK: Dispatch multiple events
                        saveBtn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.click();
                        
                        console.log('Chatbot Debug - Save button clicked');
                        
                        // Wait for UI to process
                        await new Promise(r => setTimeout(r, 300));
                        
                        // Check for error text after click (validation error)
                        const errorSelectors = [
                            '.error', '.err', '[class*="error"]',
                            '.chatbot_error', '.errorMsg', '.validation-error',
                            '[class*="invalid"]', '.red-text', '.warning'
                        ];
                        for (const sel of errorSelectors) {{
                            const errorMsg = document.querySelector(sel);
                            if (errorMsg && errorMsg.offsetParent !== null && errorMsg.innerText.trim()) {{
                                const errText = errorMsg.innerText.trim();
                                if (errText.length > 0 && errText.length < 200) {{
                                    console.log('Chatbot Debug - Error found:', errText);
                                    return 'CHATBOT_SUBMISSION_ERROR: ' + errText;
                                }}
                            }}
                        }}
                        
                        return 'CHATBOT_ANSWERED_AND_SAVE: ' + qText.slice(0, 50);
                    }}
                    return 'CHATBOT_ANSWERED: ' + qText.slice(0, 50);
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
            
            # Extract question text from result for tracking
            current_question = None
            if 'CHATBOT_ANSWERED_AND_SAVE:' in result:
                current_question = result.split('CHATBOT_ANSWERED_AND_SAVE: ')[1] if 'CHATBOT_ANSWERED_AND_SAVE: ' in result else None
            elif 'CHATBOT_ANSWERED:' in result:
                current_question = result.split('CHATBOT_ANSWERED: ')[1] if 'CHATBOT_ANSWERED: ' in result else None
            elif 'CHATBOT_SUBMISSION_ERROR:' in result:
                current_question = result.split('CHATBOT_SUBMISSION_ERROR: ')[1] if 'CHATBOT_SUBMISSION_ERROR: ' in result else None
            elif 'CHATBOT_DROPDOWN_SELECTED:' in result:
                current_question = result.split('CHATBOT_DROPDOWN_SELECTED: ')[1] if 'CHATBOT_DROPDOWN_SELECTED: ' in result else None
            elif 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE:' in result:
                current_question = result.split('CHATBOT_DROPDOWN_DEFAULT_AND_SAVE: ')[1] if 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE: ' in result else None
            elif 'CHATBOT_SAVE_DISABLED:' in result:
                current_question = result.split('CHATBOT_SAVE_DISABLED: ')[1] if 'CHATBOT_SAVE_DISABLED: ' in result else None
            elif 'CHATBOT_RADIO_AND_SAVE:' in result:
                current_question = result.split('CHATBOT_RADIO_AND_SAVE: ')[1] if 'CHATBOT_RADIO_AND_SAVE: ' in result else None
            elif 'CHATBOT_RADIO_CLICKED:' in result:
                current_question = result.split('CHATBOT_RADIO_CLICKED: ')[1] if 'CHATBOT_RADIO_CLICKED: ' in result else None
            elif 'CHATBOT_CHECKBOX_AND_SAVE:' in result:
                current_question = result.split('CHATBOT_CHECKBOX_AND_SAVE: ')[1] if 'CHATBOT_CHECKBOX_AND_SAVE: ' in result else None
            elif 'CHATBOT_CHECKBOX_CLICKED:' in result:
                current_question = result.split('CHATBOT_CHECKBOX_CLICKED: ')[1] if 'CHATBOT_CHECKBOX_CLICKED: ' in result else None
            
            # Check if stuck on same question
            if current_question:
                if previous_questions and previous_questions[-1] == current_question:
                    same_question_count += 1
                    if same_question_count >= 3:
                        print(f"⚠️ Stuck on same question ({same_question_count}x): {current_question}")
                        # Take screenshot for debugging
                        try:
                            await self._screenshot_on_error("chatbot_stuck")
                        except:
                            pass
                        return False
                else:
                    same_question_count = 0
                previous_questions.append(current_question)
            
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
            elif 'CHATBOT_SUBMISSION_ERROR' in result:
                # Validation error - wait longer and try again
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_SAVE_DISABLED' in result:
                # Button not ready yet - wait
                await asyncio.sleep(random.uniform(1, 2))
                continue
            elif result == 'NO_CHATBOT':
                # Check if maybe we're done
                if iteration > 3:
                    return True
                continue
            elif 'CHATBOT_ANSWERED_AND_SAVE' in result:
                # Wait longer after successful save to let UI update
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_RADIO_AND_SAVE' in result:
                # Wait longer after successful radio selection
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_CHECKBOX_AND_SAVE' in result:
                # Wait longer after successful checkbox selection
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_DROPDOWN_SELECTED' in result or 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE' in result:
                # Wait longer after dropdown selection
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_WAITING' in result:
                # Nothing to do, wait
                continue
        
        print("⚠️ Chatbot loop exhausted")
        return False

    async def _handle_scripted_fallback(self) -> str:
        """Execute the scripted JavaScript fallback logic and return the result string."""
        # Serialize patterns, synonyms, and stop words for JS injection
        patterns_json = json.dumps(KNOWN_QA_PATTERNS)
        synonyms_json = json.dumps(SYNONYM_MAP)
        stopwords_json = json.dumps(list(STOP_WORDS))
        
        try:
            # We use a formatted string to inject the JSON, but we must escape braces for the JS function
            # NOTE: This function must NOT use async/await - Playwright's evaluate handles timing via Python asyncio
            # Using a function expression (wrapped in parens) - function statements require a name in JS
            js_code = f"""(function() {{
                // 1. INJECTED KNOWLEDGE
                const KNOWN_PATTERNS = {patterns_json};
                const SYNONYMS = {synonyms_json};
                const STOP_WORDS_SET = new Set({stopwords_json});
                
                // Platform-specific overrides
                if (window.location.hostname.includes('linkedin')) {{
                    // Override ALL experience values for LinkedIn (numeric-only fields)
                    // Instead of maintaining a list, scan all values generically
                    Object.keys(KNOWN_PATTERNS).forEach(k => {{
                        const v = KNOWN_PATTERNS[k];
                        if (v === '3.8 Years') KNOWN_PATTERNS[k] = '4';
                        else if (v === '4 Years') KNOWN_PATTERNS[k] = '4';
                        else if (v === '2 Years') KNOWN_PATTERNS[k] = '2';
                        else if (typeof v === 'string' && v.startsWith('3.8 Years')) KNOWN_PATTERNS[k] = '4';
                    }});
                    
                    // Override salary/CTC to numeric values for LinkedIn text inputs
                    const salaryKeys = [
                        'salary range', 'current salary range', 'expected salary range', 
                        'annual salary', 'ctc range', 'current ctc', 'expected ctc',
                        'expected annual ctc in inr', 'expected annual ctc', 'expected ctc in inr', 'expected ctc inr',
                        'current salary', 'expected salary', 'current annual salary',
                        'what is your current annual salary', 'what is your current annual salary?',
                        'expected annual salary', 'what is your expected annual salary', 'what is your expected annual salary?',
                        'what is your current salary?', 'what is your expected salary?',
                        'what is your current ctc', 'what is your current ctc?',
                        'gross salary', 'gross current salary', 'gross expected salary', 'salary expectations'
                    ];
                    salaryKeys.forEach(k => {{
                        if (KNOWN_PATTERNS[k]) {{
                            // Use plain numeric values (13.5, 24) for LinkedIn text inputs - NOT full INR values
                            if (k.includes('current') || k.includes('gross current') || k === 'annual salary' || k === 'salary range' || k === 'ctc range') {{
                                KNOWN_PATTERNS[k] = '13.5';
                            }} else {{
                                KNOWN_PATTERNS[k] = '24';
                            }}
                        }}
                    }});
                    
                    // Override notice period to numeric days for LinkedIn
                    const noticeKeys = [
                        'notice period', 'what is your notice period', 'what is your notice period?',
                        'what is your notice period ?', 'notice period in days', 'notice period days',
                        'serving notice', 'serving notice period', 'are you serving notice', 'currently serving notice'
                    ];
                    noticeKeys.forEach(k => {{
                        if (KNOWN_PATTERNS[k]) KNOWN_PATTERNS[k] = '30';
                    }});
                }}

                const MAX_RETRIES = 3;
                
                // 2. SHARED UTILS (Restored from Legacy)
                // NOTE: sleep removed - use Python's asyncio.sleep() between evaluate calls instead
                // const sleep = (ms) => new Promise(r => setTimeout(r, ms));  // REMOVED - causes SyntaxError
                const isVisible = (elem) => !!(elem && (elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length));

                // Keyword extraction: normalize synonyms, strip stop words
                const extractKeywords = (text) => {{
                    const words = text.replace(/[^\w\s]/g, ' ').toLowerCase().split(/\s+/);
                    const normalized = words.map(w => SYNONYMS[w] || w);
                    return new Set(normalized.filter(w => !STOP_WORDS_SET.has(w) && w.length > 1));
                }};
                
                // Set intersection helper
                const setIntersect = (a, b) => {{
                    const result = new Set();
                    for (const item of a) {{ if (b.has(item)) result.add(item); }}
                    return result;
                }};

                // Two-pass Fuzzy Matcher implementation
                const fuzzyMatch = (question) => {{
                    if (!question) return null;
                    const qLower = question.toLowerCase().trim();
                    let bestMatch = null;
                    let bestKeyLen = 0;
                    
                    // Sort patterns by key length (descending) to prioritize longer, more specific matches
                    const sortedPatterns = Object.entries(KNOWN_PATTERNS).sort((a, b) => b[0].length - a[0].length);
                    
                    // --- PASS 1: Exact / Substring match (fast path) ---
                    for (const [key, val] of sortedPatterns) {{
                        const keyLower = key.toLowerCase();
                        if (qLower === keyLower) return val;
                        if (qLower.includes(keyLower)) {{
                            // Anti-collision for generic words
                            if (keyLower === 'years' && (qLower.includes('salary') || qLower.includes('ctc') || qLower.includes('pay') || qLower.includes('inr'))) continue;
                            if (key.length > bestKeyLen) {{
                                bestMatch = val;
                                bestKeyLen = key.length;
                            }}
                        }}
                    }}
                    
                    // --- PASS 2: Keyword overlap (fallback if Pass 1 found nothing) ---
                    if (!bestMatch) {{
                        const qKeywords = extractKeywords(qLower);
                        if (qKeywords.size > 0) {{
                            let bestScore = 0;
                            for (const [key, val] of sortedPatterns) {{
                                const kKeywords = extractKeywords(key);
                                if (kKeywords.size === 0) continue;
                                const overlap = setIntersect(qKeywords, kKeywords);
                                const score = overlap.size / Math.max(qKeywords.size, kKeywords.size);
                                if (score > bestScore && score >= 0.5) {{
                                    bestScore = score;
                                    bestMatch = val;
                                }}
                            }}
                        }}
                    }}
                    
                    // --- PASS 3: Smart salary/experience/notice disambiguation (safety net) ---
                    if (bestMatch) {{
                        const isSalaryQ = /salary|ctc|pay|compensation|package|remuneration/.test(qLower);
                        const isExpQ = /experience|years|year|months|exp\.?\b/.test(qLower) && !isSalaryQ;
                        const isNoticeQ = /notice\s*period|serving\s*notice|lwd/.test(qLower);
                        
                        if (isSalaryQ && window.location.hostname.includes('linkedin')) {{
                            bestMatch = qLower.includes('current') ? '1350000' : '2400000';
                        }}
                    }}
                    
                    return bestMatch;
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
                
                // Helper: Find best matching radio button for experience ranges
                const findBestRadioMatch = (answer, radios) => {{
                    if (!answer || !radios || radios.length === 0) return null;
                    
                    const ans = answer.toLowerCase();
                    let bestRadio = null;
                    let bestScore = -1;
                    
                    // Extract years from answer for better matching
                    const yearMatch = answer.match(/(\d+(?:\.\d+)?)/);
                    const answerYears = yearMatch ? parseFloat(yearMatch[1]) : 0;
                    
                    for (const radio of radios) {{
                        const label = radio.closest('label')?.innerText || radio.parentElement?.innerText || '';
                        const lowerLabel = label.toLowerCase();
                        let score = 0;
                        
                        // Exact text match
                        if (lowerLabel.includes(ans) || ans.includes(lowerLabel)) {{
                            score = 100;
                        }}
                        // Check for "yes" or "serving" for Yes/No questions
                        else if ((lowerLabel.includes('yes') || lowerLabel.includes('serving')) && 
                                (ans.includes('yes') || ans.includes('serving'))) {{
                            score = 90;
                        }}
                        // Experience range matching
                        else {{
                            // Look for range patterns like "0-2", "2-5", "3-5", etc.
                            const rangeMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                            if (rangeMatch && answerYears > 0) {{
                                const min = parseFloat(rangeMatch[1]);
                                const max = parseFloat(rangeMatch[2]);
                                
                                if (answerYears >= min && answerYears <= max) {{
                                    // Calculate how centered the answer is in the range
                                    const rangeSize = max - min;
                                    const offset = Math.abs(answerYears - (min + max) / 2);
                                    score = Math.max(0, 80 - (offset / rangeSize * 20));
                                }}
                            }}
                            // Single year match (e.g., "3+", "2+", "5")
                            else if (answerYears > 0) {{
                                // First try to match "X+" or "X +" patterns (like "3+", "3 +")
                                const plusMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*\+/);
                                if (plusMatch) {{
                                    const radioYears = parseFloat(plusMatch[1]);
                                    // "3+" means 3 or more, so if answer is >=3, it's a good match
                                    if (answerYears >= radioYears) {{
                                        score = 90;
                                    }} else {{
                                        // Answer is less than X+, still calculate score
                                        const diff = Math.abs(answerYears - radioYears);
                                        score = Math.max(0, 85 - diff * 10);
                                    }}
                                }} else {{
                                    // Try simple number match
                                    const singleYearMatch = lowerLabel.match(/(\d+(?:\.\d+)?)/);
                                    if (singleYearMatch) {{
                                        const radioYears = parseFloat(singleYearMatch[1]);
                                        const diff = Math.abs(answerYears - radioYears);
                                        score = Math.max(0, 90 - diff * 10);
                                    }}
                                }}
                            }}
                        }}
                        
                        if (score > bestScore) {{
                            bestScore = score;
                            bestRadio = radio;
                        }}
                    }}
                    
                    return bestRadio;
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

                // Helper: Query selector that can penetrate Shadow DOM
                const queryDeep = (selector, root = document) => {{
                    let match = root.querySelector(selector);
                    if (match) return match;
                    const hosts = root.querySelectorAll('*');
                    for (const host of hosts) {{
                        if (host.shadowRoot) {{
                            match = queryDeep(selector, host.shadowRoot);
                            if (match) return match;
                        }}
                    }}
                    return null;
                }};

                const queryAllDeep = (selector, root = document, results = []) => {{
                    root.querySelectorAll(selector).forEach(el => results.push(el));
                    root.querySelectorAll('*').forEach(el => {{
                        if (el.shadowRoot) queryAllDeep(selector, el.shadowRoot, results);
                    }});
                    return results;
                }};

                // ============================================================
                // LINKEDIN LOGIC (CLEAN REWRITE FOR 2025-2026)
                // Handles obfuscated classes and dynamic DOM structure
                // ============================================================
                if (isLinkedIn) {{
                    console.log('=== LINKEDIN AUTOMATION STARTED ===');
                    
                    // Helper: Find elements by text content (Shadow aware)
                    const findByText = (selector, text, exact = false) => {{
                        const elements = queryAllDeep(selector);
                        const searchText = text.toLowerCase();
                        return Array.from(elements).find(el => {{
                            const elText = el.innerText.toLowerCase();
                            return exact ? elText === searchText : elText.includes(searchText);
                        }});
                    }};
                    
                    // Helper: Find Easy Apply button on job details page
                    const findEasyApplyButton = () => {{
                        console.log('Looking for Easy Apply button...');
                        // 1. By class and id (most reliable - verified 2026)
                        let btn = queryDeep('button.jobs-apply-button') || queryDeep('#jobs-apply-button-id');
                        if (btn && isVisible(btn)) return btn;
                        
                        // 2. By aria-label (found during inspection)
                        btn = queryDeep('button[aria-label*="Easy Apply"], a[aria-label*="Easy Apply"]');
                        if (btn && isVisible(btn)) return btn;
                        
                        // 3. By data-view-name (LinkedIn uses <button> not <a> as of 2026)
                        btn = queryDeep('button[data-view-name="job-apply-button"], button.top-card-layout__cta--primary');
                        if (btn && isVisible(btn)) return btn;

                        // 4. By text search (broadest fallback)
                        btn = findByText('button', 'easy apply') || findByText('a', 'easy apply');
                        if (btn && isVisible(btn)) return btn;

                        return null;
                    }};

                    // Helper: Fill LinkedIn form fields
                    const handleLinkedInForm = (modal) => {{
                        console.log('Filling LinkedIn form fields (Shadow aware)...');
                        const formResults = [];
                        
                        // Helper: Check if a field is already filled
                        const isFieldPreFilled = (element) => {{
                            if (!element) return false;
                            if (element.disabled) return true;
                            // For checkboxes/radios, readOnly is not an applicable check for filled state

                            const tagName = element.tagName.toLowerCase();
                            const value = element.value ? element.value.trim() : "";

                            if (tagName === 'input' || tagName === 'textarea') {{
                                // if it's radio or checkbox, it's prefilled if checked
                                if (element.type === 'radio' || element.type === 'checkbox') return element.checked;
                                return value.length > 0;
                            }}

                            if (tagName === 'select') {{
                                // LinkedIn uses "Select an option" as placeholder.
                                const isPlaceholder = !value || value === "" || value.toLowerCase().includes("select an option") || element.options[element.selectedIndex]?.text.toLowerCase().includes("select");
                                return !isPlaceholder;
                            }}
                            
                            // Custom elements with aria-valuenow or aria-checked
                            if (element.hasAttribute('aria-valuenow')) {{
                                return element.getAttribute('aria-valuenow').trim().length > 0;
                            }}
                            if (element.hasAttribute('aria-checked')) {{
                                return element.getAttribute('aria-checked') === 'true';
                            }}
                            
                            return false;
                        }};
                        
                        // Helper: Safely fill React controlled inputs
                        const fillReactInput = (element, value) => {{
                            if (!element) return false;
                            const previousValue = element.value;
                            
                            // 1. Try React native setter
                            try {{
                                const proto = element.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                                const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                                if (nativeSetter) {{
                                    nativeSetter.call(element, value);
                                }} else {{
                                    element.value = value;
                                }}
                            }} catch(e) {{
                                element.value = value;
                            }}
                            
                            // 2. Dispatch events
                            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            element.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                            
                            // 3. Fallback for stubborn frameworks
                            if (element.value !== value && Reflect.has(element, 'value')) {{
                                Reflect.set(element, 'value', value);
                                element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            }}
                            
                            return element.value !== previousValue || element.value === value;
                        }};

                        // 0. FIRST: Check for visible autocomplete/typeahead dropdown options
                        // LinkedIn renders these in portals outside the modal, so search entire document
                        // This MUST run before anything else to select from already-open dropdowns
                        {{
                            const dropdownSelectors = '.typeahead-input__dropdown-item, [role="option"], .artdeco-typeahead__result, [data-test-typeahead-item], li[class*="typeahead"], .basic-typeahead__selectable';
                            const allDropdownOpts = document.querySelectorAll(dropdownSelectors);
                            console.log('Pre-check: scanning for visible autocomplete options:', allDropdownOpts.length);
                            
                            for (const option of allDropdownOpts) {{
                                if (option.offsetParent !== null) {{
                                    const text = option.innerText.trim();
                                    if (text && text.length > 2 && !text.toLowerCase().includes('select')) {{
                                        console.log('CLICKING VISIBLE AUTOCOMPLETE OPTION:', text);
                                        option.click();
                                        return 'LINKEDIN_AUTOCOMPLETE_SELECTED|' + JSON.stringify([{{question: 'autocomplete', answer: text, inputType: 'typeahead'}}]);
                                    }}
                                }}
                            }}
                        }}

                        // 1. Handle text/numeric inputs
                        const textInputs = queryAllDeep('input[type="text"], input[type="number"], textarea', modal);
                        for (const input of textInputs) {{
                            const labelText = input.closest('.fb-dash-form-element')?.querySelector('label')?.innerText || 
                                            queryDeep(`label[for="${{input.id}}"]`, modal)?.innerText || 
                                            input.getAttribute('aria-label') || '';
                            const lowerLabel = labelText.toLowerCase();
                            const isLocationField = lowerLabel.includes('location') || lowerLabel.includes('city');
                            
                            // Special handling: Location fields that have text but show validation errors
                            // LinkedIn requires selecting from autocomplete dropdown, not just text
                            if (isLocationField && isFieldPreFilled(input) && isVisible(input)) {{
                                // Check if there's a visible validation error on this field
                                const parentContainer = input.closest('.fb-dash-form-element') || input.closest('.jobs-easy-apply-form-section__question') || input.parentElement?.parentElement;
                                const hasError = parentContainer && (parentContainer.querySelector('.artdeco-inline-feedback--error') || parentContainer.querySelector('.fb-dash-form-element__error-field'));
                                const globalError = queryDeep('.artdeco-inline-feedback--error', modal);
                                
                                if (hasError || globalError) {{
                                    console.log('Location field has text but validation error — re-triggering autocomplete for:', labelText, 'current value:', input.value);
                                    const currentVal = input.value;
                                    
                                    // Try a different strategy: click the input field multiple times to open dropdown
                                    input.click();
                                    
                                    // Dispatch multiple events to trigger dropdown
                                    input.focus();
                                    input.dispatchEvent(new Event('click', {{ bubbles: true }}));
                                    input.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('focus', {{ bubbles: true }}));
                                    input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }}));
                                    input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }}));
                                    
                                    return 'LINKEDIN_LOCATION_RETRIGGERED';
                                }}
                                continue;  // location pre-filled and no error — skip
                            }}
                            
                            if (!isVisible(input) || isFieldPreFilled(input)) continue;
                            
                            // Check if input expects numeric values only
                            const isNumericInput = input.type === 'number' || 
                                                  input.getAttribute('inputmode') === 'numeric' ||
                                                  input.getAttribute('pattern')?.includes('\\d') ||
                                                  input.className?.toLowerCase().includes('number') ||
                                                  input.className?.toLowerCase().includes('decimal') ||
                                                  (labelText && /how many years|total years|relevant experience|experience with|decimal number|numeric/i.test(labelText));
                            
                            if (labelText) {{
                                let answer = fuzzyMatch(labelText);
                                
                                // If it's a numeric input, extract just the number from the answer
                                if (answer && isNumericInput) {{
                                    const numericMatch = answer.match(/(\d+\.?\d*)/);
                                    if (numericMatch) {{
                                        answer = numericMatch[1];
                                        console.log('Extracted numeric value for number field:', answer);
                                    }}
                                }}
                                
                                if (answer) {{
                                    console.log('Filling text field:', labelText, 'with:', answer);
                                    
                                    fillReactInput(input, answer);
                                    
                                    formResults.push({{ question: labelText, answer: answer, inputType: 'text' }});
                                    
                                    // If this is a location field, trigger autocomplete dropdown
                                    if (isLocationField) {{
                                        console.log('Location field filled — triggering autocomplete dropdown...');
                                        input.focus();
                                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        input.dispatchEvent(new Event('focus', {{ bubbles: true }}));
                                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'ArrowDown', bubbles: true }}));
                                        
                                        // Keep the input visible and focused for dropdown to appear
                                        input.scrollIntoView({{block: 'center', behavior: 'instant'}});
                                        
                                        return 'LINKEDIN_LOCATION_FILLED_WAITING_DROPDOWN';
                                    }}
                                }}
                            }}
                        }}

                        // 2. Handle Select elements (native and custom LinkedIn dropdowns)
                        const nativeSelects = queryAllDeep('select', modal);
                        const customDropdowns = queryAllDeep('[role="combobox"], .jobs-easy-apply-form-section__dropdown, button[aria-expanded], [data-test-text-entity-list-form-select]', modal);
                        
                        // Process native <select> elements
                        for (const select of nativeSelects) {{
                            if (!isVisible(select) || isFieldPreFilled(select)) continue;
                            
                            const labelText = select.closest('.fb-dash-form-element')?.querySelector('label')?.innerText || 
                                            queryDeep(`label[for="${{select.id}}"]`, modal)?.innerText ||
                                            select.getAttribute('aria-label') || '';
                            
                            const lowerLabel = labelText.toLowerCase();
                            
                            // SPECIAL CASE: For "learn about" / "hear about" / "source" questions, select ANY first option
                            const isLearnAboutQuestion = lowerLabel.includes('learn about') || 
                                                        lowerLabel.includes('hear about') || 
                                                        lowerLabel.includes('how did you') ||
                                                        lowerLabel.includes('where did you') ||
                                                        lowerLabel.includes('source');
                            
                            if (isLearnAboutQuestion) {{
                                console.log('Learn about question detected in native select - selecting first non-placeholder option');
                                const options = Array.from(select.options);
                                // Skip first option if it's a placeholder
                                const firstRealOption = options.find(o => {{
                                    const text = o.text.toLowerCase();
                                    return !text.includes('select') && !text.includes('choose') && text.trim().length > 0;
                                }});
                                
                                if (firstRealOption) {{
                                    select.value = firstRealOption.value;
                                    select.selectedIndex = firstRealOption.index;
                                    select.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    select.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                    console.log('Selected first option:', firstRealOption.text);
                                    formResults.push({{ question: labelText, answer: firstRealOption.text, inputType: 'select' }});
                                }}
                                continue;
                            }}
                            
                            if (labelText) {{
                                const answer = fuzzyMatch(labelText);
                                
                                // Determine if we should attempt to select "Yes" based on keywords
                                const isYesNoQuestion = lowerLabel.includes('experience') || 
                                                      lowerLabel.includes('developer') ||
                                                      lowerLabel.includes('comfortable') ||
                                                      lowerLabel.includes('willing');
                                
                                if (answer || isYesNoQuestion) {{
                                    const options = Array.from(select.options).map(o => ({{ text: o.text, value: o.value, index: o.index }}));
                                    let bestOpt = findBestMatch(answer, options);
                                    
                                    // Fallback: If answer is numeric (e.g. "3.8 Years") but options are Yes/No
                                    if ((!bestOpt && answer) && (lowerLabel.includes('experience') || lowerLabel.includes('year'))) {{
                                        const isYesNo = options.some(o => o.text.toLowerCase().includes('yes')) && 
                                                      options.some(o => o.text.toLowerCase().includes('no'));
                                        
                                        if (isYesNo) {{
                                            // Extract required years from question
                                            // Matches "3+ years", "minimum 3 years", "at least 3 years"
                                            const reqMatch = labelText.match(/(\d+)\+?\s*(?:years|yrs)/i);
                                            const reqYears = reqMatch ? parseFloat(reqMatch[1]) : 0;
                                            
                                            // Extract users years from answer
                                            const ansMatch = answer.match(/(\d+(?:\.\d+)?)/);
                                            const ansYears = ansMatch ? parseFloat(ansMatch[1]) : 0;
                                            
                                            console.log(`Experience Logic: Required ${{reqYears}}, User ${{ansYears}}`);
                                            
                                            if (ansYears >= reqYears) {{
                                                bestOpt = options.find(o => o.text.toLowerCase().includes('yes'));
                                            }} else {{
                                                // If user has less experience, we might want to lie (aggressive) or be honest
                                                // For now, let's be aggressive if it's close, or default Yes if parsing failed
                                                bestOpt = options.find(o => o.text.toLowerCase().includes('yes')); 
                                            }}
                                        }}
                                    }}
                                    
                                    // Fallback 2: Implicit Yes/No for Developer/Experience questions where fuzzyMatch returned null
                                    if (!bestOpt && !answer && isYesNoQuestion) {{
                                         bestOpt = options.find(o => o.text.toLowerCase().includes('yes'));
                                         if (bestOpt) console.log('Defaulting native select to Yes for:', labelText);
                                    }}

                                    if (bestOpt) {{
                                        console.log('Selecting native dropdown:', labelText, 'with:', bestOpt.text);
                                        
                                        // Robust selection logic
                                        select.value = bestOpt.value;
                                        if (select.value !== bestOpt.value) {{
                                            select.selectedIndex = bestOpt.index;
                                        }}
                                        
                                        select.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        select.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                        
                                        formResults.push({{ question: labelText, answer: bestOpt.text, inputType: 'select' }});
                                    }}
                                }}
                                
                                // AGGRESSIVE FALLBACK 3: If select still not filled and has Yes/No options, default to Yes
                                if (!isFieldPreFilled(select)) {{
                                    const options = Array.from(select.options).map(o => ({{ text: o.text, value: o.value, index: o.index }}));
                                    const hasYesNo = options.some(o => o.text.toLowerCase().includes('yes')) && 
                                                     options.some(o => o.text.toLowerCase().includes('no'));
                                    
                                    if (hasYesNo) {{
                                        const yesOption = options.find(o => o.text.toLowerCase().includes('yes'));
                                        if (yesOption) {{
                                            console.log('AGGRESSIVE FALLBACK: Defaulting to Yes for unfilled select:', labelText);
                                            select.value = yesOption.value;
                                            if (select.value !== yesOption.value) {{
                                                select.selectedIndex = yesOption.index;
                                            }}
                                            
                                            select.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            select.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                            
                                            formResults.push({{ question: labelText, answer: yesOption.text, inputType: 'select-aggressive' }});
                                        }}
                                    }}
                                }}
                            }}
                        }}
                        
                        // Process custom LinkedIn dropdowns (comboboxes)
                        for (const dropdown of customDropdowns) {{
                            if (!isVisible(dropdown) || dropdown.tagName === 'SELECT') continue;
                            
                            // Check if dropdown needs filling
                            const dropdownText = dropdown.innerText || dropdown.textContent || '';
                            const isUnselected = dropdownText.toLowerCase().includes('select an option') || 
                                               dropdownText.toLowerCase().includes('select') ||
                                               !dropdown.getAttribute('aria-expanded');
                            
                            if (!isUnselected) {{
                                // console.log('Skipping pre-filled custom dropdown:', dropdownText);
                                continue;
                            }}
                            
                            // Get label text from parent element
                            const labelText = dropdown.closest('.fb-dash-form-element')?.querySelector('label')?.innerText || 
                                            dropdown.closest('.jobs-easy-apply-form-section__question')?.querySelector('label')?.innerText ||
                                            dropdown.getAttribute('aria-label') || 
                                            dropdown.closest('div')?.querySelector('label')?.innerText || '';
                            
                            const lowerLabel = labelText.toLowerCase();
                            
                            // SPECIAL CASE: For "learn about" / "hear about" / "source" questions, select ANY first option
                            const isLearnAboutQuestion = lowerLabel.includes('learn about') || 
                                                        lowerLabel.includes('hear about') || 
                                                        lowerLabel.includes('how did you') ||
                                                        lowerLabel.includes('where did you') ||
                                                        lowerLabel.includes('source');
                            
                            if (isLearnAboutQuestion) {{
                                console.log('Learn about question detected - selecting first available option');
                                dropdown.click();
                                
                                setTimeout(() => {{
                                    const allOptions = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, .jobs-easy-apply-form-element__dropdown-option, li');
                                    for (const option of allOptions) {{
                                        const text = option.innerText.trim();
                                        const lowerText = text.toLowerCase();
                                        if (text && !lowerText.includes('select') && !lowerText.includes('choose') && text.length > 2) {{
                                            console.log('Selected first option for learn about question:', text);
                                            option.click();
                                            formResults.push({{ question: labelText, answer: text, inputType: 'custom-dropdown' }});
                                            break;
                                        }}
                                    }}
                                }}, 200);
                                
                                return 'LINKEDIN_FORM_FILLING_CUSTOM_DROPDOWN';
                            }}
                            
                            if (labelText) {{
                                const answer = fuzzyMatch(labelText);
                                // For Yes/No questions, default to "Yes" if no specific answer found
                                const isYesNoQuestion = lowerLabel.includes('experience') || 
                                                      lowerLabel.includes('developer');
                                
                                // SMART EXPERIENCE CHECK
                                let calculatedShouldSelectYes = false;
                                if (answer && (lowerLabel.includes('experience') || lowerLabel.includes('year'))) {{
                                    const reqMatch = labelText.match(/(\d+)\+?\s*(?:years|yrs)/i);
                                    const reqYears = reqMatch ? parseFloat(reqMatch[1]) : 0;
                                    const ansMatch = answer.match(/(\d+(?:\.\d+)?)/);
                                    const ansYears = ansMatch ? parseFloat(ansMatch[1]) : 0;
                                    if (ansYears >= reqYears) calculatedShouldSelectYes = true;
                                }}

                                const shouldSelectYes = calculatedShouldSelectYes || (isYesNoQuestion && (!answer || answer.toLowerCase().includes('yes')));
                                
                                if (answer || shouldSelectYes) {{
                                    console.log('Clicking custom dropdown:', labelText);
                                    dropdown.click();
                                    
                                    // Wait briefly for dropdown options to appear
                                    setTimeout(() => {{
                                        const yesOption = findByText('[role="option"], li', 'yes', true) ||
                                                        findByText('span', 'yes', true);
                                        const noOption = findByText('[role="option"], li', 'no', true) ||
                                                        findByText('span', 'no', true);
                                        
                                        if (shouldSelectYes && yesOption) {{
                                            console.log('Selecting Yes for:', labelText);
                                            yesOption.click();
                                            formResults.push({{ question: labelText, answer: 'Yes', inputType: 'custom-dropdown' }});
                                        }} else if (!shouldSelectYes && answer && answer.toLowerCase().includes('no') && noOption) {{
                                            console.log('Selecting No for:', labelText);
                                            noOption.click();
                                            formResults.push({{ question: labelText, answer: 'No', inputType: 'custom-dropdown' }});
                                        }} else if (yesOption) {{
                                            console.log('Defaulting to Yes for:', labelText);
                                            yesOption.click();
                                            formResults.push({{ question: labelText, answer: 'Yes', inputType: 'custom-dropdown' }});
                                        }}
                                    }}, 100);
                                    
                                    return 'LINKEDIN_FORM_FILLING_CUSTOM_DROPDOWN';
                                }}
                            }}
                            
                            // AGGRESSIVE FALLBACK: For unfilled custom dropdowns with Yes/No options
                            const currentText = dropdown.innerText || dropdown.textContent || '';
                            const stillUnselected = currentText.toLowerCase().includes('select an option') || 
                                                   currentText.toLowerCase().includes('select');
                            
                            if (stillUnselected && labelText) {{
                                console.log('AGGRESSIVE FALLBACK: Checking custom dropdown for Yes/No:', labelText);
                                dropdown.click();
                                
                                setTimeout(() => {{
                                    const allOptions = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, li');
                                    let hasYes = false;
                                    let hasNo = false;
                                    let yesOption = null;
                                    
                                    for (const option of allOptions) {{
                                        const text = option.innerText.trim().toLowerCase();
                                        if (text === 'yes' || text.includes('yes')) {{
                                            hasYes = true;
                                            yesOption = option;
                                        }}
                                        if (text === 'no' || text.includes('no')) hasNo = true;
                                    }}
                                    
                                    if (hasYes && hasNo && yesOption) {{
                                        console.log('AGGRESSIVE FALLBACK: Selecting Yes for custom dropdown:', labelText);
                                        yesOption.click();
                                        formResults.push({{ question: labelText, answer: 'Yes', inputType: 'custom-dropdown-aggressive' }});
                                    }}
                                }}, 150);
                                
                                return 'LINKEDIN_FORM_FILLING_CUSTOM_DROPDOWN_AGGRESSIVE';
                            }}
                        }}

                        // 3. Handle Radio buttons (e.g., Yes/No questions)
                        const fieldsets = queryAllDeep('fieldset', modal);
                        for (const fieldset of fieldsets) {{
                            const legend = fieldset.querySelector('legend')?.innerText || '';
                            const radios = Array.from(fieldset.querySelectorAll('input[type="radio"]'));
                            
                            if (legend && radios.length > 0 && !radios.some(r => r.checked)) {{
                                const answer = fuzzyMatch(legend);
                                if (answer) {{
                                    const bestRadio = findBestRadioMatch(answer, radios);
                                    if (bestRadio) {{
                                        console.log('Clicking radio:', legend, 'with:', bestRadio.id);
                                        bestRadio.click();
                                        bestRadio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        formResults.push({{ question: legend, answer: answer, inputType: 'radio' }});
                                    }}
                                }}
                            }}
                        }}
                        
                        // 3.1b Handle standalone Radio buttons (not inside fieldsets)
                        // Many forms have radio buttons directly in divs or other containers
                        const allRadios = queryAllDeep('input[type="radio"]', modal);
                        const radioGroups = {{}};
                        
                        // Group radios by name attribute
                        for (const radio of allRadios) {{
                            const name = radio.name;
                            if (!name) continue;  // Skip radios without names
                            if (!radioGroups[name]) {{
                                radioGroups[name] = [];
                            }}
                            radioGroups[name].push(radio);
                        }}
                        
                        // Process each radio group
                        for (const [name, radios] of Object.entries(radioGroups)) {{
                            // Skip if any radio in group is already checked
                            if (radios.some(r => r.checked)) continue;
                            
                            // Find label/question text for this group
                            let questionText = '';
                            const firstRadio = radios[0];
                            
                            // Try to find label text
                            const parentLabel = firstRadio.closest('label');
                            if (parentLabel) {{
                                questionText = parentLabel.innerText;
                            }} else {{
                                // Look for preceding text or parent container text
                                const container = firstRadio.closest('div[class*="question"], div[class*="field"], .form-group');
                                if (container) {{
                                    // Get text from the container, excluding the radio labels
                                    const textNodes = Array.from(container.childNodes)
                                        .filter(n => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'INPUT' && n.tagName !== 'LABEL'))
                                        .map(n => n.textContent || n.innerText)
                                        .join(' ')
                                        .trim();
                                    questionText = textNodes;
                                }}
                            }}
                            
                            // Also try to get text from aria-label or aria-labelledby
                            if (!questionText && firstRadio.getAttribute('aria-labelledby')) {{
                                const labelEl = document.getElementById(firstRadio.getAttribute('aria-labelledby'));
                                if (labelEl) questionText = labelEl.innerText;
                            }}
                            
                            if (!questionText && firstRadio.getAttribute('aria-label')) {{
                                questionText = firstRadio.getAttribute('aria-label');
                            }}
                            
                            // Try to get text from name attribute if all else fails
                            if (!questionText && name && !name.match(/^[0-9]+$/)) {{
                                questionText = name.replace(/[_-]/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();
                                console.log('Inferred question text from radio name:', questionText);
                            }}
                            
                            // Try to find answer for this question
                            if (questionText) {{
                                const answer = fuzzyMatch(questionText);
                                if (answer) {{
                                    const bestRadio = findBestRadioMatch(answer, radios);
                                    if (bestRadio) {{
                                        console.log('Clicking standalone radio:', questionText.substring(0, 50), 'with:', bestRadio.value || bestRadio.id);
                                        bestRadio.click();
                                        bestRadio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        formResults.push({{ question: questionText.substring(0, 100), answer: answer, inputType: 'radio' }});
                                    }} else {{
                                        // No match found - default to first option for Yes/No questions
                                        const yesRadio = radios.find(r => {{
                                            const label = r.closest('label')?.innerText || r.value || '';
                                            return label.toLowerCase().includes('yes');
                                        }});
                                        if (yesRadio) {{
                                            console.log('Defaulting to Yes for:', questionText.substring(0, 50));
                                            yesRadio.click();
                                            yesRadio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            formResults.push({{ question: questionText.substring(0, 100), answer: 'Yes', inputType: 'radio' }});
                                        }}
                                    }}
                                }} else {{
                                    // No fuzzy match - check if it's a Yes/No question and default to Yes
                                    const isYesNo = radios.length === 2 && 
                                        radios.some(r => (r.value || '').toLowerCase() === 'yes') &&
                                        radios.some(r => (r.value || '').toLowerCase() === 'no');
                                    
                                    if (isYesNo) {{
                                        const yesRadio = radios.find(r => (r.value || '').toLowerCase() === 'yes');
                                        if (yesRadio) {{
                                            console.log('Defaulting Yes/No question to Yes:', questionText.substring(0, 50) || 'Unknown question');
                                            yesRadio.click();
                                            yesRadio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            formResults.push({{ question: questionText.substring(0, 100) || 'Yes/No question', answer: 'Yes', inputType: 'radio' }});
                                        }}
                                    }}
                                }}
                            }} else {{
                                // No question text found - check if it's a Yes/No and default to Yes
                                const isYesNo = radios.length === 2 && 
                                    radios.some(r => (r.value || '').toLowerCase() === 'yes') &&
                                    radios.some(r => (r.value || '').toLowerCase() === 'no');
                                
                                if (isYesNo) {{
                                    const yesRadio = radios.find(r => (r.value || '').toLowerCase() === 'yes');
                                    if (yesRadio && !yesRadio.checked) {{
                                        console.log('Selecting Yes for unlabeled Yes/No question');
                                        yesRadio.click();
                                        yesRadio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        formResults.push({{ question: 'Yes/No question (no label found)', answer: 'Yes', inputType: 'radio' }});
                                    }}
                                }}
                            }}
                        }}
                        
                        // 3.2 Handle Checkboxes (consent, privacy policy, etc.)
                        // Search for all checkboxes including those with specific LinkedIn classes
                        const checkboxes = queryAllDeep('input[type="checkbox"], .fb-form-element__checkbox', modal);
                        console.log('Found', checkboxes.length, 'checkboxes in modal');
                        
                        for (const checkbox of checkboxes) {{
                            if (!isVisible(checkbox) || checkbox.checked) continue;
                            
                            // Get label text for the checkbox - try multiple methods
                            let labelText = '';
                            
                            // Method 1: Check for aria-labelledby
                            const labelledBy = checkbox.getAttribute('aria-labelledby');
                            if (labelledBy) {{
                                const labelEl = document.getElementById(labelledBy);
                                if (labelEl) labelText = labelEl.innerText;
                            }}
                            
                            // Method 2: Check for aria-label
                            if (!labelText) {{
                                labelText = checkbox.getAttribute('aria-label') || '';
                            }}
                            
                            // Method 3: Check for id and find matching label
                            if (!labelText && checkbox.id) {{
                                const label = queryDeep(`label[for="${{checkbox.id}}"]`, modal);
                                if (label) labelText = label.innerText;
                            }}
                            
                            // Method 4: Look for label in parent fieldset (LinkedIn specific structure)
                            if (!labelText) {{
                                const fieldset = checkbox.closest('fieldset');
                                if (fieldset) {{
                                    // Get text from legend or the entire fieldset
                                    const legend = fieldset.querySelector('legend');
                                    if (legend) {{
                                        labelText = legend.innerText;
                                    }} else {{
                                        labelText = fieldset.innerText.substring(0, 300);
                                    }}
                                }}
                            }}
                            
                            // Method 5: Try to find label by data-test attribute (LinkedIn specific)
                            if (!labelText) {{
                                const parent = checkbox.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question, [data-test-form-element]');
                                if (parent) {{
                                    // Look for label with data-test-text-selectable-option__label
                                    const label = parent.querySelector('[data-test-text-selectable-option__label], label');
                                    if (label) {{
                                        labelText = label.innerText || label.getAttribute('data-test-text-selectable-option__label') || '';
                                    }}
                                    // If still no label, get all text from parent
                                    if (!labelText) {{
                                        labelText = parent.innerText.substring(0, 300);
                                    }}
                                }}
                            }}
                            
                            // Method 6: Check sibling labels
                            if (!labelText) {{
                                const parent = checkbox.parentElement;
                                if (parent) {{
                                    const siblingLabel = parent.querySelector('label');
                                    if (siblingLabel) {{
                                        labelText = siblingLabel.innerText;
                                    }}
                                }}
                            }}
                            
                            console.log('Checkbox label text found:', labelText.substring(0, 100));
                            const lowerLabel = labelText.toLowerCase();
                            
                            // Check if this is a privacy/consent checkbox
                            const isConsentCheckbox = lowerLabel.includes('consent') || 
                                                     lowerLabel.includes('privacy') || 
                                                     lowerLabel.includes('agree') ||
                                                     lowerLabel.includes('declare') ||
                                                     lowerLabel.includes('i consent') ||
                                                     lowerLabel.includes('read and agree');
                            
                            let shouldCheck = isConsentCheckbox;
                            
                            // If it's not a consent checkbox, try to fuzzy match to see if it's a skill/tech question
                            // where the UI is a list of checkboxes for skills (e.g. POSTGRES, Spring Boot)
                            if (!shouldCheck && labelText) {{
                                const skillMatch = fuzzyMatch(labelText);
                                // Check if user has experience or positive response
                                if (skillMatch && (
                                    skillMatch.toLowerCase() === 'yes' || 
                                    /^\d+/.test(skillMatch) || 
                                    skillMatch.toLowerCase().includes('year') ||
                                    skillMatch.toLowerCase().includes('month') ||
                                    // if it's a known tech stack response string
                                    skillMatch.toLowerCase().includes(labelText.toLowerCase())
                                )) {{
                                    shouldCheck = true;
                                    console.log('Skill found for checkbox:', labelText, 'matched as:', skillMatch);
                                }}
                            }}
                            
                            if (shouldCheck) {{
                                console.log('Checking checkbox:', labelText.substring(0, 50));
                                checkbox.click();
                                checkbox.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                formResults.push({{ question: labelText, answer: 'Checked', inputType: 'checkbox' }});
                            }} else {{
                                console.log('Skipping checkbox - not consent/privacy related or no matching skill:', labelText.substring(0, 50));
                            }}
                        }}
                        
                        // 3.5 Check for any visible autocomplete dropdown options (post-fill catch)
                        // This handles cases where filling a field triggered a dropdown that needs selection
                        {{
                            const dropdownSelectors = '.typeahead-input__dropdown-item, [role="option"], .artdeco-typeahead__result, [data-test-typeahead-item], li[class*="typeahead"], .basic-typeahead__selectable, .artdeco-typeahead__results-list li';
                            const postFillOptions = document.querySelectorAll(dropdownSelectors);
                            for (const option of postFillOptions) {{
                                if (option.offsetParent !== null) {{
                                    const text = option.innerText.trim();
                                    if (text && text.length > 2 && !text.toLowerCase().includes('select')) {{
                                        console.log('Post-fill: clicking autocomplete option:', text);
                                        option.click();
                                        return 'LINKEDIN_AUTOCOMPLETE_SELECTED|' + JSON.stringify([{{question: 'autocomplete', answer: text, inputType: 'typeahead'}}]);
                                    }}
                                }}
                            }}
                        }}
                        
                        // 4. Form Validation Check: Are we missing anything required?
                        const checkForErrors = () => {{
                            const requiredInputs = queryAllDeep('input[required], input[aria-required="true"], textarea[required], textarea[aria-required="true"]', modal);
                            const requiredSelects = queryAllDeep('select[required], select[aria-required="true"]', modal);
                            const radioGroups = queryAllDeep('fieldset[data-test-form-builder-radio-button-group], fieldset.fb-dash-form-element', modal);
                            
                            const hasEmptyInput = requiredInputs.some(i => isVisible(i) && !i.value.trim());
                            
                            // Strict check for "Select an option" value in native selects
                            const hasEmptySelect = requiredSelects.some(s => {{
                                return isVisible(s) && (!s.value || s.value === 'Select an option' || s.selectedIndex === 0);
                            }});
                            
                            const hasEmptyRadio = radioGroups.some(g => {{
                                const rs = Array.from(g.querySelectorAll('input[type="radio"]'));
                                return isVisible(g) && rs.length > 0 && !rs.some(r => r.checked);
                            }});
                            
                            // Check for unchecked required checkboxes (privacy/consent)
                            const requiredCheckboxes = queryAllDeep('input[type="checkbox"][required], input[type="checkbox"][aria-required="true"]', modal);
                            const uncheckedCheckboxes = requiredCheckboxes.filter(cb => isVisible(cb) && !cb.checked);
                            const hasUncheckedCheckbox = uncheckedCheckboxes.length > 0;
                            
                            const hasVisibleError = !!queryDeep('.artdeco-inline-feedback--error, .fb-dash-form-element__error-field', modal);
                            
                            if (hasEmptyInput || hasEmptySelect || hasEmptyRadio || hasUncheckedCheckbox || hasVisibleError) {{
                                console.log('Validation Error detected:', {{ hasEmptyInput, hasEmptySelect, hasEmptyRadio, hasUncheckedCheckbox, hasVisibleError }});
                                return true;
                            }}
                            return false;
                        }};
                        
                        // Find action buttons (Review, Next, Submit)
                        console.log('Searching for primary action button...');
                        const primaryBtn = queryDeep('button[aria-label*="Review your application"]', modal) ||
                                         queryDeep('button[aria-label*="Continue to next step"]', modal) ||
                                         queryDeep('button[aria-label*="next step"]', modal) ||
                                         queryDeep('button[aria-label*="Submit application"]', modal) ||
                                         queryDeep('.jobs-apply-button--primary', modal) ||
                                         findByText('button', 'submit application') ||
                                         findByText('button', 'next');

                        if (primaryBtn) {{
                            // Only click if form is valid
                            if (checkForErrors()) {{
                                console.log('Form has errors or missing required fields. Waiting for resolution...');
                                return 'LINKEDIN_FORM_STUCK: Validation errors or required fields missing';
                            }}
                            
                            console.log('Clicking modal primary button:', primaryBtn.innerText || primaryBtn.getAttribute('aria-label'));
                            primaryBtn.click();
                            const actionResult = primaryBtn.getAttribute('aria-label')?.includes('Submit') ? 'LINKEDIN_FORM_FINAL_SUBMITTED' : 'LINKEDIN_FORM_STEP_CONTINUED';
                            return actionResult + (formResults.length > 0 ? '|' + JSON.stringify(formResults) : '');
                        }}

                        return 'LINKEDIN_FORM_STUCK: No button found';
                    }};

                    // Helper: Check if element is a messaging overlay (NOT an Easy Apply modal)
                    const isMessagingOverlay = (el) => {{
                        const cls = (el.className || '').toLowerCase();
                        return cls.includes('msg-overlay') || cls.includes('msg-convo') || 
                               cls.includes('msg-form') || cls.includes('messaging') ||
                               cls.includes('msg-s-message-list') || cls.includes('msg-thread');
                    }};

                    // Check for modals (SHADOW DOM AWARE)
                    const checkModals = () => {{
                        console.log('Checking for active modals (Shadow DOM aware)...');
                        // Search deep for common modal selectors
                        const dialogs = queryAllDeep('.artdeco-modal, [role="dialog"], .jobs-easy-apply-modal, [class*="modal-container"]');
                        
                        for (const dialog of dialogs) {{
                            if (!isVisible(dialog)) {{
                                console.log('Found dialog but it is not visible:', dialog.className);
                                continue;
                            }}
                            
                            // CRITICAL: Skip LinkedIn messaging overlays — they match [role="dialog"]
                            // but are NOT Easy Apply modals
                            if (isMessagingOverlay(dialog)) {{
                                console.log('Skipping messaging overlay:', dialog.className?.substring(0, 80));
                                continue;
                            }}
                            
                            const text = dialog.innerText?.toLowerCase() || '';
                            console.log('Inspecting visible dialog:', dialog.className, 'Text snippet:', text.substring(0, 50));
                            
                            // 1. Success Modal
                            if (text.includes('application sent') || text.includes('application submitted') || text.includes('success')) {{
                                return {{ type: 'success', element: dialog }};
                            }}
                            
                            // 2. Safety/Reminder Modal
                            if (text.includes('safety reminder') || text.includes('legal reminder')) {{
                                return {{ type: 'safety', element: dialog }};
                            }}
                            
                            // 3. Easy Apply Form Modal
                            if (text.includes('apply to') || 
                                dialog.querySelector('.jobs-easy-apply-content') || 
                                dialog.querySelector('[class*="easy-apply"]') ||
                                dialog.querySelector('form') ||
                                text.includes('contact info') ||
                                text.includes('resume') ||
                                text.includes('additional questions')) {{
                                return {{ type: 'form', element: dialog }};
                            }}
                        }}
                        return null;
                    }};
                    
                    const modal = checkModals();
                    if (modal) {{
                        console.log('Active Modal detected:', modal.type);
                        if (modal.type === 'success') {{
                            const closeBtn = modal.element.querySelector('button[aria-label="Dismiss"]') || 
                                           modal.element.querySelector('.artdeco-modal__dismiss') || 
                                           modal.element.querySelector('button');
                            if (closeBtn) {{
                                console.log('Closing success modal...');
                                closeBtn.click();
                                return 'LINKEDIN_SUCCESS_MODAL_CLOSED';
                            }}
                        }}
                        
                        if (modal.type === 'safety') {{
                            const continueBtn = findByText('button', 'continue') || modal.element.querySelector('button:last-child');
                            if (continueBtn) {{
                                console.log('Continuing from safety modal...');
                                continueBtn.click();
                                return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                            }}
                        }}
                        
                        if (modal.type === 'form') {{
                            return handleLinkedInForm(modal.element);
                        }}
                    }}

                    // CRITICAL: If a REAL modal is visible but not matched above, do NOT click Easy Apply
                    // Must exclude messaging overlays which also match [role="dialog"]
                    const anyModal = queryDeep('.artdeco-modal, [role="dialog"]');
                    if (anyModal && isVisible(anyModal) && !isMessagingOverlay(anyModal)) {{
                        console.log('Unknown modal detected via deep query. Handling as generic form...');
                        return handleLinkedInForm(anyModal);
                    }}

                    // No modal open - handle job selection and clicking Easy Apply
                    console.log('No modal detected. Checking for Easy Apply button...');
                    const easyApplyBtn = findEasyApplyButton();
                    if (easyApplyBtn) {{
                        console.log('Easy Apply button found, clicking...');
                        easyApplyBtn.click();
                        return 'LINKEDIN_EASY_APPLY_CLICKED';
                    }}

                    // Navigation logic if needed
                    console.log('Looking for jobs in list...');
                    // 3. If no Easy Apply button and no modal, we might be on the search page
                    // We need to select the next job from the list
                    console.log('Looking for jobs in list...');
                    
                    // Find the sidebar with extreme robust fallbacks
                    // Priority 1: .jobs-search-results-list (standard)
                    // Priority 2: div[scrollable="true"] on the left side
                    // Priority 3: Geometry-based fallback (widest scrollable div on the left half)
                    let sidebar = queryDeep('.scaffold-layout__list') || 
                                  queryDeep('.jobs-search-results-list') ||
                                  queryDeep('div[scrollable="true"] > ul');
                    
                    if (!sidebar) {{
                         const scrollables = Array.from(queryAllDeep('div[scrollable="true"], .jobs-search-results-list, .scaffold-layout__list'));
                         // Find the one that is on the left side and has decent height
                         sidebar = scrollables.find(el => {{
                             const rect = el.getBoundingClientRect();
                             return rect.left < window.innerWidth / 2 && rect.height > 300;
                         }});
                    }}
                    
                    if (!sidebar) {{
                         console.log('Sidebar not found by selector, trying geometry...');
                         // Find any div that is scrollable and on the left
                         const allDivs = queryAllDeep('div');
                         for (const div of allDivs) {{
                             const rect = div.getBoundingClientRect();
                             if (rect.left < window.innerWidth / 2 && rect.width > 200 && rect.height > 400) {{
                                 if (div.scrollHeight > div.clientHeight || div.style.overflowY === 'auto' || div.style.overflow === 'auto') {{
                                     sidebar = div;
                                     break;
                                 }}
                             }}
                         }}
                    }}

                    if (!sidebar) {{
                        console.log('Sidebar ABSOLUTELY not found, attempting global scroll...');
                        window.scrollBy(0, 800);
                        return 'LINKEDIN_SCROLLED: No jobs found (Legacy)';
                    }}

                    // Find job cards within the sidebar
                    // Priority: .job-card-container (verified 2026), [data-job-id], .scaffold-layout__list-item
                    // NOTE: .jobs-search-results-list__list-item is DEAD as of 2026 LinkedIn update
                    let jobCards = Array.from(queryAllDeep('.job-card-container, [data-job-id], [data-occludable-job-id], .scaffold-layout__list-item', sidebar));
                    
                    // Deduplicate: a .job-card-container inside a .scaffold-layout__list-item would match twice
                    // Keep the most specific (deepest) element for each job
                    const seen = new Set();
                    jobCards = jobCards.filter(card => {{
                        const jobId = card.getAttribute('data-job-id') || card.querySelector('[data-job-id]')?.getAttribute('data-job-id') || card.innerText.substring(0, 60);
                        if (seen.has(jobId)) return false;
                        seen.add(jobId);
                        return true;
                    }});
                    
                    // Fallback to role="button" logic
                    if (jobCards.length === 0) {{
                        jobCards = Array.from(queryAllDeep('div[role="button"]', sidebar)).filter(el => 
                            el.innerText.includes('\\n') && el.innerText.length > 50 
                        );
                    }}

                    // Filter valid candidates
                    // 1. Must be visible
                    // 2. Must NOT be "Applied"
                    // 3. Must have "Easy Apply" text
                    // 4. Must not be the currently active card
                    const candidates = jobCards.filter(card => {{
                        const text = card.innerText.toLowerCase();
                        // Active class may be on card itself OR on a parent <li> element
                        // LinkedIn puts --active on the <li> wrapper, not on .job-card-container
                        const isActive = card.classList.contains('jobs-search-results-list__list-item--active') ||
                                        card.closest('.jobs-search-results-list__list-item--active') !== null ||
                                        card.closest('[aria-current="true"]') !== null ||
                                        card.getAttribute('aria-current') === 'true';
                        
                        if (isActive) return false;
                        if (!isVisible(card)) return false;
                        
                        // Check explicit "Applied" status
                        if (text.includes('applied')) {{
                            // console.log('Skipping applied job:', text.split('\\n')[0]);
                            return false;
                        }}
                        
                        // User requirement: Must be "Easy Apply"
                        // Note: Some cards might say "Easy Apply" in hidden text, so strict check is good
                        if (!text.includes('easy apply')) {{
                            // console.log('Skipping non-Easy Apply job:', text.split('\\n')[0]);
                            return false;
                        }}
                        
                        return true;
                    }});

                    if (candidates.length > 0) {{
                        const nextJob = candidates[0];
                        console.log('Clicking next job:', nextJob.innerText.split('\\n')[0]);
                        nextJob.click();
                        nextJob.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        return 'LINKEDIN_JOB_SELECTED';
                    }}

                    console.log('No eligible jobs visible in sidebar, scrolling sidebar...');
                    sidebar.scrollBy(0, 800);
                    return 'LINKEDIN_SCROLLED: No jobs found';
                }}
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
                        
                        // Try radio buttons - enhanced logic with better matching
                        const radios = document.querySelectorAll('input[type="radio"]');
                        if (radios.length > 0) {{
                            let clicked = false;
                            const qText = (document.querySelector('.chatbot_MessageContainer li.botItem:last-of-type .botMsg') ||
                                         document.querySelector('.botMsg.msg') ||
                                         document.querySelector('li.botItem .botMsg'))?.innerText || 'Unknown question';
                            
                            // First try fuzzy matching for radio button questions
                            const fuzzyAnswer = fuzzyMatch(qText);
                            let bestRadio = null;
                            
                            if (fuzzyAnswer) {{
                                // Use the enhanced matching function
                                bestRadio = findBestRadioMatch(fuzzyAnswer, radios);
                            }}
                            
                            // If no fuzzy match found, try Yes/No logic
                            if (!bestRadio) {{
                                for (const radio of radios) {{
                                    const label = radio.closest('label')?.innerText || radio.parentElement?.innerText || '';
                                    if (label.toLowerCase().includes('yes') || 
                                        label.toLowerCase().includes('serving') ||
                                        label.toLowerCase().includes('currently')) {{
                                        bestRadio = radio;
                                        break;
                                    }}
                                }}
                            }}
                            
                            // Final fallback: use first unselected radio
                            if (!bestRadio && radios.length > 0 && !radios[0].checked) {{ 
                                bestRadio = radios[0]; 
                            }}
                            
                            // Click the selected radio button
                            if (bestRadio && !bestRadio.checked) {{ 
                                bestRadio.click(); 
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
                            const isNoticePeriodQuestion = qTextLower.includes('notice period');
                            const isProgrammingLanguageQuestion = qTextLower.includes('programming language') || qTextLower.includes('programming lang') || qTextLower.includes('coding language') || (qTextLower.includes('language') && (qTextLower.includes('experienced') || qTextLower.includes('proficient') || qTextLower.includes('skilled')));
                            const isExperienceQuestion = !isProgrammingLanguageQuestion && (qTextLower.includes('experience') || qTextLower.includes('years'));
                            const preferredCities = ['bengaluru', 'bangalore', 'hyderabad', 'pune', 'mumbai', 'chennai', 'delhi', 'noida', 'gurgaon'];
                            
                            // FIRST: Check if this is a binary Yes/No question
                            // Build label map first for all checkboxes
                            const checkboxLabels = allCheckboxes.map(cb => {{
                                let label = cb.closest('label') || document.querySelector(`label.mcc__label[for="${{cb.id}}"]`);
                                if (!label && cb.id) {{
                                    label = document.querySelector(`label[for="${{cb.id}}"]`);
                                }}
                                if (!label) {{
                                    label = cb.parentElement; 
                                }}
                                const labelText = label ? (label.innerText || cb.id || '') : (cb.id || '');
                                return {{ cb, labelText, lowerLabel: labelText.toLowerCase() }};
                            }});
                            
                            // Check if binary (exactly 2 checkboxes with Yes/No labels)
                            const isBinaryYesNo = allCheckboxes.length === 2 && 
                                checkboxLabels.every((item) => 
                                    item.lowerLabel.includes('yes') || item.lowerLabel.includes('no')
                                );
                            
                            if (isBinaryYesNo) {{
                                // Find the Yes checkbox
                                const yesCheckbox = checkboxLabels.find((item) => 
                                    item.lowerLabel.includes('yes') && !item.lowerLabel.includes('not')
                                );
                                
                                if (yesCheckbox && !yesCheckbox.cb.checked) {{
                                    yesCheckbox.cb.click();
                                    if (!yesCheckbox.cb.checked) {{
                                        yesCheckbox.cb.checked = true;
                                        yesCheckbox.cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    }}
                                    clickedCount = 1;
                                    debugLog.push("CB: " + yesCheckbox.labelText);
                                }} else if (yesCheckbox && yesCheckbox.cb.checked) {{
                                    clickedCount = 1;
                                    debugLog.push("CB: " + yesCheckbox.labelText + " (already checked)");
                                }}
                            }} else if (isCityQuestion && allCheckboxes.length <= 3) {{
                                // Check if these are actual city checkboxes (not Yes/No)
                                const cityNames = ['pune', 'mumbai', 'bangalore', 'bengaluru', 'hyderabad', 'chennai', 'delhi', 'noida', 'gurgaon', 'gurugram', 'kolkata', 'ahmedabad'];
                                const containsCities = checkboxLabels.some(item => 
                                    cityNames.some(city => item.lowerLabel.includes(city))
                                );
                                
                                if (containsCities) {{
                                    // This is a city selection question - select ALL city options (skip "Skip")
                                    for (const item of checkboxLabels) {{
                                        // Skip the "Skip this question" option
                                        if (item.lowerLabel.includes('skip')) {{
                                            debugLog.push("CITY_SKIP: " + item.labelText);
                                            continue;
                                        }}
                                        
                                        // Check if this is a city option
                                        const isCityOption = cityNames.some(city => item.lowerLabel.includes(city));
                                        
                                        if (isCityOption && !item.cb.checked) {{
                                            item.cb.click();
                                            if (!item.cb.checked) {{
                                                item.cb.checked = true;
                                                item.cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            }}
                                            clickedCount++;
                                            debugLog.push("CITY_ALL: " + item.labelText);
                                        }} else if (isCityOption && item.cb.checked) {{
                                            clickedCount++;
                                            debugLog.push("CITY_ALL: " + item.labelText + " (already checked)");
                                        }}
                                    }}
                                    
                                    // Click save button after selecting all cities
                                    if (clickedCount > 0) {{
                                        const saveBtn = document.querySelector('div.sendMsg:not(.disabled)') || document.querySelector('.sendMsgbtn_container .sendMsg');
                                        if (saveBtn) {{ 
                                            saveBtn.click(); 
                                            return 'NAUKRI_CHAT_CHECKBOX_SAVED: Selected all ' + clickedCount + ' cities | DBG: ' + debugLog.join(', '); 
                                        }}
                                    }}
                                }} else {{
                                    // For relocation questions with few checkboxes, select Yes if available
                                    let yesCheckbox = checkboxLabels.find((item) => 
                                        item.lowerLabel.includes('yes') && !item.lowerLabel.includes('no')
                                    );
                                    
                                    // If no exact Yes found, look for positive indicators
                                    if (!yesCheckbox) {{
                                        yesCheckbox = checkboxLabels.find((item) => 
                                            item.lowerLabel.includes('willing') || 
                                            item.lowerLabel.includes('agree') ||
                                            item.lowerLabel.includes('confirm')
                                        );
                                    }}
                                    
                                    if (yesCheckbox && !yesCheckbox.cb.checked) {{
                                        yesCheckbox.cb.click();
                                        if (!yesCheckbox.cb.checked) {{
                                            yesCheckbox.cb.checked = true;
                                            yesCheckbox.cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        }}
                                        clickedCount = 1;
                                        debugLog.push("RELOC_CB: " + yesCheckbox.labelText);
                                    }} else if (yesCheckbox && yesCheckbox.cb.checked) {{
                                        clickedCount = 1;
                                        debugLog.push("RELOC_CB: " + yesCheckbox.labelText + " (already checked)");
                                    }}
                                }}
                            }} else if (isNoticePeriodQuestion) {{
                                // For notice period questions, select "Serving Notice Period" option
                                let bestCheckbox = null;
                                let bestScore = -1;
                                let allLabels = []; // Debug: store all found labels
                                
                                for (const item of checkboxLabels) {{
                                    allLabels.push(item.labelText);
                                    let score = 0;
                                    const labelLower = item.lowerLabel;
                                    
                                    // Highest priority: "Serving Notice Period" option
                                    if (labelLower.includes('serving notice period')) {{
                                        score = 100;
                                    }}
                                    // Secondary: any option with "serving" in it
                                    else if (labelLower.includes('serving')) {{
                                        score = 90;
                                    }}
                                    // Third: "Serving Notice" (without "Period")
                                    else if (labelLower.includes('serving notice')) {{
                                        score = 85;
                                    }}
                                    
                                    if (score > bestScore) {{
                                        bestScore = score;
                                        bestCheckbox = item;
                                    }}
                                }}
                                
                                // Click only the "Serving Notice Period" checkbox
                                if (bestCheckbox && bestScore >= 85 && !bestCheckbox.cb.checked) {{
                                    bestCheckbox.cb.click();
                                    if (!bestCheckbox.cb.checked) {{
                                        bestCheckbox.cb.checked = true;
                                        bestCheckbox.cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    }}
                                    clickedCount = 1;
                                    debugLog.push("NOTICE_CB: " + bestCheckbox.labelText + " (score: " + bestScore + ")");
                                }} else if (bestCheckbox && bestScore >= 85 && bestCheckbox.cb.checked) {{
                                    clickedCount = 1;
                                    debugLog.push("NOTICE_CB: " + bestCheckbox.labelText + " (already checked)");
                                }} else {{
                                    // Serving Notice Period not found - don't select anything and log for debugging
                                    debugLog.push("NOTICE_CB_ERROR: Serving Notice Period not found. Available: " + allLabels.join(", "));
                                }}
                            }} else if (isExperienceQuestion) {{
                                // For experience questions with checkboxes, select only the best matching range
                                // Target: 3.8 years experience -> select "3 - 5 years"
                                let bestCheckbox = null;
                                let bestScore = -1;
                                let allLabels = []; // Debug: store all found labels
                                const targetExperience = 3.8; // Years of experience
                                
                                for (const item of checkboxLabels) {{
                                    allLabels.push(item.labelText);
                                    let score = 0;
                                    const labelLower = item.lowerLabel;
                                    
                                    // Look for year ranges like "3 - 5 years", "1-2 years", etc.
                                    const rangeMatch = labelLower.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                                    if (rangeMatch) {{
                                        const min = parseFloat(rangeMatch[1]);
                                        const max = parseFloat(rangeMatch[2]);
                                        
                                        // If target falls within range, high score
                                        if (targetExperience >= min && targetExperience <= max) {{
                                            score = 100;
                                        }}
                                        // If target is close to range, medium score
                                        else if (Math.abs(targetExperience - max) <= 1 || Math.abs(targetExperience - min) <= 1) {{
                                            score = 80;
                                        }}
                                    }}
                                    // Look for single year values
                                    else {{
                                        const yearMatch = labelLower.match(/(\d+(?:\.\d+)?)/);
                                        if (yearMatch) {{
                                            const year = parseFloat(yearMatch[1]);
                                            const diff = Math.abs(targetExperience - year);
                                            if (diff <= 0.5) score = 90;
                                            else if (diff <= 1) score = 70;
                                            else if (diff <= 2) score = 50;
                                        }}
                                    }}
                                    
                                    if (score > bestScore) {{
                                        bestScore = score;
                                        bestCheckbox = item;
                                    }}
                                }}
                                
                                // Click only the best matching checkbox
                                if (bestCheckbox && bestScore >= 50 && !bestCheckbox.cb.checked) {{
                                    bestCheckbox.cb.click();
                                    if (!bestCheckbox.cb.checked) {{
                                        bestCheckbox.cb.checked = true;
                                        bestCheckbox.cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    }}
                                    clickedCount = 1;
                                    debugLog.push("EXP_CB: " + bestCheckbox.labelText + " (score: " + bestScore + ")");
                                }} else if (bestCheckbox && bestScore >= 50 && bestCheckbox.cb.checked) {{
                                    clickedCount = 1;
                                    debugLog.push("EXP_CB: " + bestCheckbox.labelText + " (already checked)");
                                }} else {{
                                    // No good match found - log for debugging
                                    debugLog.push("EXP_CB_ERROR: No matching experience range found. Available: " + allLabels.join(", "));
                                }}
                            }} else if (isProgrammingLanguageQuestion) {{
                                // For programming language questions, select ALL options except "Other" and "Skip"
                                for (const item of checkboxLabels) {{
                                    const labelLower = item.lowerLabel.trim();
                                    
                                    // Skip "Other" and "Skip" options
                                    if (labelLower === 'other' || labelLower.includes('skip') || labelLower === 'others' || labelLower.startsWith('other ')) {{
                                        debugLog.push("LANG_SKIP: " + item.labelText);
                                        continue;
                                    }}
                                    
                                    if (!item.cb.checked) {{
                                        item.cb.click();
                                        if (!item.cb.checked) {{
                                            item.cb.checked = true;
                                            item.cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        }}
                                        clickedCount++;
                                        debugLog.push("LANG_CB: " + item.labelText);
                                    }} else {{
                                        clickedCount++;
                                        debugLog.push("LANG_CB: " + item.labelText + " (already checked)");
                                    }}
                                }}
                            }} else {{
                                // Not binary - process normally
                                for (const cb of allCheckboxes) {{
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

                                    // ACTION: Click the checkbox (for non-binary questions)
                                    cb.click();
                                    
                                    // Verification & Fallback
                                    if (!cb.checked) {{
                                         cb.checked = true;
                                         cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    }}
                                    
                                    clickedCount++;
                                }}
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
                            // Actual tab IDs from DOM: profile, top_candidate, similar_jobs, preference
                            const tabOrder = ['profile', 'top_candidate', 'similar_jobs', 'preference'];
                            
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
                                
                                // DEBUG: Log what we're looking for
                                console.log('NAUKRI DEBUG: Looking for next tab:', nextTabId);
                                console.log('NAUKRI DEBUG: Current tab:', currentTabId, 'index:', currentIdx);
                                
                                // Try multiple selectors to find the tab
                                let nextTab = document.querySelector(`#${{nextTabId}} .tab-list-item`);
                                
                                if (!nextTab) {{
                                    // Fallback: try finding by data-tab attribute or other means
                                    const allTabs = document.querySelectorAll('.tab-list-item');
                                    for (const tab of allTabs) {{
                                        const tabText = tab.innerText.toLowerCase();
                                        if (tabText.includes(nextTabId.replace('_', ' ')) || 
                                            tabText.includes(nextTabId.replace('_', ''))) {{
                                            nextTab = tab;
                                            console.log('NAUKRI DEBUG: Found tab by text match:', tabText);
                                            break;
                                        }}
                                    }}
                                }}
                                
                                if (nextTab) {{
                                    console.log('NAUKRI DEBUG: Clicking tab:', nextTab.innerText?.substring(0, 30));
                                    nextTab.click();
                                    return 'NAUKRI_NAVIGATING_TO_TAB (0 jobs): ' + nextTabId + ' (from: ' + (currentTabId || 'unknown') + ')';
                                }} else {{
                                    console.log('NAUKRI DEBUG: Could not find tab element for:', nextTabId);
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
                        // Actual tab IDs from DOM: profile, top_candidate, similar_jobs, preference
                        const tabOrder = ['profile', 'top_candidate', 'similar_jobs', 'preference'];
                        
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
                            
                            // DEBUG: Log what we're looking for
                            console.log('NAUKRI DEBUG: Looking for next tab:', nextTabId);
                            console.log('NAUKRI DEBUG: Current tab:', currentTabId, 'index:', currentIdx);
                            
                            // Try multiple selectors to find the tab
                            let nextTab = document.querySelector(`#${{nextTabId}} .tab-list-item`);
                            
                            if (!nextTab) {{
                                // Fallback: try finding by data-tab attribute or other means
                                const allTabs = document.querySelectorAll('.tab-list-item');
                                for (const tab of allTabs) {{
                                    const tabText = tab.innerText.toLowerCase();
                                    if (tabText.includes(nextTabId.replace('_', ' ')) || 
                                        tabText.includes(nextTabId.replace('_', ''))) {{
                                        nextTab = tab;
                                        console.log('NAUKRI DEBUG: Found tab by text match:', tabText);
                                        break;
                                    }}
                                }}
                            }}
                            
                            if (nextTab) {{
                                console.log('NAUKRI DEBUG: Clicking tab:', nextTab.innerText?.substring(0, 30));
                                nextTab.click();
                                return 'NAUKRI_NAVIGATING_TO_TAB: ' + nextTabId;
                            }} else {{
                                console.log('NAUKRI DEBUG: Could not find tab element for:', nextTabId);
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
                        
                        // C. Location - Add all locations one by one (same logic as skills)
                        const locationsToAdd = ['Anywhere in India', 'Work from home / Remote', 'Bangalore', 'Noida', 'Gurgaon', 'Pune', 'Delhi', 'Delhi / NCR', 'Mumbai', 'Hyderabad'];
                        const locationSelectize = getSelectize('locations');
                        const locationInput = document.querySelector('input#locations-selectized');
                        if (locationInput) {{
                            const locControl = locationInput.closest('.selectize-control');
                            const locationContainer = locControl ? locControl.querySelector('.selectize-input') : null;
                            if (locationContainer) {{
                                // Check existing locations using Selectize API
                                let existingLocations = [];
                                if (locationSelectize) {{
                                    existingLocations = locationSelectize.items.map(key => {{
                                        const opt = locationSelectize.options[key];
                                        return opt ? (opt.text || opt.name || key).toLowerCase() : key.toLowerCase();
                                    }});
                                }} else {{
                                    // Fallback: DOM parsing with × removal
                                    existingLocations = Array.from(locationContainer.querySelectorAll('.item'))
                                        .map(item => (item.textContent || '').replace(/×/g, '').toLowerCase().trim());
                                }}
                                
                                for (const location of locationsToAdd) {{
                                    // Use a keyword from each location for matching
                                    const locKeyword = location.toLowerCase().split('/')[0].trim().split(' ').pop();
                                    if (!existingLocations.some(l => l.includes(locKeyword))) {{
                                        // Try Selectize API first
                                        if (locationSelectize) {{
                                            const options = locationSelectize.options;
                                            let foundKey = null;
                                            for (const key in options) {{
                                                const optText = (options[key].text || options[key].name || '').toLowerCase();
                                                if (optText.includes(location.toLowerCase()) || optText.includes(locKeyword)) {{
                                                    foundKey = key;
                                                    break;
                                                }}
                                            }}
                                            if (foundKey) {{
                                                locationSelectize.addItem(foundKey);
                                                return 'INSTAHYRE_ADDED_LOCATION: ' + location;
                                            }}
                                        }}
                                        // Fallback: Set pending state, trigger input, schedule click
                                        sessionStorage.setItem('instahyre_pending', 'location_' + location + '|' + Date.now());
                                        locationInput.focus();
                                        locationInput.click();
                                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                        if (setter) setter.call(locationInput, location);
                                        locationInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        setTimeout(() => {{
                                            const dropdown = locControl.querySelector('.selectize-dropdown-content');
                                            if (dropdown) {{
                                                const option = dropdown.querySelector('.option.active, .option:first-child');
                                                if (option) {{
                                                    option.click();
                                                    sessionStorage.removeItem('instahyre_pending');
                                                }}
                                            }}
                                        }}, 500);
                                        return 'INSTAHYRE_ADDING_LOCATION: ' + location;
                                    }}
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
                            const hasLocation = locContainer && locContainer.querySelectorAll('.item').length >= 3;
                            
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


