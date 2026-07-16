"""
UI Error Detector - Platform-specific error detection and healing.

Detects validation errors, modal messages, and form issues on:
- LinkedIn (artdeco-inline-feedback, modal errors)
- Naukri (ss-snackbar, validation errors)
- Instahyre (error modals)

Integrates with SelfHealingMatcher for automatic retry.
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from playwright.async_api import Page


class ErrorType(Enum):
    VALIDATION_ERROR = "validation_error"
    INPUT_MISMATCH = "input_mismatch"
    REQUIRED_FIELD_EMPTY = "required_field_empty"
    INVALID_FORMAT = "invalid_format"
    SUBMISSION_FAILED = "submission_failed"
    RATE_LIMIT = "rate_limit"
    SESSION_EXPIRED = "session_expired"
    STATE_DESYNC = "state_desync"
    GENERIC_ERROR = "generic_error"


class Platform(Enum):
    LINKEDIN = "linkedin"
    NAUKRI = "naukri"
    INSTAHYRE = "instahyre"
    UNKNOWN = "unknown"


@dataclass
class UIError:
    error_type: ErrorType
    platform: Platform
    message: str
    field_label: Optional[str]
    field_value: Optional[str]
    available_options: List[str]
    suggestions: List[str]
    screenshot_path: Optional[str] = None


class UIErrorDetector:
    """
    Detects errors in UI and provides recovery suggestions.
    """
    
    ERROR_PATTERNS = {
        ErrorType.INPUT_MISMATCH: [
            'invalid', 'incorrect', 'not valid', 'please select',
            'please enter', 'choose a valid', 'selection required'
        ],
        ErrorType.INVALID_FORMAT: [
            'format', 'pattern', 'should be', 'must be', 'invalid format',
            'please enter a valid', 'expected format'
        ],
        ErrorType.REQUIRED_FIELD_EMPTY: [
            'required', 'mandatory', 'cannot be empty', 'this field is required',
            'please fill', 'complete this field'
        ],
        ErrorType.SUBMISSION_FAILED: [
            'error submitting', 'failed to submit', 'try again',
            'something went wrong', 'error loading'
        ],
        ErrorType.RATE_LIMIT: [
            'rate limit', 'too many', 'try again later', 'limit reached',
            'slow down', 'please wait',
            # Naukri server-side error toast: "There was some error processing your request"
            'error processing', 'some error', 'processing your request',
            'something went wrong',
        ],
    }
    
    def __init__(self, page: Page, screenshot_dir: str = None):
        self.page = page
        self.screenshot_dir = screenshot_dir or "~/Desktop/sentinel_errors"
    
    async def detect_errors(self) -> List[UIError]:
        platform = await self._detect_platform()
        errors = []
        
        if platform == Platform.LINKEDIN:
            errors = await self._detect_linkedin_errors()
        elif platform == Platform.NAUKRI:
            errors = await self._detect_naukri_errors()
        elif platform == Platform.INSTAHYRE:
            errors = await self._detect_instahyre_errors()
        
        return errors
    
    async def _detect_platform(self) -> Platform:
        try:
            url = self.page.url.lower()
            if 'linkedin.com' in url:
                return Platform.LINKEDIN
            elif 'naukri.com' in url:
                return Platform.NAUKRI
            elif 'instahyre.com' in url:
                return Platform.INSTAHYRE
        except Exception:
            pass
        return Platform.UNKNOWN
    
    async def _detect_linkedin_errors(self) -> List[UIError]:
        errors = []
        
        try:
            inline_errors = await self.page.evaluate('''
                () => {
                    const errors = [];
                    const errorElements = document.querySelectorAll('.artdeco-inline-feedback--error');
                    
                    for (const errorEl of errorElements) {
                        const message = errorEl.querySelector('.artdeco-inline-feedback__message')?.innerText || 
                                       errorEl.innerText || '';
                        
                        const container = errorEl.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question');
                        const label = container?.querySelector('label')?.innerText || '';
                        const input = container?.querySelector('input, select, textarea');
                        // Read value from multiple sources: LinkedIn React-controlled inputs
                        // don't always expose their visible text via .value.
                        let value = input?.value || '';
                        if (!value.trim() && input) {
                            value = input.getAttribute('aria-valuenow') || input.getAttribute('data-value') || '';
                            if (!value.trim()) {
                                const preview = container?.querySelector('.fb-dash-form-element__preview-value, [data-test*="displayValue"], [data-test*="DisplayValue"], span.fb-dash-form-element__value, .fb-dash-form-element__text, [class*="preview-value"], [class*="display-value"]');
                                if (preview) value = (preview.innerText || preview.textContent || '').trim();
                            }
                        }
                        
                        const select = container?.querySelector('select');
                        const options = select ? 
                            Array.from(select.options).map(o => o.text) : [];
                        
                        errors.push({
                            message: message.trim(),
                            field_label: label.trim(),
                            field_value: value,
                            available_options: options
                        });
                    }
                    
                    return errors;
                }
            ''')
            
            for err in inline_errors:
                error_type = self._classify_error(err['message'])
                if err.get('field_value') and err['field_value'].strip():
                    error_type = ErrorType.STATE_DESYNC
                errors.append(UIError(
                    error_type=error_type,
                    platform=Platform.LINKEDIN,
                    message=err['message'],
                    field_label=err['field_label'],
                    field_value=err['field_value'],
                    available_options=err['available_options'],
                    suggestions=self._get_suggestions(error_type, err)
                ))
            
            modal_error = await self.page.evaluate('''
                () => {
                    const errorModal = document.querySelector('.artdeco-modal--error, [role="alert"]');
                    if (errorModal && errorModal.offsetParent !== null) {
                        return errorModal.innerText;
                    }
                    return null;
                }
            ''')
            
            if modal_error:
                errors.append(UIError(
                    error_type=ErrorType.SUBMISSION_FAILED,
                    platform=Platform.LINKEDIN,
                    message=modal_error,
                    field_label=None,
                    field_value=None,
                    available_options=[],
                    suggestions=['Retry submission', 'Check for missing fields']
                ))

            errors.extend(await self._detect_aria_invalid_errors(Platform.LINKEDIN))
            errors.extend(await self._detect_error_color_elements(Platform.LINKEDIN))
            errors = self._dedupe_errors(errors)

        except Exception as e:
            print(f"⚠️ Error detecting LinkedIn errors: {e}")
        
        return errors
    
    async def _detect_naukri_errors(self) -> List[UIError]:
        errors = []
        
        try:
            snackbar_error = await self.page.evaluate('''
                () => {
                    // Hybrid selector: real Naukri DOM is div.ss-snackbar.ss-snackbar-error.ss-snackbar-active
                    // (no -body suffix). Keep legacy .ss-snackbar-body + attribute fallbacks for resilience.
                    const snackbar = document.querySelector(
                        '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                        + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
                    );
                    if (snackbar && snackbar.offsetParent !== null) {
                        return snackbar.innerText;
                    }
                    // Generic fallback: any visible snackbar/toast/alert mentioning error/processing
                    const generic = document.querySelector('[class*="snackbar"], [class*="toast"], [role="alert"]');
                    if (generic && generic.offsetParent !== null) {
                        const t = (generic.innerText || '').toLowerCase();
                        if (t.includes('error') || t.includes('processing') || t.includes('some error')) {
                            return generic.innerText;
                        }
                    }
                    return null;
                }
            ''')
            
            if snackbar_error:
                error_type = self._classify_error(snackbar_error)
                errors.append(UIError(
                    error_type=error_type,
                    platform=Platform.NAUKRI,
                    message=snackbar_error,
                    field_label=None,
                    field_value=None,
                    available_options=[],
                    suggestions=self._get_suggestions(error_type, {'message': snackbar_error})
                ))
            
            field_errors = await self.page.evaluate('''
                () => {
                    const errors = [];
                    const errorElements = document.querySelectorAll('.error-message, .validation-error');
                    
                    for (const errorEl of errorElements) {
                        if (errorEl.offsetParent === null) continue;
                        
                        const message = errorEl.innerText;
                        const container = errorEl.closest('.form-group, .input-field');
                        const label = container?.querySelector('label')?.innerText || '';
                        
                        errors.push({
                            message: message,
                            field_label: label
                        });
                    }
                    
                    return errors;
                }
            ''')
            
            for err in field_errors:
                error_type = self._classify_error(err['message'])
                errors.append(UIError(
                    error_type=error_type,
                    platform=Platform.NAUKRI,
                    message=err['message'],
                    field_label=err.get('field_label'),
                    field_value=None,
                    available_options=[],
                    suggestions=[]
                ))

            errors.extend(await self._detect_aria_invalid_errors(Platform.NAUKRI))
            errors.extend(await self._detect_error_color_elements(Platform.NAUKRI))
            errors = self._dedupe_errors(errors)

        except Exception as e:
            print(f"⚠️ Error detecting Naukri errors: {e}")
        
        return errors
    
    async def _detect_instahyre_errors(self) -> List[UIError]:
        errors = []
        
        try:
            error_message = await self.page.evaluate('''
                () => {
                    const errorEl = document.querySelector('.error-modal, .alert-error');
                    if (errorEl && errorEl.offsetParent !== null) {
                        return errorEl.innerText;
                    }
                    return null;
                }
            ''')
            
            if error_message:
                error_type = self._classify_error(error_message)
                errors.append(UIError(
                    error_type=error_type,
                    platform=Platform.INSTAHYRE,
                    message=error_message,
                    field_label=None,
                    field_value=None,
                    available_options=[],
                    suggestions=[]
                ))

            errors.extend(await self._detect_aria_invalid_errors(Platform.INSTAHYRE))
            errors.extend(await self._detect_error_color_elements(Platform.INSTAHYRE))
            errors = self._dedupe_errors(errors)

        except Exception as e:
            print(f"⚠️ Error detecting Instahyre errors: {e}")
        
        return errors
    
    async def _detect_aria_invalid_errors(self, platform: Platform) -> List[UIError]:
        """
        Method A: Detect errors via aria-invalid="true" attributes.

        Most reliable across frameworks. Scans for inputs/selects/textareas
        that the framework has marked as invalid.
        """
        errors = []
        try:
            raw = await self.page.evaluate('''
                () => {
                    const errors = [];
                    const invalids = document.querySelectorAll(
                        'input[aria-invalid="true"], select[aria-invalid="true"], textarea[aria-invalid="true"]'
                    );
                    for (const el of invalids) {
                        if (el.offsetParent === null && el.type !== 'hidden') continue;

                        const container = el.closest(
                            '.fb-dash-form-element, .jobs-easy-apply-form-section__question, .form-group, .input-field, [role="group"]'
                        ) || el.parentElement;

                        let label = '';
                        if (container) {
                            const labelEl = container.querySelector('label');
                            if (labelEl) label = labelEl.innerText;
                        }
                        if (!label) {
                            const id = el.id;
                            if (id) {
                                const forLabel = document.querySelector('label[for="' + id + '"]');
                                if (forLabel) label = forLabel.innerText;
                            }
                        }

                        let value = el.value || '';
                        if (!value.trim()) {
                            value = el.getAttribute('aria-valuenow') || el.getAttribute('data-value') || '';
                        }

                        let options = [];
                        if (el.tagName.toLowerCase() === 'select') {
                            options = Array.from(el.options).map(o => o.text);
                        }

                        let message = '';
                        if (container) {
                            const msgEl = container.querySelector(
                                '.artdeco-inline-feedback--error .artdeco-inline-feedback__message, .error-message, .validation-error'
                            );
                            if (msgEl) message = msgEl.innerText.trim();
                        }
                        if (!message) message = 'Invalid input';

                        errors.push({
                            message: message,
                            field_label: (label || '').trim(),
                            field_value: value,
                            available_options: options
                        });
                    }
                    return errors;
                }
            ''')

            for err in raw:
                error_type = self._classify_error(err['message'])
                if err.get('field_value') and err['field_value'].strip():
                    error_type = ErrorType.STATE_DESYNC
                errors.append(UIError(
                    error_type=error_type,
                    platform=platform,
                    message=err['message'],
                    field_label=err.get('field_label'),
                    field_value=err.get('field_value'),
                    available_options=err.get('available_options', []),
                    suggestions=self._get_suggestions(error_type, err)
                ))
        except Exception as e:
            print(f"⚠️ Error detecting aria-invalid errors: {e}")

        return errors

    async def _detect_error_color_elements(self, platform: Platform) -> List[UIError]:
        """
        Method D: Detect errors via computed CSS color (fallback).

        Targets LinkedIn Artdeco error red rgb(204, 0, 0) with a tolerance
        band: R 200-210, G 0-10, B 0-10.
        """
        errors = []
        try:
            raw = await self.page.evaluate('''
                () => {
                    const ERROR_R_MIN = 200, ERROR_R_MAX = 210;
                    const ERROR_G_MAX = 10;
                    const ERROR_B_MAX = 10;
                    const errors = [];

                    const candidates = document.querySelectorAll(
                        'p, span, div, li, .artdeco-inline-feedback__message'
                    );
                    for (const el of candidates) {
                        if (el.offsetParent === null) continue;
                        const text = (el.innerText || '').trim();
                        if (!text || text.length > 200) continue;

                        const color = window.getComputedStyle(el).color;
                        const m = color.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                        if (!m) continue;

                        const r = parseInt(m[1]);
                        const g = parseInt(m[2]);
                        const b = parseInt(m[3]);

                        if (r >= ERROR_R_MIN && r <= ERROR_R_MAX &&
                            g <= ERROR_G_MAX && b <= ERROR_B_MAX) {
                            const container = el.closest(
                                '.fb-dash-form-element, .jobs-easy-apply-form-section__question, .form-group, .input-field'
                            ) || el.parentElement;

                            let label = '';
                            let value = '';
                            let options = [];

                            if (container) {
                                const labelEl = container.querySelector('label');
                                if (labelEl) label = labelEl.innerText;
                                const input = container.querySelector('input, select, textarea');
                                if (input) {
                                    value = input.value || input.getAttribute('aria-valuenow') || '';
                                    if (input.tagName.toLowerCase() === 'select') {
                                        options = Array.from(input.options).map(o => o.text);
                                    }
                                }
                            }

                            errors.push({
                                message: text,
                                field_label: (label || '').trim(),
                                field_value: value,
                                available_options: options
                            });
                        }
                    }
                    return errors;
                }
            ''')

            for err in raw:
                error_type = self._classify_error(err['message'])
                if err.get('field_value') and err['field_value'].strip():
                    error_type = ErrorType.STATE_DESYNC
                errors.append(UIError(
                    error_type=error_type,
                    platform=platform,
                    message=err['message'],
                    field_label=err.get('field_label'),
                    field_value=err.get('field_value'),
                    available_options=err.get('available_options', []),
                    suggestions=self._get_suggestions(error_type, err)
                ))
        except Exception as e:
            print(f"⚠️ Error detecting color-based errors: {e}")

        return errors

    def _dedupe_errors(self, errors: List[UIError]) -> List[UIError]:
        """Remove duplicate errors by (field_label, message) key."""
        seen = set()
        result = []
        for err in errors:
            key = (err.field_label or '', err.message or '')
            if key in seen:
                continue
            seen.add(key)
            result.append(err)
        return result

    def _classify_error(self, message: str) -> ErrorType:
        if not message:
            return ErrorType.GENERIC_ERROR
        message_lower = message.lower()
        
        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern in message_lower:
                    return error_type
        
        return ErrorType.GENERIC_ERROR
    
    def _get_suggestions(self, error_type: ErrorType, error_data: Dict) -> List[str]:
        suggestions = {
            ErrorType.INPUT_MISMATCH: [
                'Try alternative value from options',
                'Check if value matches available choices',
                'Use fuzzy matching to find closest option'
            ],
            ErrorType.INVALID_FORMAT: [
                'Reformat the value to match expected pattern',
                'Extract numeric part only',
                'Check date format requirements'
            ],
            ErrorType.REQUIRED_FIELD_EMPTY: [
                'Fill the required field',
                'Check for hidden required fields'
            ],
            ErrorType.SUBMISSION_FAILED: [
                'Retry submission',
                'Check for network issues',
                'Verify all fields are correctly filled'
            ],
            ErrorType.RATE_LIMIT: [
                'Wait before retrying',
                'Pause application process'
            ],
        }
        
        if error_data.get('available_options'):
            opts = error_data['available_options'][:5]
            base_suggestions = suggestions.get(error_type, ['No specific suggestion'])
            return base_suggestions + [f"Available options: {', '.join(opts)}"]
        
        return suggestions.get(error_type, ['No specific suggestion'])
    
    async def has_errors(self) -> bool:
        errors = await self.detect_errors()
        return len(errors) > 0
    
    async def get_first_error(self) -> Optional[UIError]:
        errors = await self.detect_errors()
        return errors[0] if errors else None
    
    async def dismiss_error_modals(self) -> bool:
        try:
            dismissed = await self.page.evaluate('''
                () => {
                    const linkedinClose = document.querySelector(
                        '.artdeco-modal__dismiss, button[aria-label*="Dismiss"], button[aria-label*="Close"]'
                    );
                    if (linkedinClose && linkedinClose.offsetParent !== null) {
                        linkedinClose.click();
                        return true;
                    }
                    
                    const naukriClose = document.querySelector('.ss-close, button.close');
                    if (naukriClose && naukriClose.offsetParent !== null) {
                        naukriClose.click();
                        return true;
                    }
                    
                    return false;
                }
            ''')
            return dismissed
        except Exception:
            return False


class UIErrorRecovery:
    """
    Handles recovery from UI errors with self-healing integration.
    """
    
    def __init__(
        self,
        detector: UIErrorDetector,
        self_healing_matcher,
        input_resolver
    ):
        self.detector = detector
        self.self_healing = self_healing_matcher
        self.resolver = input_resolver
    
    async def attempt_recovery(
        self,
        error: UIError,
        original_answer: str,
        question: str = ""
    ) -> Tuple[bool, str, str]:
        if error.error_type == ErrorType.STATE_DESYNC:
            from src.sentinel.human_behavior import resync_input_state

            try:
                field_label = error.field_label or ""
                js_find = """() => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    const target = labels.find(l => l.innerText.trim().includes('""" + field_label.replace("'", "\'") + """'));
                    if (!target) return null;
                    const container = target.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question, .form-group, .input-field') || target.parentElement;
                    return container ? container.querySelector('input:not([type="radio"]):not([type="checkbox"]), textarea, select') : null;
                }"""
                element = await self.detector.page.query_selector(
                    'input[aria-invalid="true"], textarea[aria-invalid="true"], select[aria-invalid="true"]'
                )
                if not element and field_label:
                    element = await self.detector.page.evaluate_handle(js_find)

                if element:
                    ok = await resync_input_state(self.detector.page, element)
                    if ok:
                        return True, original_answer, 'state_resync'
            except Exception as e:
                print(f"⚠️ STATE_DESYNC recovery failed: {e}")

            return False, original_answer, 'state_resync_failed'

        if error.error_type == ErrorType.INPUT_MISMATCH:
            if error.available_options:
                from src.patterns.input_aware_resolver import Option, InputType
                
                options = [
                    Option(value=o, label=o, index=i) 
                    for i, o in enumerate(error.available_options)
                ]
                
                result = self.resolver.resolve(
                    answer=original_answer,
                    input_type=InputType.SELECT,
                    options=options,
                    question=question
                )
                
                if result.matched_option:
                    return True, result.matched_option.label, 'option_matching'
            
            learned = self.self_healing.get_learned_answer(question)
            if learned:
                return True, learned[0], 'learned_pattern'
        
        elif error.error_type == ErrorType.INVALID_FORMAT:
            reformatted = self._reformat_answer(original_answer, error.message)
            if reformatted != original_answer:
                return True, reformatted, 'reformatting'
        
        elif error.error_type == ErrorType.REQUIRED_FIELD_EMPTY:
            return True, original_answer, 'fill_required'
        
        return False, original_answer, 'no_recovery'
    
    def _reformat_answer(self, answer: str, error_message: str) -> str:
        if not answer:
            return answer
        import re
        
        error_lower = error_message.lower() if error_message else ''
        
        if 'number' in error_lower or 'numeric' in error_lower:
            match = re.search(r'(\d+\.?\d*)', answer)
            if match:
                return match.group(1)
        
        if 'date' in error_lower:
            for pattern in [r'(\d{2})/(\d{2})/(\d{4})', r'(\d{4})-(\d{2})-(\d{2})']:
                match = re.search(pattern, answer)
                if match:
                    groups = match.groups()
                    if len(groups[0]) == 4:
                        return f"{groups[2]}/{groups[1]}/{groups[0]}"
                    return match.group(0)
        
        if 'phone' in error_lower or 'mobile' in error_lower:
            digits = re.sub(r'[^\d]', '', answer)
            if len(digits) >= 10:
                return digits[-10:]
        
        return answer
    
    async def heal_and_retry(
        self,
        fill_function,
        field_identifier: str,
        original_answer: str,
        question: str = "",
        max_retries: int = 3
    ) -> Tuple[bool, str]:
        for attempt in range(max_retries):
            await fill_function()
            await asyncio.sleep(0.5)
            
            error = await self.detector.get_first_error()
            
            if not error:
                return True, original_answer
            
            print(f"⚠️ UI Error detected (attempt {attempt + 1}/{max_retries}): {error.message[:50]}")
            
            success, new_answer, strategy = await self.attempt_recovery(
                error, original_answer, question
            )
            
            if success and new_answer != original_answer:
                print(f"🔧 Recovery strategy: {strategy} -> {new_answer}")
                original_answer = new_answer
                continue
            
            await self.detector.dismiss_error_modals()
            
            self.self_healing.on_answer_failure(
                question=question,
                attempted_answer=original_answer,
                input_type='select' if error.available_options else 'text',
                options=error.available_options,
                platform=error.platform.value,
                url=self.detector.page.url,
                error_type=error.error_type.value
            )
        
        return False, original_answer
