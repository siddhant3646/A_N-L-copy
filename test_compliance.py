#!/usr/bin/env python3
"""
Test script to verify compliance questions return correct answers.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.sentinel.agent import SentinelAgent
from src.sentinel.question_classifier import QuestionClassifier

# Test cases for compliance questions
compliance_tests = [
    # Visa employment questions - should return "No"
    ("worked with visa in the past 2 years", "No"),
    ("worked with visa in the last 2 years", "No"),
    ("have you worked with visa", "No"),
    ("have you worked for visa", "No"),
    ("have you ever worked for visa", "No"),
    ("have you been employed by visa", "No"),
    ("worked at visa", "No"),
    ("employed at visa", "No"),
    
    # Other company employment questions - should return "No"
    ("have you worked with navan in the past", "No"),
    ("have you worked with reed", "No"),
    ("have you worked with nielsen", "No"),
    ("worked with navan", "No"),
    ("worked for reed", "No"),
    ("worked at nielsen", "No"),
    
    # Current employer (Everbridge) - should return "Yes"
    ("worked with everbridge", "Yes"),
    ("have you worked at everbridge", "Yes"),
    ("are you currently employed by everbridge", "Yes"),
    # Previous employer (Fiserv) - should also return "Yes"
    ("worked with fiserv", "Yes"),
    ("have you worked at fiserv", "Yes"),
    ("are you currently employed by fiserv", "No"),
    
    # Generic employment history - should return "No"
    ("have you worked with any of the following companies", "No"),
    ("have you worked with any of these companies", "No"),
    ("have you ever been employed by any of the", "No"),
    ("currently employed by any of the", "No"),
    ("currently an employee of any", "No"),
    
    # Conflict of interest - should return "No"
    ("conflict of interest", "No"),
    ("do you have any conflict of interest", "No"),
    ("do you have any relatives working", "No"),
    ("do you have any family members employed", "No"),
    ("close relative working", "No"),
    
    # Third party/contractor - should return "No"
    ("are you a third party", "No"),
    ("are you currently a third party", "No"),
    ("are you a temporary employee", "No"),
    
    # Visa sponsorship - should return "No"
    ("visa sponsorship", "No"),
    ("will you now or in the future require sponsorship", "No"),
    
    # Regular yes/no questions - should return "Yes"
    ("willing to relocate", "Yes"),
    ("are you comfortable working", "Yes"),
    ("do you have experience with java", "Yes"),
]

def test_question_classifier():
    """Test the QuestionClassifier for yes/no answers."""
    print("\n" + "="*60)
    print("Testing QuestionClassifier._get_yes_no_answer()")
    print("="*60)
    
    classifier = QuestionClassifier()
    passed = 0
    failed = 0
    
    for question, expected in compliance_tests[:10]:  # Test first 10 with classifier
        answer = classifier._get_yes_no_answer(question)
        status = "✅ PASS" if answer == expected else "❌ FAIL"
        
        if answer == expected:
            passed += 1
        else:
            failed += 1
            
        print(f"{status} | Q: {question[:50]:<50} | Expected: {expected:<3} | Got: {answer}")
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return passed, failed

def test_sentinel_agent():
    """Test the SentinelAgent fuzzy matching for compliance questions."""
    print("\n" + "="*60)
    print("Testing SentinelAgent._fuzzy_match_question()")
    print("="*60)
    
    # Create agent without browser
    agent = SentinelAgent(browser=None)
    
    passed = 0
    failed = 0
    
    for question, expected in compliance_tests:
        result = agent._fuzzy_match_question(question)
        answer = result[0] if result[0] else ""
        
        # For simple yes/no questions, check if the answer matches
        if expected in ["Yes", "No"]:
            # Check if the expected answer is in the result
            match = expected.lower() in answer.lower() if answer else False
            status = "✅ PASS" if match else "❌ FAIL"
            
            if match:
                passed += 1
            else:
                failed += 1
        else:
            # For other answers, just check if we got something
            status = "✅ PASS" if answer else "⚠️  EMPTY"
            passed += 1 if answer else 0
            
        display_answer = answer[:40] + "..." if len(answer) > 40 else answer
        print(f"{status} | Q: {question[:45]:<45} | Expected: {expected:<10} | Got: {display_answer}")
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return passed, failed

if __name__ == "__main__":
    print("Compliance Question Testing Suite")
    print("="*60)
    
    # Test QuestionClassifier
    c_passed, c_failed = test_question_classifier()
    
    # Test SentinelAgent
    a_passed, a_failed = test_sentinel_agent()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"QuestionClassifier: {c_passed} passed, {c_failed} failed")
    print(f"SentinelAgent: {a_passed} passed, {a_failed} failed")
    print(f"Total: {c_passed + a_passed} passed, {c_failed + a_failed} failed")
    
    if c_failed + a_failed == 0:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {c_failed + a_failed} tests failed")
        sys.exit(1)
