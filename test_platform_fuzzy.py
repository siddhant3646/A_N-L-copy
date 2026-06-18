#!/usr/bin/env python3
"""
Test script for platform-specific fuzzy matching for tech stack experience questions.
"""

import sys
sys.path.insert(0, '/Users/siddhant/Desktop/Resume/MyModels/A_N&L')

from src.sentinel.question_classifier import QuestionClassifier


def test_linkedin_tech_experience():
    """Test LinkedIn tech stack experience answers."""
    print("\n" + "="*60)
    print("TESTING LINKEDIN TECH STACK EXPERIENCE")
    print("="*60)
    
    classifier = QuestionClassifier(platform="linkedin")
    
    test_cases = [
        "How many years of work experience do you have with React?",
        "How many years into Java?",
        "Experience with Python",
        "Years into AWS",
    ]
    
    print("\nExpected: All should return '4' (numeric only, no 'Years')\n")
    
    all_passed = True
    for question in test_cases:
        category, confidence = classifier.classify(question)
        answer, ans_confidence = classifier.get_answer(question, category)
        
        passed = answer == "4"
        status = "PASS" if passed else "FAIL"
        
        print(f"{status} | {question[:50]:<50} | Answer: '{answer}'")
        
        if not passed:
            all_passed = False
            print(f"      Expected: '4', Got: '{answer}'")
    
    return all_passed


def test_naukri_tech_experience():
    """Test Naukri tech stack experience answers."""
    print("\n" + "="*60)
    print("TESTING NAUKRI TECH STACK EXPERIENCE")
    print("="*60)
    
    classifier = QuestionClassifier(platform="naukri")
    
    test_cases = [
        "How many years of work experience do you have with React?",
        "How many years into Java?",
        "Experience with Python",
        "Years into AWS",
    ]
    
    print("\nExpected: All should return '4 Years' (with 'Years' suffix)\n")
    
    all_passed = True
    for question in test_cases:
        category, confidence = classifier.classify(question)
        answer, ans_confidence = classifier.get_answer(question, category)
        
        passed = answer == "4 Years"
        status = "PASS" if passed else "FAIL"
        
        print(f"{status} | {question[:50]:<50} | Answer: '{answer}'")
        
        if not passed:
            all_passed = False
            print(f"      Expected: '4 Years', Got: '{answer}'")
    
    return all_passed


def test_platform_difference():
    """Test that LinkedIn and Naukri give different answers."""
    print("\n" + "="*60)
    print("TESTING PLATFORM DIFFERENCE")
    print("="*60)
    
    linkedin_classifier = QuestionClassifier(platform="linkedin")
    naukri_classifier = QuestionClassifier(platform="naukri")
    
    test_question = "How many years of work experience do you have with React?"
    
    li_category, _ = linkedin_classifier.classify(test_question)
    li_answer, _ = linkedin_classifier.get_answer(test_question, li_category)
    
    na_category, _ = naukri_classifier.classify(test_question)
    na_answer, _ = naukri_classifier.get_answer(test_question, na_category)
    
    print(f"\nQuestion: {test_question}")
    print(f"LinkedIn Answer: '{li_answer}'")
    print(f"Naukri Answer:   '{na_answer}'")
    
    if li_answer == "4" and na_answer == "4 Years":
        print("\nPASS - Platform-specific answers are correct!")
        return True
    else:
        print(f"\nFAIL - Expected LinkedIn: '4', Naukri: '4 Years'")
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("PLATFORM-SPECIFIC FUZZY MATCHING TEST SUITE")
    print("="*60)
    
    results = []
    
    results.append(("LinkedIn Tech Experience", test_linkedin_tech_experience()))
    results.append(("Naukri Tech Experience", test_naukri_tech_experience()))
    results.append(("Platform Difference", test_platform_difference()))
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    print("\n" + "="*60)
    if all_passed:
        print("ALL TESTS PASSED!")
        print("="*60)
        sys.exit(0)
    else:
        print("SOME TESTS FAILED!")
        print("="*60)
        sys.exit(1)
